"""Small, offline catalog for user-supplied OpenAPI 3 JSON documents.

The input is treated only as data: it is never imported, evaluated, or used to
make network requests. Public summaries intentionally omit paths and schemas.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SpecCatalogError(ValueError):
    """A stable error for invalid or oversized specification input."""


_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
_SAFE_LABEL = re.compile(r"[^\w .:/+-]+", re.UNICODE)
_MAX_INPUT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    operation_id: str
    tags: tuple[str, ...]

    @property
    def read_candidate(self) -> bool:
        return self.method == "GET"


@dataclass(frozen=True)
class SpecCatalog:
    openapi_version: str
    info_version: str
    source_sha256: str
    tags: tuple[str, ...]
    operations: tuple[Operation, ...]

    def summary(self) -> dict[str, Any]:
        """Return safe aggregate metadata, without paths or raw schemas."""
        methods = sorted({op.method for op in self.operations})
        return {
            "documented_status": "documented_not_live_verified",
            "openapi_version": self.openapi_version,
            "openapi_document_version": self.info_version,
            "source_sha256": self.source_sha256,
            "tags": list(self.tags),
            "methods": methods,
            "operation_count": len(self.operations),
            "get_read_candidate_count": sum(op.read_candidate for op in self.operations),
            "non_get_count": sum(not op.read_candidate for op in self.operations),
        }


def load_spec(source: str | Path, *, max_bytes: int = _MAX_INPUT_BYTES) -> SpecCatalog:
    """Load a JSON spec directly or from a ZIP with exactly one .json member."""
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise SpecCatalogError("size_limit_invalid")
    path = Path(source)
    try:
        if path.stat().st_size > max_bytes:
            raise SpecCatalogError("input_too_large")
        if path.suffix.lower() == ".zip":
            raw = _read_zip(path, max_bytes)
        else:
            with path.open("rb") as stream:
                raw = stream.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise SpecCatalogError("input_too_large")
    except SpecCatalogError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise SpecCatalogError("input_unavailable") from exc
    return _parse_spec(raw)


def _read_zip(path: Path, max_bytes: int) -> bytes:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            json_entries = [entry for entry in entries if entry.filename.lower().endswith(".json")]
            if len(json_entries) != 1:
                raise SpecCatalogError("zip_json_member_count_invalid")
            entry = json_entries[0]
            if entry.flag_bits & 0x1 or entry.file_size > max_bytes:
                raise SpecCatalogError("zip_member_invalid")
            with archive.open(entry) as stream:
                raw = stream.read(max_bytes + 1)
            if len(raw) > max_bytes or len(raw) != entry.file_size:
                raise SpecCatalogError("input_too_large")
            return raw
    except SpecCatalogError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise SpecCatalogError("zip_invalid") from exc


def _parse_spec(raw: bytes) -> SpecCatalog:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecCatalogError("json_invalid") from exc
    if not isinstance(document, dict) or not isinstance(document.get("openapi"), str):
        raise SpecCatalogError("openapi_version_missing")
    openapi_version = document["openapi"]
    if not re.fullmatch(r"3\.\d+\.\d+", openapi_version):
        raise SpecCatalogError("openapi_version_unsupported")
    info = document.get("info")
    if not isinstance(info, dict) or not isinstance(info.get("version"), str):
        raise SpecCatalogError("info_version_missing")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise SpecCatalogError("paths_invalid")

    operation_by_identity: dict[tuple[str, str], Operation] = {}
    for route, path_item in paths.items():
        if not isinstance(route, str) or not route.startswith("/") or not isinstance(path_item, dict):
            raise SpecCatalogError("path_invalid")
        for raw_method, detail in path_item.items():
            method = raw_method.lower() if isinstance(raw_method, str) else ""
            if method not in _METHODS:
                continue  # Path parameters, servers, summaries, and extensions.
            if not isinstance(detail, dict):
                raise SpecCatalogError("operation_invalid")
            operation_id = detail.get("operationId")
            if not isinstance(operation_id, str) or not operation_id.strip():
                raise SpecCatalogError("operation_id_invalid")
            operation_tags = _labels(detail.get("tags", []))
            key = (method.upper(), route)
            operation_by_identity.setdefault(
                key, Operation(key[0], route, operation_id.strip(), operation_tags)
            )

    all_tags = set(_labels(document.get("tags", [])))
    for operation in operation_by_identity.values():
        all_tags.update(operation.tags)
    return SpecCatalog(
        openapi_version=openapi_version,
        info_version=_label(info["version"]),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        tags=tuple(sorted(all_tags)),
        operations=tuple(operation_by_identity[key] for key in sorted(operation_by_identity)),
    )


def _labels(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(sorted({label for label in (
        _label(item.get("name") if isinstance(item, dict) else item)
        for item in value
    ) if label}))


def _label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _SAFE_LABEL.sub("", value).strip()[:80]
