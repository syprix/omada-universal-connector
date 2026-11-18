"""Redacted projection of site-wide switch-port PoE information."""
from __future__ import annotations

import math
import re


class SwitchPortPoeInfoError(ValueError):
    """PoE info rows cannot be bounded or safely bound to a switch."""

    def __init__(self, code: str = "switch_port_poe_info_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAC = re.compile(r"(?:[0-9A-Fa-f]{2}(?P<sep>[:-])){5}[0-9A-Fa-f]{2}\Z")
_NUMERIC_FIELDS = frozenset({"poeStatus", "power", "voltage", "current"})
_OUTPUT_FIELDS = frozenset({"port", "supportPoe", "poeDisplayType", "poe"}) | _NUMERIC_FIELDS
_DOCUMENTED_REDACTED_FIELDS = frozenset({
    "standardPort", "configStack", "configMlagPeerLink", "configMlagDad",
    "stackPortsGroupIndex", "portName", "switchName", "switchType",
    "switchStatusCategory", "switchSupportPoe", "site", "tagIds", "tagName",
    "connectedStatus", "madUsed", "disable", "type", "operation",
    "portStatus", "linkSpeed", "duplex", "lagSetting", "stackId", "stackName",
    "unit", "pdClass",
})
_ALLOWED_FIELDS = _OUTPUT_FIELDS | _DOCUMENTED_REDACTED_FIELDS | frozenset({"switchMac"})
_MAX_ROWS = 4096
_MAX_ROW_FIELDS = 64
_MAX_KEY_LENGTH = 128
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _mac_key(value: object) -> str | None:
    if type(value) is not str:
        return None
    match = _MAC.fullmatch(value)
    if match is None:
        return None
    separator = match.group("sep")
    if any(value[index] != separator for index in (2, 5, 8, 11, 14)):
        return None
    return value.replace(separator, "").lower()


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def project_switch_port_poe_info(rows: object,
                                 expected_switch_mac: str) -> dict[str, object]:
    """Project rows for one known switch, dropping identity and port settings.

    ``rows`` must already be collected from the complete paginated response.
    Measurements are returned as reported, without unit or scale claims.
    """
    expected = _mac_key(expected_switch_mac)
    if expected is None:
        raise SwitchPortPoeInfoError("switch_ref_invalid")
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise SwitchPortPoeInfoError()

    items: list[dict[str, object]] = []
    invalid_rows = missing_count = unknown_count = redacted_count = skipped_other = duplicate_ports = 0
    matched_rows = 0
    seen_ports: set[int] = set()

    for row in rows:
        if not isinstance(row, dict) or len(row) > _MAX_ROW_FIELDS:
            invalid_rows += 1
            continue
        for key in row:
            if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
                raise SwitchPortPoeInfoError()
        row_mac = _mac_key(row.get("switchMac"))
        if row_mac is None:
            invalid_rows += 1
            missing_count += "switchMac" not in row
            continue
        if row_mac != expected:
            skipped_other += 1
            continue
        matched_rows += 1
        for key in row:
            if key == "switchMac" or key in _DOCUMENTED_REDACTED_FIELDS:
                redacted_count += 1
            elif key not in _ALLOWED_FIELDS:
                unknown_count += 1

        port = row.get("port")
        if type(port) is not int or not 0 <= port <= 4096:
            invalid_rows += 1
            if "port" not in row:
                missing_count += 1
            continue
        item: dict[str, object] = {"port": port}
        if port in seen_ports:
            duplicate_ports += 1
        else:
            seen_ports.add(port)

        for field in ("supportPoe", "poeDisplayType", "poe", *_NUMERIC_FIELDS):
            if field not in row:
                missing_count += 1
                continue
            value = row[field]
            if field == "supportPoe":
                valid = type(value) is bool
            elif field == "poeDisplayType":
                valid = type(value) is int and -1 <= value <= 9
            elif field == "poe":
                valid = type(value) is int and value in (0, 1)
            else:
                valid = _finite_number(value)
            if valid:
                item[field] = value
            else:
                invalid_rows += 1
        items.append(item)

    target_absent = matched_rows == 0
    return {
        "status": "ok",
        "resource": "switch_port_poe_info",
        "data": {"items": items},
        "partial": bool(invalid_rows or missing_count or unknown_count or
                         duplicate_ports or target_absent),
        "invalid_row_count": invalid_rows,
        "missing_field_count": missing_count,
        "unknown_field_count": unknown_count,
        "redacted_field_count": redacted_count,
        "skipped_other_switch_count": skipped_other,
        "duplicate_port_count": duplicate_ports,
        "target_rows_present": matched_rows > 0,
    }
