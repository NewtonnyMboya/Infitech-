# INFILINK DataCore

DataCore is the storage and retrieval layer for INFILINK. This milestone provides a working SQLite reference adapter and a small adapter contract. It is not a claim of distributed replication or universal database connectivity.

## Quick start

```python
from runtime.python.datacore import DataCore, SQLiteAdapter

db = DataCore(SQLiteAdapter("infilink.db"))
db.create_collection("customers", {"fields": {"name": "string", "email": "string"}, "required": ["name"], "indexes": ["email"]})
customer_id = db.put("customers", {"name": "Ada", "email": "ada@example.test"})
customer = db.get("customers", customer_id)
db.close()
```

Run tests from the `infilink/` directory:

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Current capabilities

- SQLite local persistence and explicit adapter contract.
- JSON object documents with a 1 MiB per-document bound.
- Versioned collection metadata; incompatible schema changes require an explicit migration.
- Required fields, declared field types and optional additional properties.
- Declared top-level indexes and bounded equality lookup.
- Transactions for writes, SQLite online backup and integrity checks.
- Parameterized values and validated identifiers.

## Adapter roadmap

PostgreSQL, object/blob storage, graph databases, vector indexes and remote document stores can be implemented as separate `StorageAdapter` implementations. They are not connected by this reference implementation. Replication, conflict resolution, distributed transactions, encryption-at-rest policy and automated migrations remain future work requiring backend-specific design and operational testing.

Never expose a database file or adapter directly to untrusted clients. Put access behind authenticated, authorized service handlers and TLS transport.
