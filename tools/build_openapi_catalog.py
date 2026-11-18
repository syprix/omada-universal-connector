#!/usr/bin/env python3
"""Build an inert, offline method/path catalog from the three supplied ZIPs.

Only OpenAPI ``paths`` keys and standard HTTP method names are retained. No
schema, description, example, server URL, credential, or response is copied.
The generated catalog is documentation metadata and is never used for routing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import stat
import sys
import tempfile
import zipfile
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, BinaryIO, Iterator


SCHEMA_REVISION = 1
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_JSON_BYTES = 24 * 1024 * 1024
MAX_ZIP_MEMBERS = 1
MAX_CENTRAL_DIRECTORY_BYTES = 4096
MAX_PATHS_PER_SOURCE = 5000
MAX_OPERATIONS_PER_SOURCE = 5000
MAX_UNIQUE_OPERATIONS = 8000
MAX_PATH_LENGTH = 512
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_BACKUP_BYTES = MAX_OUTPUT_BYTES
MAX_COMPRESSION_RATIO = 100
ALLOWED_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
_PARAM = re.compile(r"\{([A-Za-z][A-Za-z0-9_]{0,63})\}")
_UUID = re.compile(r"(?i)[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_MAC = re.compile(r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\Z")
_MAC_DOTTED = re.compile(r"(?i)(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}\Z")
_IPV4 = re.compile(r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}\Z")
_STATIC_SEGMENT = re.compile(r"[A-Za-z0-9._~-]{1,96}\Z")
_EOCD = struct.Struct("<4s4H2LH")
_EOCD_SIGNATURE = b"PK\x05\x06"
_EOCD_SEARCH_BYTES = 22 + 65_535


class CatalogBuildError(ValueError):
    """Stable, non-sensitive generator failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SourceSpec:
    family: str
    archive_path: Path
    member_name: str


DEFAULT_SOURCES = (
    ("er7212pc-6.2.14", "ER7212PC_6.2.14.zip", "ER7212PC_6.2.14.json"),
    ("hardware-controller-6.3.0", "Hardware_Controller_6.3.0.zip", "Hardware_Controller_6.3.0.json"),
    ("omada-cbc-standard-6.3.0", "Omada_CBC_Standard_6.3.0.zip", "Omada_CBC_Standard_6.3.0.json"),
)

# These hashes identify only the three reviewed local source snapshots. The
# public CLI refuses changed archives; synthetic tests call build_catalog
# without this production-only binding.
TRUSTED_SOURCE_SHA256 = {
    "er7212pc-6.2.14": "25a044099a4621594d7568fb90a775330436990a7db51c33fb112301c2442a00",
    "hardware-controller-6.3.0": "3a6ec3a9741839ba06de3f11df3d6d67ddd3ac702fd98dce286b0268dc0a8f44",
    "omada-cbc-standard-6.3.0": "15e5101bcb31437569735fde06b964b988538445782bada4fa4fb9fbea951063",
}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogBuildError("json_duplicate_key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise CatalogBuildError("json_nonfinite_constant")


def _valid_path_template(path: object) -> str:
    if (not isinstance(path, str) or not path.startswith("/") or
            len(path) > MAX_PATH_LENGTH or path.startswith("//") or
            any(ord(char) < 0x21 or ord(char) > 0x7e for char in path) or
            any(char in path for char in ("?", "#", "\\", "%", "@"))):
        raise CatalogBuildError("path_template_invalid")
    segments = path.split("/")[1:]
    if not segments or any(not segment for segment in segments):
        raise CatalogBuildError("path_template_invalid")
    seen_params: set[str] = set()
    for segment in segments:
        param = _PARAM.fullmatch(segment)
        if param:
            name = param.group(1)
            if name in seen_params:
                raise CatalogBuildError("path_template_invalid")
            seen_params.add(name)
            continue
        if ("{" in segment or "}" in segment or not _STATIC_SEGMENT.fullmatch(segment) or
                segment in {".", ".."} or _UUID.fullmatch(segment) or
                _MAC.fullmatch(segment) or _MAC_DOTTED.fullmatch(segment) or _IPV4.fullmatch(segment) or
                (segment.isdecimal() and not re.fullmatch(r"v[1-9][0-9]*", segment, re.I)) or
                (len(segment) >= 12 and re.fullmatch(r"[0-9a-fA-F]+", segment))):
            raise CatalogBuildError("path_template_invalid")
    return path


def _read_spec(source: SourceSpec) -> tuple[bytes, dict[str, Any]]:
    try:
        with _open_regular_file(source.archive_path, "source_unavailable") as stream:
            archive_size = os.fstat(stream.fileno()).st_size
            if archive_size <= 0 or archive_size > MAX_ARCHIVE_BYTES:
                raise CatalogBuildError("archive_size_invalid")
            _preflight_zip(stream, archive_size)
            try:
                with zipfile.ZipFile(stream, "r") as archive:
                    infos = archive.infolist()
                    names = [info.filename for info in infos]
                    if len(names) != len(set(names)):
                        raise CatalogBuildError("zip_duplicate_member")
                    if not 1 <= len(infos) <= MAX_ZIP_MEMBERS:
                        raise CatalogBuildError("zip_member_count_invalid")
                    files = [info for info in infos if not info.is_dir()]
                    if len(files) != 1 or files[0].filename != source.member_name:
                        raise CatalogBuildError("zip_member_invalid")
                    info = files[0]
                    if (info.flag_bits & 0x1 or info.file_size <= 0 or info.file_size > MAX_JSON_BYTES or
                            info.compress_size <= 0 or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO):
                        raise CatalogBuildError("zip_member_size_invalid")
                    with archive.open(info, "r") as member:
                        raw = member.read(MAX_JSON_BYTES + 1)
                        if len(raw) <= MAX_JSON_BYTES and member.read(1):
                            raw += b"x"
            except CatalogBuildError:
                raise
            except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError):
                raise CatalogBuildError("zip_invalid") from None
    except CatalogBuildError:
        raise
    except OSError:
        raise CatalogBuildError("source_unavailable") from None
    if len(raw) != info.file_size or len(raw) > MAX_JSON_BYTES:
        raise CatalogBuildError("zip_member_size_invalid")
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"),
                              object_pairs_hook=_reject_duplicate_keys,
                              parse_constant=_reject_constant)
    except CatalogBuildError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise CatalogBuildError("json_invalid") from None
    if not isinstance(document, dict):
        raise CatalogBuildError("document_invalid")
    return raw, document


def _preflight_zip(stream: BinaryIO, archive_size: int) -> None:
    """Bound the central-directory member count before ZipFile materializes it.

    This accepts the ordinary single-disk, non-Zip64 archives supplied for the
    project. The archive size and tail read are bounded before `infolist()`.
    """
    try:
        tail_size = min(archive_size, _EOCD_SEARCH_BYTES)
        stream.seek(archive_size - tail_size)
        tail = stream.read(tail_size)
    except OSError:
        raise CatalogBuildError("zip_invalid") from None
    offset = tail.rfind(_EOCD_SIGNATURE)
    base_offset = archive_size - len(tail)
    while offset >= 0:
        if offset + _EOCD.size <= len(tail):
            fields = _EOCD.unpack_from(tail, offset)
            (signature, disk_number, central_disk, disk_entries, total_entries,
             central_size, central_offset, comment_length) = fields
            if (signature == _EOCD_SIGNATURE and
                    offset + _EOCD.size + comment_length == len(tail)):
                eocd_absolute = base_offset + offset
                if (disk_number != 0 or central_disk != 0 or disk_entries != total_entries or
                        total_entries == 0xFFFF or central_size == 0xFFFFFFFF or
                        central_offset == 0xFFFFFFFF or central_offset + central_size != eocd_absolute):
                    raise CatalogBuildError("zip_format_unsupported")
                if central_size > MAX_CENTRAL_DIRECTORY_BYTES:
                    raise CatalogBuildError("zip_central_directory_too_large")
                if total_entries != MAX_ZIP_MEMBERS:
                    raise CatalogBuildError("zip_member_count_invalid")
                return
        offset = tail.rfind(_EOCD_SIGNATURE, 0, offset)
    raise CatalogBuildError("zip_invalid")


def _operations_for_source(document: object) -> list[tuple[str, str]]:
    if not isinstance(document, dict):
        raise CatalogBuildError("document_invalid")
    paths = document.get("paths")
    if not isinstance(paths, dict) or not 1 <= len(paths) <= MAX_PATHS_PER_SOURCE:
        raise CatalogBuildError("paths_invalid")
    operations: set[tuple[str, str]] = set()
    count = 0
    for raw_path, item in paths.items():
        path = _valid_path_template(raw_path)
        if not isinstance(item, dict):
            raise CatalogBuildError("path_item_invalid")
        for raw_method, operation in item.items():
            if raw_method not in ALLOWED_METHODS:
                continue  # OpenAPI path-item metadata is not an operation.
            if not isinstance(operation, dict):
                raise CatalogBuildError("operation_invalid")
            count += 1
            if count > MAX_OPERATIONS_PER_SOURCE:
                raise CatalogBuildError("operation_count_exceeded")
            operations.add((raw_method.upper(), path))
    if not operations:
        raise CatalogBuildError("operations_empty")
    return sorted(operations)


def build_catalog(sources: Iterable[SourceSpec], *,
                 expected_sha256: dict[str, str] | None = None) -> dict[str, object]:
    """Build the reduced catalog from exactly the three known source families."""
    specs = tuple(sources)
    expected = {family: (archive, member) for family, archive, member in DEFAULT_SOURCES}
    if len(specs) != len(expected) or {item.family for item in specs} != set(expected):
        raise CatalogBuildError("source_set_invalid")
    if len({item.family for item in specs}) != len(specs):
        raise CatalogBuildError("source_set_invalid")
    if expected_sha256 is not None and (
            not isinstance(expected_sha256, dict) or set(expected_sha256) != set(expected) or
            any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in expected_sha256.values())):
        raise CatalogBuildError("trusted_source_hashes_invalid")

    entries: dict[tuple[str, str], list[str]] = {}
    source_rows: list[dict[str, object]] = []
    for source in sorted(specs, key=lambda item: item.family):
        expected_archive, expected_member = expected[source.family]
        if (source.archive_path.name != expected_archive or source.member_name != expected_member):
            raise CatalogBuildError("source_identity_invalid")
        raw, document = _read_spec(source)
        source_digest = hashlib.sha256(raw).hexdigest()
        if expected_sha256 is not None and source_digest != expected_sha256[source.family]:
            raise CatalogBuildError("source_hash_unrecognized")
        operations = _operations_for_source(document)
        if len(entries) + len(operations) > MAX_UNIQUE_OPERATIONS:
            # This conservative pre-check avoids large intermediate catalogs;
            # exact duplicates may therefore cause a fail-closed rejection.
            raise CatalogBuildError("catalog_operation_count_exceeded")
        for method, path in operations:
            entries.setdefault((method, path), []).append(source.family)
        source_rows.append({
            "family": source.family,
            "source_sha256": source_digest,
            "documented_operation_count": len(operations),
        })

    if len(entries) > MAX_UNIQUE_OPERATIONS:
        raise CatalogBuildError("catalog_operation_count_exceeded")
    operations = [
        {
            "method": method,
            "path_template": path,
            "documented_in": sorted(families),
        }
        for (method, path), families in sorted(entries.items())
    ]
    return {
        "schema_revision": SCHEMA_REVISION,
        "catalog_scope": "documentation_presence_only_not_runtime_support",
        "legacy_full_matrix_note": (
            "tools/full_api_matrix.py is a broader legacy report; this reduced catalog "
            "is generated directly from the pinned local exports and does not inherit its status claims."
        ),
        "catalog_grants_execution": False,
        "implementation_status_from_catalog": "unknown",
        "controller_support_status_from_catalog": "unknown",
        "live_status_from_catalog": "unknown",
        "sources": source_rows,
        "operations": operations,
    }


def catalog_bytes(catalog: dict[str, object]) -> bytes:
    try:
        data = (json.dumps(catalog, ensure_ascii=True, sort_keys=True, indent=2,
                           separators=(",", ": "), allow_nan=False) + "\n").encode("ascii")
    except (TypeError, ValueError):
        raise CatalogBuildError("catalog_serialization_invalid") from None
    if len(data) > MAX_OUTPUT_BYTES:
        raise CatalogBuildError("catalog_output_too_large")
    return data


def _resolve_path(path: Path) -> Path:
    try:
        return Path(path).resolve(strict=False)
    except (OSError, RuntimeError):
        raise CatalogBuildError("output_path_invalid") from None


def _same_file(left: Path, right: Path) -> bool:
    if _resolve_path(left) == _resolve_path(right):
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def validate_destinations(output: Path, backup: Path | None,
                          protected_inputs: Iterable[Path]) -> None:
    """Reject output/backup paths aliasing any input by path, symlink, or hardlink."""
    output = Path(output)
    backup = Path(backup) if backup is not None else None
    inputs = tuple(Path(item) for item in protected_inputs)
    if backup is not None and _same_file(output, backup):
        raise CatalogBuildError("output_backup_conflict")
    for destination in (output, backup):
        if destination is None:
            continue
        for source in inputs:
            if _same_file(destination, source):
                raise CatalogBuildError("output_conflicts_with_input")


def write_catalog(output: Path, catalog: dict[str, object], *, backup: Path | None = None,
                  protected_inputs: Iterable[Path] = ()) -> None:
    """Atomically write output; optional explicit backup preserves prior bytes."""
    output = Path(output)
    validate_destinations(output, backup, protected_inputs)
    payload = catalog_bytes(catalog)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        if backup is not None and output.exists():
            backup = Path(backup)
            prior_bytes = _read_bounded(output, MAX_BACKUP_BYTES, "backup_too_large")
            backup.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(backup, prior_bytes)
        _atomic_write(output, payload)
    except CatalogBuildError:
        raise
    except OSError:
        raise CatalogBuildError("output_write_failed") from None


def _atomic_write(path: Path, payload: bytes) -> None:
    fd = -1
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        temp_name = None
        _fsync_directory(path.parent)
    except OSError:
        raise
    finally:
        if fd >= 0:
            os.close(fd)
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _fsync_directory(directory: Path) -> None:
    """Attempt directory fsync after atomic rename; unsupported filesystems may skip it."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        directory_fd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    except OSError:
        # Some filesystems/platforms do not allow fsync on directory handles.
        pass
    finally:
        os.close(directory_fd)


@contextmanager
def _open_regular_file(path: Path, failure_code: str) -> Iterator[BinaryIO]:
    """Open without blocking on FIFOs and reject symlinks/non-regular files."""
    fd = -1
    try:
        if not hasattr(os, "O_NONBLOCK") or not hasattr(os, "O_NOFOLLOW"):
            raise CatalogBuildError(failure_code)
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        fd = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise CatalogBuildError(failure_code)
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            yield stream
    except CatalogBuildError:
        raise
    except OSError:
        raise CatalogBuildError(failure_code) from None
    finally:
        if fd >= 0:
            os.close(fd)


def _read_bounded(path: Path, limit: int, too_large_code: str) -> bytes:
    """Read a regular, non-symlink file by one descriptor, at most limit+1 bytes."""
    try:
        with _open_regular_file(path, "output_unavailable") as stream:
            if os.fstat(stream.fileno()).st_size > limit:
                raise CatalogBuildError(too_large_code)
            data = stream.read(limit + 1)
    except CatalogBuildError:
        raise
    if len(data) > limit:
        raise CatalogBuildError(too_large_code)
    return data


def default_source_specs(source_dir: Path) -> tuple[SourceSpec, ...]:
    return tuple(SourceSpec(family, source_dir / archive, member)
                 for family, archive, member in DEFAULT_SOURCES)


def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=repo.parent,
                        help="directory containing the three supplied ZIP exports")
    parser.add_argument("--output", type=Path, default=repo / "docs" / "OPENAPI_ROUTE_CATALOG.json")
    parser.add_argument("--backup", type=Path,
                        help="optional explicit path for an atomic backup of an existing output")
    parser.add_argument("--check", action="store_true",
                        help="compare generated bytes to output without writing")
    args = parser.parse_args(argv)
    try:
        sources = default_source_specs(args.source_dir)
        input_paths = tuple(source.archive_path for source in sources)
        validate_destinations(args.output, args.backup, input_paths)
        catalog = build_catalog(sources, expected_sha256=TRUSTED_SOURCE_SHA256)
        payload = catalog_bytes(catalog)
        if args.check:
            current = _read_bounded(args.output, MAX_OUTPUT_BYTES, "output_too_large")
            if current != payload:
                raise CatalogBuildError("output_not_current")
        else:
            write_catalog(args.output, catalog, backup=args.backup,
                          protected_inputs=input_paths)
    except CatalogBuildError as exc:
        print(f"catalog build failed: {exc.code}", file=sys.stderr)
        return 2
    print(f"catalog operations={len(catalog['operations'])} output_bytes={len(payload)}")
    for source in catalog["sources"]:
        print(f"{source['family']}: documented_operations={source['documented_operation_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
