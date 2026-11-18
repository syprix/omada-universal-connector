from __future__ import annotations

import hashlib
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
from unittest.mock import patch

from tools import build_openapi_catalog as builder


class BuildOpenApiCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _archive_raw(self, family: str, raw: bytes, *, extra: dict[str, bytes] | None = None,
                     member_name: str | None = None, subdir: str = "") -> builder.SourceSpec:
        values = {item[0]: (item[1], item[2]) for item in builder.DEFAULT_SOURCES}
        archive_name, expected_member = values[family]
        directory = self.root / subdir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / archive_name
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(member_name or expected_member, raw)
            for name, data in (extra or {}).items():
                archive.writestr(name, data)
        return builder.SourceSpec(family, path, expected_member)

    def _source(self, family: str, paths: dict[str, object]) -> builder.SourceSpec:
        raw = json.dumps({
            "openapi": "3.0.1",
            "info": {"title": "private title to discard", "version": "0.1"},
            "servers": [{"url": "https://192.0.2.99/private-controller"}],
            "paths": paths,
            "components": {"schemas": {"PrivateSchema": {"secret": "omit"}}},
        }, separators=(",", ":")).encode()
        return self._archive_raw(family, raw)

    def _three_sources(self, path_sets: tuple[dict[str, object], ...] | None = None):
        if path_sets is None:
            path_sets = (
                {"/openapi/v1/{omadacId}/sites": {"get": {"operationId": "discard"}, "post": {}}},
                {"/openapi/v1/{omadacId}/sites": {"get": {}, "delete": {}},
                "/openapi/v1/{omadacId}/devices/{apMac}/health": {"get": {}}},
                {"/openapi/v1/{omadacId}/devices/{apMac}/health": {"get": {}},
                 "/openapi/v2/{controller}/health": {"get": {}}},
            )
        return [self._source(spec[0], paths)
                for spec, paths in zip(builder.DEFAULT_SOURCES, path_sets, strict=True)]

    def test_exact_method_path_dedupe_presence_and_metadata_only(self) -> None:
        sources = self._three_sources()
        catalog = builder.build_catalog(sources)
        self.assertEqual(catalog["catalog_scope"], "documentation_presence_only_not_runtime_support")
        self.assertFalse(catalog["catalog_grants_execution"])
        self.assertEqual(catalog["implementation_status_from_catalog"], "unknown")
        self.assertEqual(catalog["controller_support_status_from_catalog"], "unknown")
        self.assertEqual(catalog["live_status_from_catalog"], "unknown")
        rows = catalog["operations"]
        self.assertEqual(len(rows), 5)
        first = next(row for row in rows if row["method"] == "GET" and
                     row["path_template"] == "/openapi/v1/{omadacId}/sites")
        self.assertEqual(first["documented_in"], ["er7212pc-6.2.14", "hardware-controller-6.3.0"])
        self.assertEqual(set(first), {"method", "path_template", "documented_in"})
        self.assertTrue(all(set(row) == {"method", "path_template", "documented_in"} for row in rows))
        self.assertEqual(rows, sorted(rows, key=lambda row: (row["method"], row["path_template"])))

        rendered = builder.catalog_bytes(catalog).decode("ascii")
        for private in ("private title", "192.0.2.99", "private-controller", "PrivateSchema",
                        "operationId", "discard", "secret", "components", "servers"):
            self.assertNotIn(private, rendered)
        for source, row in zip(sorted(sources, key=lambda item: item.family), catalog["sources"], strict=True):
            raw = zipfile.ZipFile(source.archive_path).read(source.member_name)
            self.assertEqual(row["source_sha256"], hashlib.sha256(raw).hexdigest())

    def test_source_path_template_spellings_remain_distinct(self) -> None:
        path_sets = (
            {"/x/{siteId}/items/{itemId}": {"get": {}}},
            {"/x/{site_ref}/items/{item_ref}": {"get": {}}},
            {"/x/{siteId}/items/{itemId}": {"get": {}}},
        )
        catalog = builder.build_catalog(self._three_sources(path_sets))
        rows = [row for row in catalog["operations"] if row["path_template"].startswith("/x/")]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["documented_in"], ["er7212pc-6.2.14", "omada-cbc-standard-6.3.0"])
        self.assertEqual(rows[1]["documented_in"], ["hardware-controller-6.3.0"])

    def test_rejects_urls_queries_concrete_ids_and_malformed_templates(self) -> None:
        bad_paths = (
            "https://controller.example/openapi/v1/sites",
            "/openapi/v1/sites?token=private",
            "/openapi/v1/sites/0123456789abcdef01234567",
            "/openapi/v1/sites/aa:bb:cc:dd:ee:ff",
            "/openapi/v1/sites/aabb.ccdd.eeff",
            "/openapi/v1/sites/192.0.2.1",
            "/openapi/v1/sites/123",
            "/openapi/v1/{unterminated/sites",
            "/openapi/v1/sites/{id}/../devices",
            "/openapi//v1/sites",
            "/openapi/v1/sites/#fragment",
        )
        for path in bad_paths:
            with self.subTest(path=path):
                sources = self._three_sources((
                    {path: {"get": {}}}, {}, {},
                ))
                with self.assertRaisesRegex(builder.CatalogBuildError, "path_template_invalid"):
                    builder.build_catalog(sources)

    def test_ignores_path_item_metadata_but_does_not_accept_unknown_methods_as_operations(self) -> None:
        sources = self._three_sources((
            {"/safe/path": {"parameters": [{"name": "private"}],
                             "summary": "private text", "connect": {}, "get": {}}},
            {"/other": {"$ref": "#/components/paths/private", "get": {}}},
            {"/third": {"x-vendor-extension": {"value": "private"}, "get": {}}},
        ))
        catalog = builder.build_catalog(sources)
        self.assertEqual(catalog["operations"], [
            {"method": "GET", "path_template": "/other",
             "documented_in": ["hardware-controller-6.3.0"]},
            {"method": "GET", "path_template": "/safe/path",
             "documented_in": ["er7212pc-6.2.14"]},
            {"method": "GET", "path_template": "/third",
             "documented_in": ["omada-cbc-standard-6.3.0"]},
        ])
        rendered = builder.catalog_bytes(catalog).decode()
        self.assertNotIn("private", rendered)

    def test_rejects_bad_zip_member_count_name_duplicate_and_duplicate_json_keys(self) -> None:
        valid = json.dumps({"paths": {"/x": {"get": {}}}}).encode()
        extra_member = self._archive_raw("er7212pc-6.2.14", valid,
                                         extra={"unexpected.json": b"{}"}, subdir="bad-extra")
        bad_member = self._archive_raw("hardware-controller-6.3.0", valid,
                                       member_name="different.json", subdir="bad-name")
        duplicate_json_key = self._archive_raw(
            "omada-cbc-standard-6.3.0",
            b'{"paths":{"/x":{"get":{}},"/x":{"post":{}}}}', subdir="bad-duplicate")
        duplicate_member = self.root / "bad-duplicate-zip" / "ER7212PC_6.2.14.zip"
        duplicate_member.parent.mkdir(parents=True)
        expected_member = "ER7212PC_6.2.14.json"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate_member, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr(expected_member, valid)
                archive.writestr(expected_member, valid)
        duplicate_zip_source = builder.SourceSpec(
            "er7212pc-6.2.14", duplicate_member, expected_member)
        good_sources = self._three_sources()
        for source, code in ((extra_member, "zip_member_count_invalid"),
                             (bad_member, "zip_member_invalid"),
                             (duplicate_zip_source, "zip_member_count_invalid"),
                             (duplicate_json_key, "json_duplicate_key")):
            with self.subTest(code=code):
                sources = [source if item.family == source.family else item for item in good_sources]
                with self.assertRaisesRegex(builder.CatalogBuildError, code):
                    builder.build_catalog(sources)

    def test_oversized_json_and_operation_collections_fail_closed(self) -> None:
        sources = self._three_sources()
        oversized = self._archive_raw("er7212pc-6.2.14", b'{"paths":{"/x":{"get":{}}}}')
        with patch.object(builder, "MAX_JSON_BYTES", 8):
            with self.assertRaisesRegex(builder.CatalogBuildError, "zip_member_size_invalid"):
                builder.build_catalog([oversized, *sources[1:]])

        too_many_paths = {f"/path{i}": {"get": {}} for i in range(builder.MAX_PATHS_PER_SOURCE + 1)}
        with self.assertRaisesRegex(builder.CatalogBuildError, "paths_invalid"):
            builder.build_catalog(self._three_sources((too_many_paths, {}, {})))

        with patch.object(builder, "MAX_OPERATIONS_PER_SOURCE", 1):
            with self.assertRaisesRegex(builder.CatalogBuildError, "operation_count_exceeded"):
                builder.build_catalog(self._three_sources((
                    {"/one": {"get": {}, "post": {}}},
                    {"/two": {"get": {}}},
                    {"/three": {"get": {}}},
                )))

        with patch.object(builder, "MAX_ARCHIVE_BYTES", 8):
            with self.assertRaisesRegex(builder.CatalogBuildError, "archive_size_invalid"):
                builder.build_catalog(self._three_sources())

    def test_catalog_serialization_is_reproducible_and_write_can_be_checked_or_backed_up(self) -> None:
        catalog = builder.build_catalog(self._three_sources())
        first = builder.catalog_bytes(catalog)
        second = builder.catalog_bytes(builder.build_catalog(self._three_sources()))
        self.assertEqual(first, second)
        output = self.root / "catalog.json"
        output.write_bytes(b"old catalog\n")
        backup = self.root / "backup" / "catalog.before.json"
        builder.write_catalog(output, catalog, backup=backup)
        self.assertEqual(backup.read_bytes(), b"old catalog\n")
        self.assertEqual(output.read_bytes(), first)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with patch.object(builder, "MAX_OUTPUT_BYTES", 1):
            with self.assertRaisesRegex(builder.CatalogBuildError, "catalog_output_too_large"):
                builder.catalog_bytes(catalog)

        old = output.read_bytes()
        self.assertEqual(output.read_bytes(), old)

    def test_cli_generation_is_idempotent_and_check_mode_never_writes(self) -> None:
        sources = self._three_sources()
        trusted = {
            source.family: hashlib.sha256(
                zipfile.ZipFile(source.archive_path).read(source.member_name)).hexdigest()
            for source in sources
        }
        output = self.root / "generated" / "catalog.json"
        base = ["--source-dir", str(self.root), "--output", str(output)]
        with patch.object(builder, "TRUSTED_SOURCE_SHA256", trusted), redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(base), 0)
        generated = output.read_bytes()
        with patch.object(builder, "TRUSTED_SOURCE_SHA256", trusted), redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(base + ["--check"]), 0)
        self.assertEqual(output.read_bytes(), generated)

        output.write_bytes(b"manual previous version")
        previous = output.read_bytes()
        with patch.object(builder, "TRUSTED_SOURCE_SHA256", trusted), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(builder.main(base + ["--check"]), 2)
        self.assertEqual(output.read_bytes(), previous)

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(builder.main(base), 2)
        self.assertEqual(output.read_bytes(), previous)

    def test_production_source_hash_allowlist_rejects_modified_export(self) -> None:
        sources = self._three_sources()
        with self.assertRaisesRegex(builder.CatalogBuildError, "source_hash_unrecognized"):
            builder.build_catalog(sources, expected_sha256=builder.TRUSTED_SOURCE_SHA256)

    def test_destinations_cannot_alias_input_via_path_symlink_or_hardlink(self) -> None:
        source = self._three_sources()[0].archive_path
        with self.assertRaisesRegex(builder.CatalogBuildError, "output_conflicts_with_input"):
            builder.validate_destinations(source, None, [source])

        symlink = self.root / "output-symlink.zip"
        symlink.symlink_to(source)
        with self.assertRaisesRegex(builder.CatalogBuildError, "output_conflicts_with_input"):
            builder.validate_destinations(symlink, None, [source])

        hardlink = self.root / "output-hardlink.zip"
        os.link(source, hardlink)
        with self.assertRaisesRegex(builder.CatalogBuildError, "output_conflicts_with_input"):
            builder.validate_destinations(hardlink, None, [source])

        backup_link = self.root / "backup-input.zip"
        backup_link.symlink_to(source)
        with self.assertRaisesRegex(builder.CatalogBuildError, "output_conflicts_with_input"):
            builder.validate_destinations(self.root / "out.json", backup_link, [source])
        with self.assertRaisesRegex(builder.CatalogBuildError, "output_backup_conflict"):
            builder.validate_destinations(self.root / "out.json", self.root / "nested" / ".." / "out.json", [])

    def test_backup_size_is_bounded_before_copy(self) -> None:
        catalog = builder.build_catalog(self._three_sources())
        output = self.root / "too-large-old.json"
        output.write_bytes(b"x" * (builder.MAX_BACKUP_BYTES + 1))
        backup = self.root / "backup.json"
        with self.assertRaisesRegex(builder.CatalogBuildError, "backup_too_large"):
            builder.write_catalog(output, catalog, backup=backup)
        self.assertFalse(backup.exists())

    def test_zip_member_count_is_rejected_before_infolist_materializes_entries(self) -> None:
        source = self._archive_raw(
            "er7212pc-6.2.14", b'{"paths":{"/x":{"get":{}}}}',
            extra={"another.json": b"{}"}, subdir="many-members")
        with patch.object(zipfile.ZipFile, "infolist", side_effect=AssertionError("must not parse central directory")):
            with self.assertRaisesRegex(builder.CatalogBuildError, "zip_member_count_invalid"):
                builder.build_catalog([source, *self._three_sources()[1:]])

    def test_cli_check_bounds_existing_output_before_read(self) -> None:
        sources = self._three_sources()
        trusted = {
            source.family: hashlib.sha256(
                zipfile.ZipFile(source.archive_path).read(source.member_name)).hexdigest()
            for source in sources
        }
        output = self.root / "huge.json"
        with output.open("wb") as stream:
            stream.truncate(builder.MAX_OUTPUT_BYTES + 1)
        base = ["--source-dir", str(self.root), "--output", str(output), "--check"]
        with patch.object(builder, "TRUSTED_SOURCE_SHA256", trusted), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(builder.main(base), 2)
        self.assertIn("output_too_large", err.getvalue())
        self.assertEqual(output.stat().st_size, builder.MAX_OUTPUT_BYTES + 1)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFO support")
    def test_source_and_bounded_output_reads_reject_fifo_without_blocking(self) -> None:
        fifo_dir = self.root / "fifo-source"
        fifo_dir.mkdir()
        fifo = fifo_dir / "ER7212PC_6.2.14.zip"
        os.mkfifo(fifo)
        source = builder.SourceSpec(
            "er7212pc-6.2.14", fifo, "ER7212PC_6.2.14.json")
        with self.assertRaisesRegex(builder.CatalogBuildError, "source_unavailable"):
            builder.build_catalog([source, *self._three_sources()[1:]])
        with self.assertRaisesRegex(builder.CatalogBuildError, "output_unavailable"):
            builder._read_bounded(fifo, 100, "output_too_large")

    def test_source_and_bounded_output_reads_reject_symlinks(self) -> None:
        source = self._three_sources()[0]
        link_dir = self.root / "linked-source"
        link_dir.mkdir()
        link = link_dir / "ER7212PC_6.2.14.zip"
        link.symlink_to(source.archive_path)
        linked_spec = builder.SourceSpec(source.family, link, source.member_name)
        with self.assertRaisesRegex(builder.CatalogBuildError, "source_unavailable"):
            builder.build_catalog([linked_spec, *self._three_sources()[1:]])
        with self.assertRaisesRegex(builder.CatalogBuildError, "output_unavailable"):
            builder._read_bounded(link, 100_000, "output_too_large")

    def test_zip_preflight_and_reader_share_one_open_file_reference(self) -> None:
        original = self._archive_raw(
            "er7212pc-6.2.14", b'{"paths":{"/original":{"get":{}}}}', subdir="same-fd")
        replacement_path = self.root / "replacement.zip"
        with zipfile.ZipFile(replacement_path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(original.member_name, b'{"paths":{"/replacement":{"get":{}}}}')
        preflight = builder._preflight_zip

        replaced = False
        def replace_after_preflight(stream, size):
            nonlocal replaced
            preflight(stream, size)
            if not replaced:
                replacement_path.replace(original.archive_path)
                replaced = True

        with patch.object(builder, "_preflight_zip", side_effect=replace_after_preflight):
            catalog = builder.build_catalog([original, *self._three_sources()[1:]])
        paths = {row["path_template"] for row in catalog["operations"]}
        self.assertIn("/original", paths)
        self.assertNotIn("/replacement", paths)

    def test_source_family_set_and_identity_are_fixed(self) -> None:
        sources = self._three_sources()
        with self.assertRaisesRegex(builder.CatalogBuildError, "source_set_invalid"):
            builder.build_catalog(sources[:2])
        wrong = builder.SourceSpec("er7212pc-6.2.14", sources[0].archive_path, "other.json")
        with self.assertRaisesRegex(builder.CatalogBuildError, "source_identity_invalid"):
            builder.build_catalog([wrong, *sources[1:]])


if __name__ == "__main__":
    unittest.main()
