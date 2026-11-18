"""Redacted projection of site-wide switch-port counter rows."""
from __future__ import annotations

import re


class SwitchPortCountersError(ValueError):
    """Port-counter rows cannot be bounded or safely bound to a switch."""

    def __init__(self, code: str = "switch_port_counters_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAC = re.compile(r"(?:[0-9A-Fa-f]{2}(?P<sep>[:-])){5}[0-9A-Fa-f]{2}\Z")
_COUNTERS = (
    "txBytes", "rxBytes", "txFrames", "rxFrames", "txMulticast",
    "rxMulticast", "txBroadcast", "rxBroadcast", "txErrors", "rxErrors",
)
_ALLOWED_FIELDS = frozenset({"switchMac", "port", *_COUNTERS})
_DOCUMENTED_REDACTED_FIELDS = frozenset({
    "standardPort", "configStack", "configMlagPeerLink", "configMlagDad",
    "stackPortsGroupIndex", "portName", "switchName", "switchType",
    "switchStatusCategory", "switchSupportPoe", "site", "tagIds", "tagName",
    "connectedStatus", "madUsed", "disable", "type", "operation", "supportPoe",
    "poeDisplayType", "poe", "portStatus", "linkSpeed", "duplex", "lagSetting",
    "stackId", "stackName", "unit",
})
_MAX_ROWS = 4096
_MAX_ROW_FIELDS = 64
_MAX_KEY_LENGTH = 128
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _mac_key(value: object) -> str | None:
    if type(value) is not str:
        return None
    match = _MAC.fullmatch(value)
    if match is None:
        return None
    sep = match.group("sep")
    # The pattern captures the last separator; reject mixed delimiters.
    expected = sep
    if any(value[index] != expected for index in (2, 5, 8, 11, 14)):
        return None
    return value.replace(sep, "").lower()


def project_switch_port_counters(rows: object,
                                 expected_switch_mac: str) -> dict[str, object]:
    """Project fully paginated rows belonging to one already-inventoried switch.

    Valid rows for other switches are skipped. Rows without a valid MAC are
    omitted and mark the projection partial. No MAC or other identity field is
    returned. Pagination and controller/site selection are the caller's job.
    """
    expected = _mac_key(expected_switch_mac)
    if expected is None:
        raise SwitchPortCountersError("switch_ref_invalid")
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise SwitchPortCountersError()

    items: list[dict[str, int]] = []
    invalid_rows = 0
    missing_count = 0
    unknown_count = 0
    redacted_count = 0
    skipped_other = 0
    seen_ports: set[int] = set()
    duplicate_ports = 0
    matched_rows = 0

    for row in rows:
        if not isinstance(row, dict) or len(row) > _MAX_ROW_FIELDS:
            invalid_rows += 1
            continue
        for key in row:
            if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
                raise SwitchPortCountersError()

        row_mac = _mac_key(row.get("switchMac"))
        if row_mac is None:
            invalid_rows += 1
            missing_count += 1 if "switchMac" not in row else 0
            continue
        if row_mac != expected:
            skipped_other += 1
            continue
        matched_rows += 1

        for key in row:
            if key == "switchMac":
                redacted_count += 1
            elif key not in _ALLOWED_FIELDS:
                if key in _DOCUMENTED_REDACTED_FIELDS:
                    redacted_count += 1
                else:
                    unknown_count += 1

        safe: dict[str, int] = {}
        port = row.get("port")
        if type(port) is not int or not 0 <= port <= 4096:
            invalid_rows += 1
            if "port" not in row:
                missing_count += 1
            continue
        safe["port"] = port
        if port in seen_ports:
            duplicate_ports += 1
        else:
            seen_ports.add(port)

        for field in _COUNTERS:
            if field not in row:
                missing_count += 1
                continue
            value = row[field]
            if type(value) is int and _INT64_MIN <= value <= _INT64_MAX:
                safe[field] = value
            else:
                invalid_rows += 1
        items.append(safe)

    missing_target_rows = matched_rows == 0
    return {
        "status": "ok",
        "resource": "switch_port_counters",
        "data": {"items": items},
        "partial": bool(invalid_rows or missing_count or unknown_count or
                         duplicate_ports or missing_target_rows),
        "invalid_row_count": invalid_rows,
        "missing_field_count": missing_count,
        "unknown_field_count": unknown_count,
        "redacted_field_count": redacted_count,
        "skipped_other_switch_count": skipped_other,
        "duplicate_port_count": duplicate_ports,
        "target_rows_present": matched_rows > 0,
    }
