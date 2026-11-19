"""Compact comparison of selected, site-bound capability reads."""
from __future__ import annotations

import re
from typing import Any

try:
    from .site_capabilities import FIELDS
except ImportError:
    from site_capabilities import FIELDS

MAX_SITES = 16
_REF = re.compile(r"[0-9a-f]{24}\Z")
_ERRORS = {"openapi_permission_denied", "openapi_http_error", "openapi_rejected",
           "openapi_authentication_failed", "site_ref_unknown", "site_ref_invalid"}


class SiteCapabilityComparisonError(ValueError):
    pass


def project_site_capability_comparison(site_refs: object,
                                       results: dict[str, object]) -> dict[str, object]:
    if (not isinstance(site_refs, list) or not 2 <= len(site_refs) <= MAX_SITES or
            any(not isinstance(ref, str) or not _REF.fullmatch(ref) for ref in site_refs) or
            len(set(site_refs)) != len(site_refs) or not isinstance(results, dict)):
        raise SiteCapabilityComparisonError("site_capability_comparison_invalid")

    columns: list[dict[str, object]] = []
    values_by_site: dict[str, dict[str, bool]] = {}
    for ref in site_refs:
        result = results.get(ref)
        if (not isinstance(result, dict) or result.get("status") != "ok" or
                result.get("resource") != "site_capabilities" or result.get("site_ref") != ref):
            error = result.get("error") if isinstance(result, dict) else None
            if not isinstance(error, str) or error not in _ERRORS:
                error = "source_unavailable"
            columns.append({"site_ref": ref, "status": "unavailable", "partial": True,
                            "error": error, "enabled_count": 0, "disabled_count": 0,
                            "unknown_count": len(FIELDS)})
            values_by_site[ref] = {}
            continue

        data = result.get("data")
        flags = data.get("capabilities") if isinstance(data, dict) else None
        if not isinstance(flags, dict):
            raise SiteCapabilityComparisonError("site_capability_response_invalid")
        safe = {name: value for name, value in flags.items()
                if name in set(FIELDS.values()) and type(value) is bool}
        enabled = sum(value is True for value in safe.values())
        disabled = sum(value is False for value in safe.values())
        columns.append({"site_ref": ref, "status": "ok",
                        "partial": result.get("partial") is not False,
                        "enabled_count": enabled, "disabled_count": disabled,
                        "unknown_count": len(FIELDS) - len(safe)})
        values_by_site[ref] = safe

    features = [{"name": name, "values": [
        (1 if values_by_site[ref][name] else 0) if name in values_by_site[ref] else None
        for ref in site_refs
    ]} for name in sorted(FIELDS.values())]
    return {"status": "ok", "resource": "site_capability_comparison",
            "site_refs": site_refs, "sites": columns, "feature_columns": sorted(FIELDS.values()),
            "feature_values": [row["values"] for row in features],
            "partial": any(site["partial"] for site in columns),
            "semantics": "1=enabled, 0=disabled, null=unknown_or_unavailable"}
