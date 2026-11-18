"""Bounded summaries for OLT Ethernet port and LAG configuration reads."""
from __future__ import annotations

from typing import Any


MAX_ROWS = 128
MAX_FIELDS = 16
MAX_INT32 = 2_147_483_647
_PORT_FIELDS = {
    "port", "mediaType", "description", "status", "speed", "duplex", "flowControl",
    "lag", "speedLink", "duplexLink", "linkStatus", "type", "speedMax",
}
_LAG_FIELDS = {"lag", "description", "status", "speed", "duplex", "flowControl"}
_PORT_TYPES = {0: "COPPER", 1: "COMBO", 2: "SFP", 3: "SFP_PLUS", 4: "RJ45"}


class OltEthConfigError(ValueError):
    """Raised when an OLT Ethernet configuration response is unbounded."""


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _valid_integer(value: Any, maximum: int = MAX_INT32) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _project_rows(result: Any, *, lag_rows: bool) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_ROWS:
        raise OltEthConfigError("response_invalid")

    allowed_fields = _LAG_FIELDS if lag_rows else _PORT_FIELDS
    invalid = 0
    missing = 0
    unknown = 0
    redacted = 0
    admin: dict[str, int] = {}
    speed: dict[int, int] = {}
    speed_link: dict[int, int] = {}
    duplex: dict[str, int] = {}
    duplex_link: dict[str, int] = {}
    flow_control: dict[str, int] = {}
    link: dict[str, int] = {}
    port_types: dict[str, int] = {}
    lag_member_count = 0

    for row in result:
        if not isinstance(row, dict) or len(row) > MAX_FIELDS:
            invalid += 1
            continue
        unknown += len(set(row) - allowed_fields)
        redacted += len(row)
        identity_field = "lag" if lag_rows else "port"
        identity = row.get(identity_field)
        if not isinstance(identity, str) or len(identity) > 128:
            invalid += 1
        if not lag_rows and row.get("lag"):
            if not isinstance(row["lag"], str) or len(row["lag"]) > 128:
                invalid += 1
            else:
                lag_member_count += 1

        for field, counts, valid_values, labels in (
            ("status", admin, {0, 1}, {0: "DISABLED", 1: "ENABLED"}),
            ("duplex", duplex, {0, 2}, {0: "AUTO", 2: "FULL"}),
            ("flowControl", flow_control, {0, 1}, {0: "DISABLED", 1: "ENABLED"}),
        ):
            value = row.get(field)
            if value is None:
                missing += 1
            elif type(value) is int and value in valid_values:
                _increment(counts, labels[value])
            else:
                invalid += 1

        value = row.get("speed")
        if value is None:
            missing += 1
        elif _valid_integer(value, 100_000):
            _increment(speed, value)
        else:
            invalid += 1

        if not lag_rows:
            for field, counts, valid_values, labels in (
                ("linkStatus", link, {0, 1}, {0: "LINK_DOWN", 1: "LINK_UP"}),
                ("duplexLink", duplex_link, {0, 1}, {0: "DISABLED", 1: "ENABLED"}),
            ):
                value = row.get(field)
                if value is None:
                    missing += 1
                elif type(value) is int and value in valid_values:
                    _increment(counts, labels[value])
                else:
                    invalid += 1
            value = row.get("speedLink")
            if value is None:
                missing += 1
            elif _valid_integer(value, 100_000):
                _increment(speed_link, value)
            else:
                invalid += 1
            for field in ("mediaType", "speedMax"):
                value = row.get(field)
                if value is not None and not _valid_integer(value):
                    invalid += 1
            value = row.get("type")
            if value is None:
                missing += 1
            elif type(value) is int and value in _PORT_TYPES:
                _increment(port_types, _PORT_TYPES[value])
            else:
                invalid += 1

    data: dict[str, object] = {
        "item_count": len(result),
        "admin_state_counts": admin,
        "speed_mode_counts": [{"mbps": key, "count": speed[key]} for key in sorted(speed)],
        "duplex_mode_counts": duplex,
        "flow_control_state_counts": flow_control,
    }
    if lag_rows:
        data["lag_count"] = len(result)
    else:
        data["link_state_counts"] = link
        data["port_type_counts"] = port_types
        data["negotiated_speed_counts"] = [
            {"mbps": key, "count": speed_link[key]} for key in sorted(speed_link)]
        data["negotiated_duplex_link_state_counts"] = duplex_link
        data["ports_in_lags"] = lag_member_count
    return {
        "data": data,
        "partial": bool(missing or invalid or unknown),
        "missing_count": missing,
        "invalid_count": invalid,
        "unknown_field_count": unknown,
        "redacted_field_count": redacted,
    }


def project_olt_lag_config_summary(result: Any) -> dict[str, object]:
    return _project_rows(result, lag_rows=True)


def project_olt_eth_config_summary(result: Any) -> dict[str, object]:
    return _project_rows(result, lag_rows=False)
