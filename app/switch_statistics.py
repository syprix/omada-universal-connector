from __future__ import annotations

from collections import Counter
from typing import Any


class SwitchStatisticsError(ValueError):
    pass


MAX_PORTS = 4096
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MAX = 2**63 - 1
_STATUS_CODES = {0, 1, *range(10, 18), *range(20, 28), *range(30, 34), 40, 41, 50}
_SPEED_CODES = {-1, *range(10)}


def _int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _count_map(counter: Counter[int | str]) -> dict[str, int]:
    return {str(key): count for key, count in sorted(counter.items(), key=lambda pair: str(pair[0]))}


def summarize_switch_statistics(raw: Any) -> dict[str, object]:
    """Project documented switch and port statistics without device identities."""
    if not isinstance(raw, dict) or len(raw) > 64:
        raise SwitchStatisticsError("response_shape")
    ports = raw.get("ports")
    if not isinstance(ports, list) or len(ports) > MAX_PORTS:
        raise SwitchStatisticsError("port_rows")

    data: dict[str, object] = {"port_count": len(ports)}
    missing = 0
    invalid = 0
    unknown_fields = sum(key not in {
        "name", "status", "statusCategory", "portNum", "ports", "uplink", "supportPoe",
        "speeds", "supportStack", "supportSTP", "mlagMsg",
    } for key in raw)

    for source, target, accepted in (
        ("status", "status_code", _STATUS_CODES),
        ("statusCategory", "status_category_code", {0, 1, 2, 3, 4}),
        ("portNum", "reported_port_count", None),
    ):
        if source not in raw:
            missing += 1
            continue
        value = raw[source]
        if not _int(value, _INT32_MIN, _INT32_MAX) or (accepted is not None and value not in accepted) or (
            source == "portNum" and value < 0
        ):
            invalid += 1
            continue
        data[target] = value

    by_link: Counter[int] = Counter()
    by_type: Counter[int] = Counter()
    by_poe: Counter[str] = Counter()
    by_stp: Counter[str] = Counter()
    tx_bytes = rx_bytes = total_bytes = 0
    has_counter = False
    unknown_port_rows = 0
    for row in ports:
        if not isinstance(row, dict) or len(row) > 64:
            unknown_port_rows += 1
            continue
        valid_row = True
        port_type = row.get("type")
        if _int(port_type, 1, 3):
            by_type[port_type] += 1
        else:
            valid_row = False
        state = row.get("portStatus")
        if not isinstance(state, dict) or len(state) > 32:
            unknown_port_rows += 1
            continue
        link = state.get("linkStatus")
        if _int(link, 0, 1):
            by_link[link] += 1
        else:
            valid_row = False
        poe, discarding = state.get("poe"), state.get("stpDiscarding")
        if type(poe) is bool:
            by_poe[str(poe).lower()] += 1
        else:
            valid_row = False
        if type(discarding) is bool:
            by_stp[str(discarding).lower()] += 1
        else:
            valid_row = False
        counters = (state.get("tx"), state.get("rx"), state.get("total"))
        if all(_int(value, 0, _INT64_MAX) for value in counters):
            tx_bytes += counters[0]
            rx_bytes += counters[1]
            total_bytes += counters[2]
            has_counter = True
        else:
            valid_row = False
        if not valid_row:
            unknown_port_rows += 1
    data["by_link_status_code"] = _count_map(by_link)
    data["by_port_type_code"] = _count_map(by_type)
    data["by_poe_in_use"] = _count_map(by_poe)
    data["by_stp_discarding"] = _count_map(by_stp)
    data["unknown_port_rows"] = unknown_port_rows
    if has_counter:
        data["tx_bytes"] = tx_bytes
        data["rx_bytes"] = rx_bytes
        data["total_bytes"] = total_bytes
    else:
        missing += 1

    for source, target in (("supportPoe", "support_poe"),
                           ("supportStack", "support_stack"),
                           ("supportSTP", "support_stp")):
        value = raw.get(source)
        if type(value) is bool:
            data[target] = value
        elif source in raw:
            invalid += 1
        else:
            missing += 1
    uplink = raw.get("uplink")
    if isinstance(uplink, dict):
        data["uplink_present"] = bool(uplink)
    elif uplink is not None:
        invalid += 1
    else:
        missing += 1

    mlag = raw.get("mlagMsg")
    if isinstance(mlag, dict):
        role = mlag.get("role")
        if _int(role, _INT32_MIN, _INT32_MAX):
            data["mlag_role_code"] = role
        for source, target in (("dadLinkPort", "dad_link_count"),
                               ("peerLinkPort", "peer_link_count")):
            values = mlag.get(source)
            if isinstance(values, list) and len(values) <= MAX_PORTS and all(
                _int(value, 0, _INT32_MAX) for value in values
            ):
                data[target] = len(values)
            else:
                invalid += 1
    elif mlag is not None:
        invalid += 1
    if "speeds" in raw:
        speeds = raw["speeds"]
        if isinstance(speeds, list) and len(speeds) <= 64 and all(
            _int(value, -1, 9) for value in speeds
        ):
            data["supported_speed_codes"] = sorted(set(speeds))
        else:
            invalid += 1
    else:
        missing += 1

    return {
        "status": "ok",
        "resource": "switch_statistics",
        "data": data,
        "partial": bool(missing or invalid or unknown_fields or unknown_port_rows),
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown_fields,
    }
