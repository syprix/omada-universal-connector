"""Redacted, bounded summary of AP groups bound to one site SSID."""

from __future__ import annotations

from typing import Any

MAX_AP_GROUPS = 128
INT32_MAX = 2**31 - 1
INT64_MAX = 2**63 - 1


class SsidApGroupsError(ValueError):
    """The AP-group response is malformed or exceeds its projection bounds."""


def _count(value: Any, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise SsidApGroupsError("response_invalid")
    return value


def project_ssid_ap_groups(result: Any) -> dict[str, object]:
    """Return only counts and documented SSID limits; omit group identities."""
    if not isinstance(result, dict):
        raise SsidApGroupsError("response_invalid")
    known = {"apGroups", "maxSsids2G", "maxSsids5G", "maxSsids6G", "maxSsidsMlo"}
    unknown_field_count = sum(1 for key in result if key not in known)
    partial = unknown_field_count > 0
    out: dict[str, object] = {"unknown_field_count": unknown_field_count}
    group_rows = result.get("apGroups")
    if group_rows is None:
        out.update({"group_count": None, "access_point_count": None,
                    "remaining_binding_count": None, "unknown_row_field_count": None})
        partial = True
    else:
        if not isinstance(group_rows, list) or len(group_rows) > MAX_AP_GROUPS:
            raise SsidApGroupsError("response_invalid")
        total_aps = 0
        remaining_total = 0
        unknown_row_field_count = 0
        for row in group_rows:
            if not isinstance(row, dict):
                raise SsidApGroupsError("response_invalid")
            unknown_row_field_count += sum(
                1 for key in row if key not in {"id", "name", "apNum", "remainingBinding"})
            if "apNum" not in row:
                partial = True
            else:
                total_aps += _count(row["apNum"], INT64_MAX)
                if total_aps > INT64_MAX:
                    raise SsidApGroupsError("response_invalid")
            bindings = row.get("remainingBinding")
            if bindings is None:
                partial = True
            elif not isinstance(bindings, dict) or len(bindings) > 16:
                raise SsidApGroupsError("response_invalid")
            else:
                for key, value in bindings.items():
                    if not isinstance(key, str) or not key or len(key) > 64:
                        raise SsidApGroupsError("response_invalid")
                    remaining_total += _count(value, INT32_MAX)
                    if remaining_total > INT64_MAX:
                        raise SsidApGroupsError("response_invalid")
        out["group_count"] = len(group_rows)
        out["access_point_count"] = total_aps
        out["remaining_binding_count"] = remaining_total
        out["unknown_row_field_count"] = unknown_row_field_count
        partial = partial or unknown_row_field_count > 0

    for source, target in (("maxSsids2G", "max_ssids_2g"),
                           ("maxSsids5G", "max_ssids_5g"),
                           ("maxSsids6G", "max_ssids_6g"),
                           ("maxSsidsMlo", "max_ssids_mlo")):
        if source in result:
            out[target] = _count(result[source], INT32_MAX)
        else:
            partial = True
    out["partial"] = partial
    return out
