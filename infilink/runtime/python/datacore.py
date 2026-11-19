"""INFILINK DataCore: bounded JSON-document storage with a SQLite reference adapter.

This is a local reference backend, not a distributed database. External adapters can
implement StorageAdapter without changing the DataCore API.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
_MAX_DOCUMENT_BYTES = 1_048_576


class DataCoreError(Exception):
    """Base error for DataCore operations."""


class SchemaError(DataCoreError):
    """Invalid or incompatible collection schema."""


class StorageAdapter(ABC):
    """Minimal adapter contract for relational/document storage backends."""
    @abstractmethod
    def close(self) -> None: ...
    @abstractmethod
    def health(self) -> dict[str, Any]: ...
    @abstractmethod
    def create_collection(self, name: str, schema: dict[str, Any], version: int = 1) -> None: ...
    @abstractmethod
    def put(self, collection: str, document: dict[str, Any], document_id: str | None = None) -> str: ...
    @abstractmethod
    def get(self, collection: str, document_id: str) -> dict[str, Any] | None: ...
    @abstractmethod
    def delete(self, collection: str, document_id: str) -> bool: ...


class SQLiteAdapter(StorageAdapter):
    """SQLite-backed document store with schema metadata and safe indexed lookup."""
    def __init__(self, database: str | Path = ":memory:") -> None:
        self.database = str(database)
        if self.database != ":memory:":
            Path(self.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.database, timeout=5.0)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA busy_timeout = 5000")
        if self.database != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS _iil_collections (
                name TEXT PRIMARY KEY, schema_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version > 0), created_at REAL NOT NULL
            );
        """)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def health(self) -> dict[str, Any]:
        row = self._db.execute("PRAGMA quick_check").fetchone()
        return {"backend": "sqlite", "ok": bool(row and row[0] == "ok"), "database": self.database}

    def create_collection(self, name: str, schema: dict[str, Any], version: int = 1) -> None:
        _check_name(name)
        _validate_schema(schema)
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise SchemaError("schema version must be a positive integer")
        encoded = _json(schema)
        existing = self._db.execute(
            "SELECT schema_json, version FROM _iil_collections WHERE name=?", (name,)
        ).fetchone()
        if existing:
            if existing["schema_json"] != encoded or existing["version"] != version:
                raise SchemaError("collection exists with a different schema; use an explicit migration")
            return
        with self._db:
            self._db.execute(
                "INSERT INTO _iil_collections(name,schema_json,version,created_at) VALUES(?,?,?,?)",
                (name, encoded, version, time.time()),
            )
            self._db.execute(
                f"CREATE TABLE {_table(name)} (id TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at REAL NOT NULL)"
            )

    def collection_info(self, name: str) -> dict[str, Any]:
        _check_name(name)
        row = self._db.execute(
            "SELECT name,schema_json,version,created_at FROM _iil_collections WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            raise DataCoreError(f"unknown collection: {name}")
        return {"name": row["name"], "schema": json.loads(row["schema_json"]),
                "version": row["version"], "created_at": row["created_at"]}

    def put(self, collection: str, document: dict[str, Any], document_id: str | None = None) -> str:
        info = self.collection_info(collection)
        if not isinstance(document, dict):
            raise DataCoreError("documents must be JSON objects")
        _validate_document(document, info["schema"])
        encoded = _json(document)
        if len(encoded.encode("utf-8")) > _MAX_DOCUMENT_BYTES:
            raise DataCoreError("document exceeds 1 MiB limit")
        key = document_id or str(uuid.uuid4())
        if not isinstance(key, str) or not key or len(key) > 128:
            raise DataCoreError("document id must be a non-empty string of at most 128 characters")
        with self._db:
            self._db.execute(
                f"INSERT INTO {_table(collection)}(id,body,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
                (key, encoded, time.time()),
            )
        return key

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        self.collection_info(collection)
        row = self._db.execute(
            f"SELECT body FROM {_table(collection)} WHERE id=?", (document_id,)
        ).fetchone()
        return json.loads(row["body"]) if row else None

    def delete(self, collection: str, document_id: str) -> bool:
        self.collection_info(collection)
        with self._db:
            cur = self._db.execute(f"DELETE FROM {_table(collection)} WHERE id=?", (document_id,))
        return cur.rowcount > 0

    def find_equal(self, collection: str, field: str, value: Any, limit: int = 100) -> list[dict[str, Any]]:
        """Find documents by a declared indexed top-level field."""
        info = self.collection_info(collection)
        if field not in info["schema"].get("indexes", []):
            raise SchemaError(f"field is not indexed: {field}")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise DataCoreError("limit must be between 1 and 1000")
        rows = self._db.execute(
            f"SELECT body FROM {_table(collection)} WHERE json_extract(body, ?) = ? LIMIT ?",
            (f"$.{field}", value, limit),
        ).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def create_index(self, collection: str, field: str) -> None:
        info = self.collection_info(collection)
        if field not in info["schema"].get("indexes", []):
            raise SchemaError("only fields declared in the collection schema may be indexed")
        index_name = f"idx_{collection}_{field}"
        self._db.execute(
            f"CREATE INDEX IF NOT EXISTS {_quote(index_name)} ON {_table(collection)} "
            f"(json_extract(body, '$.{field}'))"
        )
        self._db.commit()

    def list_collections(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT name,version FROM _iil_collections ORDER BY name").fetchall()
        return [{"name": r["name"], "version": r["version"]} for r in rows]

    def backup(self, destination: str | Path) -> str:
        """Create a consistent SQLite backup using SQLite's online backup API."""
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(str(target))
        try:
            self._db.backup(dest)
        finally:
            dest.close()
        return str(target)

    def integrity_check(self) -> dict[str, Any]:
        messages = [r[0] for r in self._db.execute("PRAGMA integrity_check").fetchall()]
        return {"ok": messages == ["ok"], "messages": messages}


class DataCore:
    """Small facade over a selected storage adapter."""
    def __init__(self, adapter: StorageAdapter) -> None:
        self.adapter = adapter
    def close(self) -> None:
        self.adapter.close()
    def health(self) -> dict[str, Any]:
        return self.adapter.health()
    def create_collection(self, name: str, schema: dict[str, Any], version: int = 1) -> None:
        self.adapter.create_collection(name, schema, version)
    def put(self, collection: str, document: dict[str, Any], document_id: str | None = None) -> str:
        return self.adapter.put(collection, document, document_id)
    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        return self.adapter.get(collection, document_id)
    def delete(self, collection: str, document_id: str) -> bool:
        return self.adapter.delete(collection, document_id)


def _check_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise SchemaError("names must start with a letter and contain only letters, digits or underscores")


def _table(name: str) -> str:
    _check_name(name)
    return _quote("docs_" + name)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _validate_schema(schema: dict[str, Any]) -> None:
    if not isinstance(schema, dict):
        raise SchemaError("schema must be a JSON object")
    fields, indexes = schema.get("fields", {}), schema.get("indexes", [])
    if not isinstance(fields, dict) or not isinstance(indexes, list):
        raise SchemaError("schema fields must be an object and indexes must be a list")
    for field, kind in fields.items():
        _check_name(field)
        if kind not in {"string", "number", "integer", "boolean", "object", "array", "any"}:
            raise SchemaError(f"unsupported field type for {field}")
    for field in indexes:
        _check_name(field)
        if field not in fields:
            raise SchemaError(f"indexed field is not declared: {field}")


def _validate_document(document: dict[str, Any], schema: dict[str, Any]) -> None:
    fields, required = schema.get("fields", {}), schema.get("required", [])
    if not isinstance(required, list) or any(k not in fields for k in required):
        raise SchemaError("required must list declared fields")
    missing = [key for key in required if key not in document]
    if missing:
        raise SchemaError("missing required fields: " + ", ".join(missing))
    for key, value in document.items():
        if key not in fields:
            if schema.get("additionalProperties", False) is not True:
                raise SchemaError(f"undeclared field: {key}")
            continue
        checks = {
            "string": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "any": lambda v: True,
        }
        if not checks[fields[key]](value):
            raise SchemaError(f"field {key} must be {fields[key]}")


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DataCoreError("value is not valid JSON") from exc
