"""Redacted status projections for OLT ONU isolation settings."""
from __future__ import annotations

from typing import Any


_ENABLED = {"ENABLE", "DISABLE"}
_GLOBAL_FIELDS = {"onuIsolation", "supportOnuIsolation"}
_ISOLATION_FIELDS = {"onuIsolation", "isolateAllVlan", "vlanList"}


class OltPonStatusError(ValueError):
    """Raised when a PON status response has an unsupported shape."""


def _project_flags(result: Any, fields: set[str], *, isolation_detail: bool) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise OltPonStatusError("response_invalid")

    values: dict[str, bool] = {}
    missing = 0
    invalid = 0
    unknown = len(set(result) - fields)
    redacted = 0
    for source, target in (("onuIsolation", "onu_isolation_enabled"),
                           ("supportOnuIsolation", "onu_isolation_supported"),
                           ("isolateAllVlan", "all_vlan_scope_enabled")):
        if source not in fields:
            continue
        value = result.get(source)
        if value is None:
            missing += 1
        elif isinstance(value, str) and len(value) <= 16 and value in _ENABLED:
            values[target] = value == "ENABLE"
            redacted += 1
        else:
            invalid += 1

    data: dict[str, object] = values
    if isolation_detail:
        vlan_list = result.get("vlanList")
        if vlan_list is None:
            missing += 1
            data["vlan_list_configured"] = False
        elif isinstance(vlan_list, str) and len(vlan_list) <= 256:
            # The source contains VLAN identifiers; disclose only whether a list exists.
            data["vlan_list_configured"] = bool(vlan_list.strip())
            redacted += 1
        else:
            invalid += 1
    return {
        "data": data,
        "partial": bool(missing or invalid or unknown),
        "missing_count": missing,
        "invalid_count": invalid,
        "unknown_field_count": unknown,
        "redacted_field_count": redacted,
    }


def project_olt_onu_global_status(result: Any) -> dict[str, object]:
    return _project_flags(result, _GLOBAL_FIELDS, isolation_detail=False)


def project_olt_onu_isolation_status(result: Any) -> dict[str, object]:
    return _project_flags(result, _ISOLATION_FIELDS, isolation_detail=True)
