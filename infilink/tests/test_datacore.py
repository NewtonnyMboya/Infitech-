import tempfile
import unittest
from pathlib import Path

from datacore import DataCore, DataCoreError, SchemaError, SQLiteAdapter

SCHEMA = {"fields": {"name": "string", "age": "integer"},
          "required": ["name"], "indexes": ["name"]}


class DataCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.adapter = SQLiteAdapter(Path(self.temp.name) / "data.sqlite")
        self.core = DataCore(self.adapter)
        self.core.create_collection("people", SCHEMA)

    def tearDown(self):
        self.core.close()
        self.temp.cleanup()

    def test_crud_and_update(self):
        key = self.core.put("people", {"name": "Ada", "age": 36}, "ada")
        self.assertEqual(self.core.get("people", key)["name"], "Ada")
        self.core.put("people", {"name": "Ada Lovelace"}, key)
        self.assertEqual(self.core.get("people", key), {"name": "Ada Lovelace"})
        self.assertTrue(self.core.delete("people", key))
        self.assertIsNone(self.core.get("people", key))

    def test_schema_validation(self):
        with self.assertRaises(SchemaError):
            self.core.put("people", {"age": "thirty"})
        with self.assertRaises(SchemaError):
            self.core.put("people", {"name": "Ada", "unknown": 1})

    def test_indexed_lookup(self):
        self.core.adapter.create_index("people", "name")
        self.core.put("people", {"name": "Ada", "age": 36}, "a")
        self.core.put("people", {"name": "Grace", "age": 85}, "g")
        self.assertEqual(self.core.adapter.find_equal("people", "name", "Ada")[0]["age"], 36)
        with self.assertRaises(SchemaError):
            self.core.adapter.find_equal("people", "age", 36)

    def test_schema_version_conflict(self):
        with self.assertRaises(SchemaError):
            self.core.create_collection("people", SCHEMA, version=2)

    def test_backup_and_integrity(self):
        self.core.put("people", {"name": "Backup"}, "b")
        backup = Path(self.temp.name) / "backup.sqlite"
        self.core.adapter.backup(backup)
        restored = SQLiteAdapter(backup)
        try:
            self.assertEqual(restored.get("people", "b")["name"], "Backup")
            self.assertTrue(restored.integrity_check()["ok"])
        finally:
            restored.close()

    def test_reject_nan(self):
        with self.assertRaises(DataCoreError):
            self.core.put("people", {"name": "bad", "age": float("nan")})


if __name__ == "__main__":
    unittest.main()
