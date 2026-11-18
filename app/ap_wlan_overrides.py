"""Bounded, credential-redacting summary of AP WLAN override settings."""
from __future__ import annotations


class ApWlanOverridesError(ValueError):
    """The documented AP WLAN override response is outside supported bounds."""


_ROOT = frozenset({"ssidOverrides", "apGroupId", "apGroupName"})
_ROW = frozenset({"ssidId", "ssidEntryId", "ssidName", "ssidPassword", "band",
                  "security", "vlanEnable", "vlanId", "vlanPoolIds", "ssidEnable"})
_REDACTED = frozenset({"ssidId", "ssidEntryId", "ssidName", "ssidPassword",
                       "vlanId", "vlanPoolIds", "apGroupId", "apGroupName"})
_MAX_ROWS = 256
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def summarize_ap_wlan_overrides(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8 or "ssidOverrides" not in raw:
        raise ApWlanOverridesError()
    rows = raw["ssidOverrides"]
    if not isinstance(rows, list) or len(rows) > 4096:
        raise ApWlanOverridesError()

    unknown = invalid = missing = redacted = invalid_rows = 0
    enabled = disabled = unknown_enable = 0
    vlan_enabled = vlan_disabled = unknown_vlan_enable = 0
    password_present = vlan_id_present = vlan_pool_present = 0
    bands: dict[int, int] = {}
    security: dict[int, int] = {}

    for field in ("apGroupId", "apGroupName"):
        if field not in raw:
            continue
        redacted += 1
        if not isinstance(raw[field], str) or len(raw[field]) > 256:
            invalid += 1

    unknown += sum(1 for field in raw if field not in _ROOT)
    included = min(len(rows), _MAX_ROWS)
    for row in rows[:_MAX_ROWS]:
        if not isinstance(row, dict) or len(row) > 24:
            invalid_rows += 1
            continue
        unknown += sum(1 for field in row if field not in _ROW)
        for field in ("ssidId", "ssidName"):
            if field not in row:
                missing += 1
                continue
            redacted += 1
            value = row[field]
            limit = 256 if field == "ssidId" else 32
            if not isinstance(value, str) or len(value) > limit:
                invalid += 1
        if "ssidEntryId" in row:
            redacted += 1
            if not _int32(row["ssidEntryId"]):
                invalid += 1
        if "ssidPassword" in row:
            redacted += 1
            value = row["ssidPassword"]
            if not isinstance(value, str) or not (8 <= len(value) <= 63
                    and value.isascii() and all(" " <= c <= "~" for c in value)):
                invalid += 1
            else:
                password_present += 1
        if "vlanPoolIds" in row:
            redacted += 1
            value = row["vlanPoolIds"]
            if not isinstance(value, str) or len(value) > 1024:
                invalid += 1
            elif value:
                vlan_pool_present += 1
        if "vlanId" in row:
            redacted += 1
            if _int32(row["vlanId"]):
                vlan_id_present += 1
            else:
                invalid += 1
        if "band" in row:
            value = row["band"]
            if not isinstance(value, list) or len(value) > 3:
                invalid += 1
            else:
                for code in value:
                    if type(code) is int and code in (0, 1, 2):
                        bands[code] = bands.get(code, 0) + 1
                    else:
                        invalid += 1
        if "security" in row:
            code = row["security"]
            if type(code) is int and code in (0, 2, 3, 4, 5):
                security[code] = security.get(code, 0) + 1
            else:
                invalid += 1
        if "ssidEnable" not in row:
            unknown_enable += 1
        elif type(row["ssidEnable"]) is bool:
            enabled += int(row["ssidEnable"])
            disabled += int(not row["ssidEnable"])
        else:
            invalid += 1
            unknown_enable += 1
        if "vlanEnable" not in row:
            unknown_vlan_enable += 1
        elif type(row["vlanEnable"]) is bool:
            vlan_enabled += int(row["vlanEnable"])
            vlan_disabled += int(not row["vlanEnable"])
        else:
            invalid += 1
            unknown_vlan_enable += 1

    truncated = len(rows) - included
    partial = bool(truncated or invalid_rows or unknown or invalid or missing
                   or unknown_enable or unknown_vlan_enable)
    return {
        "status": "ok", "resource": "ap_wlan_overrides",
        "entry_count": len(rows), "included_entry_count": included,
        "truncated_entry_count": truncated, "enabled_count": enabled,
        "disabled_count": disabled, "unknown_enabled_state_count": unknown_enable,
        "vlan_enabled_count": vlan_enabled, "vlan_disabled_count": vlan_disabled,
        "unknown_vlan_state_count": unknown_vlan_enable,
        "password_present_count": password_present,
        "vlan_id_present_count": vlan_id_present,
        "vlan_pool_present_count": vlan_pool_present,
        "by_band_code": dict(sorted(bands.items())),
        "by_security_code": dict(sorted(security.items())),
        "ap_group_assigned": isinstance(raw.get("apGroupId"), str)
                              and bool(raw.get("apGroupId")),
        "redacted_field_count": redacted, "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown, "invalid_field_count": invalid,
        "missing_field_count": missing, "partial": partial,
    }
