#!/usr/bin/env python3
"""Build a per-operation evidence ledger from the reduced route catalog.

The catalog contains only method/path/source presence. This report adds static
connector-map and test-reference hints; it does not certify behavior, tests,
schemas, or live support.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _canonical(method: str, path: str) -> tuple[str, str]:
    if not isinstance(method, str) or not isinstance(path, str):
        raise ValueError("invalid operation identity")
    normalized = re.sub(r"\{[^{}]+\}", "{}", path)
    return method.upper(), normalized


def build_report(
    catalog: dict[str, Any],
    *,
    source_map: dict[tuple[str, str], str],
    registry_entries: tuple[Any, ...],
    test_root: Path,
    catalog_sha256: str,
    auxiliary_source_operations: dict[tuple[str, str], tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if catalog.get("catalog_scope") != "documentation_presence_only_not_runtime_support":
        raise ValueError("catalog scope is not recognized")
    raw_operations = catalog.get("operations")
    if not isinstance(raw_operations, list):
        raise ValueError("catalog operations are missing")

    registry: dict[tuple[str, str], list[Any]] = {}
    for entry in registry_entries:
        key = _canonical(entry.upstream_method, entry.upstream_template)
        registry.setdefault(key, []).append(entry)

    tests: list[tuple[str, str]] = []
    auxiliary_source_operations = {
        _canonical(method, path): value
        for (method, path), value in (auxiliary_source_operations or {}).items()
    }
    if test_root.exists():
        for path in sorted(test_root.glob("test_*.py")):
            try:
                body = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            tests.append((path.name, body))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_operations:
        if not isinstance(raw, dict):
            raise ValueError("invalid operation catalog row")
        method, path = raw.get("method"), raw.get("path_template")
        key = _canonical(method, path)
        if key in seen:
            raise ValueError("duplicate normalized catalog operation")
        seen.add(key)
        sources = raw.get("documented_in")
        if not isinstance(sources, list) or any(not isinstance(item, str) for item in sources):
            raise ValueError("invalid documented source list")

        entries = registry.get(key, [])
        auxiliary = auxiliary_source_operations.get(key)
        mapped = source_map.get(key)
        if entries or auxiliary:
            implementation_evidence = "fixed_get_registry_route"
        elif mapped is not None:
            implementation_evidence = "manual_source_map_only"
        else:
            implementation_evidence = "not_mapped"

        references: list[str] = []
        if entries or auxiliary:
            # Operation ids are often asserted directly in adapter/registry
            # tests. Projection/client tests instead exercise the public
            # `read_<operation_id>` method without repeating that id as text.
            # Match both forms so the ledger does not hide function-specific
            # tests merely because they test behavior through the client API.
            needles = [
                re.compile(rf"\b{re.escape(name)}\b")
                for entry in entries
                for name in (entry.operation_id, f"read_{entry.operation_id}")
            ]
            if auxiliary:
                needles.extend(re.compile(rf"\b{re.escape(name)}\b")
                               for name in (auxiliary[0], f"read_{auxiliary[0]}"))
            references = [name for name, body in tests if any(needle.search(body) for needle in needles)]

        rows.append({
            "method": method.upper(),
            "path_template": path,
            "documented_in": sorted(set(sources)),
            "connector_evidence": implementation_evidence,
            "operation_ids": sorted({entry.operation_id for entry in entries} |
                                     ({auxiliary[0]} if auxiliary else set())),
            "public_templates": sorted({entry.public_template for entry in entries} |
                                        ({auxiliary[1]} if auxiliary else set())),
            "source_map_label": mapped if mapped is not None else None,
            "static_test_references": references,
            "test_execution": "not_assessed_by_this_report",
            "schema_review": "not_assessed_by_reduced_catalog",
            "function_verified": False,
            "live_status": "not_assessed_by_this_report",
        })

    rows.sort(key=lambda row: (row["method"], row["path_template"].casefold(), row["path_template"]))
    counts: dict[str, int] = {}
    for row in rows:
        label = row["connector_evidence"]
        counts[label] = counts.get(label, 0) + 1
    return {
        "scope": "per_operation_evidence_hints_not_function_verification",
        "catalog_sha256": catalog_sha256,
        "operation_count": len(rows),
        "connector_evidence_counts": counts,
        "function_verification_performed": False,
        "test_execution_performed": False,
        "live_checks_performed": False,
        "operations": rows,
    }

AUXILIARY_SOURCE_OPERATIONS = {
    ("GET", "/openapi/v1/{controller_id}/upgrade/overview/try-beta/channel"):
        ("controller_try_beta_settings_summary",
         "/v1/controller/firmware-preview-settings/summary"),
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/ports/switch-detail"):
        ("site_agile_switch_general_config_summary",
         "/v1/sites/{site_ref}/switches/{switch_ref}/agile-general-config-summary"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "docs/OPENAPI_ROUTE_CATALOG.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/OPERATION_EVIDENCE.json")
    parser.add_argument("--tests", type=Path, default=ROOT / "tests")
    args = parser.parse_args()

    from app.operation_registry import REGISTRY  # local import for a useful CLI error
    from tools.full_api_matrix import IMPLEMENTED

    catalog_bytes = args.catalog.read_bytes()
    catalog = json.loads(catalog_bytes)
    source_map = {
        _canonical(method, path): label
        for (method, path), label in IMPLEMENTED.items()
    }
    report = build_report(
        catalog,
        source_map=source_map,
        registry_entries=REGISTRY.entries,
        test_root=args.tests,
        catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        auxiliary_source_operations=AUXILIARY_SOURCE_OPERATIONS,
    )
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "operation_count": report["operation_count"],
        "connector_evidence_counts": report["connector_evidence_counts"],
        "function_verification_performed": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
