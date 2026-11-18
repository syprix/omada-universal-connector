from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.spec_catalog import SpecCatalogError, load_spec


def fixture() -> dict[str, object]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Synthetic fixture", "version": "2.1"},
        "tags": [{"name": "Inventory"}, {"name": "Top Level"}],
        "paths": {
            "/items": {
                "get": {"operationId": "listItems", "tags": ["Inventory"], "responses": {"200": {"secretSchema": "private"}}},
                "post": {"operationId": "createItem", "tags": ["Changes"]},
            },
            "/items/{id}": {"get": {"operationId": "getItem"}},
        },
    }


class SpecCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_json(self, name: str = "spec.json", value: object | None = None) -> Path:
        path = self.root / name
        path.write_text(json.dumps(fixture() if value is None else value), encoding="utf-8")
        return path

    def test_json_catalog_exposes_only_redacted_documentation_summary(self) -> None:
        catalog = load_spec(self.write_json())
        summary = catalog.summary()
        self.assertEqual(summary["documented_status"], "documented_not_live_verified")
        self.assertEqual(summary["methods"], ["GET", "POST"])
        self.assertEqual(summary["get_read_candidate_count"], 2)
        self.assertEqual(summary["non_get_count"], 1)
        self.assertEqual(summary["tags"], ["Changes", "Inventory", "Top Level"])
        self.assertNotIn("paths", summary)
        self.assertNotIn("secretSchema", json.dumps(summary))
        self.assertNotIn(str(self.root), json.dumps(summary))
        self.assertEqual(len(summary["source_sha256"]), 64)

    def test_operations_keep_path_and_method_but_summary_does_not(self) -> None:
        catalog = load_spec(self.write_json())
        self.assertEqual(
            [(op.method, op.path, op.operation_id, op.read_candidate) for op in catalog.operations],
            [("GET", "/items", "listItems", True), ("GET", "/items/{id}", "getItem", True), ("POST", "/items", "createItem", False)],
        )

    def test_zip_reads_single_json_member_without_extraction(self) -> None:
        archive_path = self.root / "spec.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("nested/spec.json", json.dumps(fixture()))
            archive.writestr("readme.txt", "not parsed")
        catalog = load_spec(archive_path)
        self.assertEqual(catalog.info_version, "2.1")
        self.assertFalse((self.root / "nested").exists())

    def test_zip_requires_exactly_one_json_member(self) -> None:
        archive_path = self.root / "ambiguous.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("a.json", "{}")
            archive.writestr("b.JSON", "{}")
        with self.assertRaisesRegex(SpecCatalogError, "zip_json_member_count_invalid"):
            load_spec(archive_path)

    def test_size_limit_and_openapi_validation(self) -> None:
        path = self.write_json()
        with self.assertRaisesRegex(SpecCatalogError, "input_too_large"):
            load_spec(path, max_bytes=10)
        invalid = fixture()
        invalid["openapi"] = "2.0"
        with self.assertRaisesRegex(SpecCatalogError, "openapi_version_unsupported"):
            load_spec(self.write_json("bad.json", invalid))

    def test_missing_operation_id_is_rejected(self) -> None:
        invalid = fixture()
        invalid["paths"] = {"/items": {"get": {"responses": {}}}}
        with self.assertRaisesRegex(SpecCatalogError, "operation_id_invalid"):
            load_spec(self.write_json("bad.json", invalid))


if __name__ == "__main__":
    unittest.main()
