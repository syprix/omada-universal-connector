"""Bounded aggregate projection for the OLT Ethernet and PON port read."""
from __future__ import annotations

from typing import Any


MAX_ROWS = 64
MAX_ONUS_PER_PORT = 256
MAX_INT32 = 2_147_483_647
_ROOT_FIELDS = {"ethUnit1PortDTOList", "ponPortDTOList"}
_ETH_FIELDS = {
    "port", "mediaType", "description", "status", "speed", "duplex", "flowControl",
    "lag", "speedLink", "duplexLink", "linkStatus", "type", "speedMax",
}
_PON_FIELDS = {
    "portId", "status", "downstreamFEC", "keyExchangePeriod", "dbaCalculateMode",
    "maxDistance", "minDistance", "portIsolate", "onuIsolate", "longLaserOnuAutoDetect",
    "autoDetectInterval", "type", "linkStatus", "duplexLink", "speed", "upLinkSpeed",
    "downLinkSpeed", "longLaserOnuAutoIsolate", "downlinkList", "onuNum",
}
_ETH_MEDIA = {"FIBER", "COPPER"}
_ETH_ADMIN = {"DISABLE", "ENABLE"}
_ETH_LINK = {"LINK_UP", "LINK_DOWN"}
_ETH_DUPLEX = {"FULL", "HALF", "AUTO"}
_ETH_TYPES = {"COPPER", "COMBO", "SFP", "SFP+", "RJ45"}
_PON_ADMIN = {"DISABLE", "ENABLE"}
_PON_LINK = {"INACTIVE", "ACTIVE_WORKING", "ACTIVE_WORKING_NONE", "ACTIVE_STANDBY"}


class OltPortsSummaryError(ValueError):
    """Raised when the response exceeds the documented port-list bounds."""


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _valid_int(value: Any, maximum: int = MAX_INT32) -> bool:
    return type(value) is int and 0 <= value <= maximum


def project_olt_ports_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise OltPortsSummaryError("response_invalid")

    eth_rows = result.get("ethUnit1PortDTOList")
    pon_rows = result.get("ponPortDTOList")
    missing = sum(name not in result or result.get(name) is None for name in _ROOT_FIELDS)
    if eth_rows is None:
        eth_rows = []
    if pon_rows is None:
        pon_rows = []
    if (not isinstance(eth_rows, list) or len(eth_rows) > MAX_ROWS or
            not isinstance(pon_rows, list) or len(pon_rows) > MAX_ROWS):
        raise OltPortsSummaryError("response_invalid")

    invalid = 0
    unknown = len(set(result) - _ROOT_FIELDS)
    redacted = 0
    eth_admin: dict[str, int] = {}
    eth_link: dict[str, int] = {}
    eth_media: dict[str, int] = {}
    eth_duplex: dict[str, int] = {}
    eth_type: dict[str, int] = {}
    eth_speed: dict[int, int] = {}
    pon_admin: dict[str, int] = {}
    pon_link: dict[str, int] = {}
    onu_count = 0
    onu_count_present = 0
    onu_list_count = 0
    mismatch_count = 0

    for row in eth_rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid += 1
            continue
        unknown += len(set(row) - _ETH_FIELDS)
        redacted += len(row)
        port = row.get("port")
        if not isinstance(port, str) or len(port) > 32:
            invalid += 1
        for field, counts, allowed in (("status", eth_admin, _ETH_ADMIN),
                                       ("linkStatus", eth_link, _ETH_LINK),
                                       ("mediaType", eth_media, _ETH_MEDIA),
                                       ("duplex", eth_duplex, _ETH_DUPLEX),
                                       ("type", eth_type, _ETH_TYPES)):
            value = row.get(field)
            if value is None:
                missing += 1
            elif isinstance(value, str) and value in allowed:
                _increment(counts, value)
            else:
                invalid += 1
        speed = row.get("speedLink")
        if speed is None:
            missing += 1
        elif _valid_int(speed, 100_000):
            _increment(eth_speed, speed)
        else:
            invalid += 1

    for row in pon_rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid += 1
            continue
        unknown += len(set(row) - _PON_FIELDS)
        redacted += len(row)
        port_id = row.get("portId")
        if port_id is not None and (not isinstance(port_id, str) or len(port_id) > 128):
            invalid += 1
        for field, counts, allowed in (("status", pon_admin, _PON_ADMIN),
                                       ("linkStatus", pon_link, _PON_LINK)):
            value = row.get(field)
            if value is None:
                missing += 1
            elif isinstance(value, str) and value in allowed:
                _increment(counts, value)
            else:
                invalid += 1
        declared_onus = row.get("onuNum")
        onu_rows = row.get("downlinkList")
        if declared_onus is not None:
            if _valid_int(declared_onus):
                onu_count += declared_onus
                onu_count_present += 1
            else:
                invalid += 1
        if onu_rows is not None:
            if not isinstance(onu_rows, list) or len(onu_rows) > MAX_ONUS_PER_PORT:
                invalid += 1
            else:
                onu_list_count += len(onu_rows)
                if declared_onus is not None and _valid_int(declared_onus) and declared_onus != len(onu_rows):
                    mismatch_count += 1
        elif declared_onus is None:
            missing += 1

    data: dict[str, object] = {
        "ethernet_port_count": len(eth_rows),
        "ethernet_admin_state_counts": eth_admin,
        "ethernet_link_state_counts": eth_link,
        "ethernet_media_type_counts": eth_media,
        "ethernet_duplex_counts": eth_duplex,
        "ethernet_port_type_counts": eth_type,
        "ethernet_negotiated_speed_counts": [
            {"mbps": speed, "count": eth_speed[speed]} for speed in sorted(eth_speed)
        ],
        "pon_port_count": len(pon_rows),
        "pon_laser_state_counts": pon_admin,
        "pon_link_state_counts": pon_link,
        "onu_count": onu_count,
        "onu_count_reported_port_count": onu_count_present,
        "onu_rows_counted": onu_list_count,
        "onu_count_mismatch_count": mismatch_count,
    }
    return {
        "data": data,
        "partial": bool(missing or invalid or unknown or mismatch_count),
        "missing_count": missing,
        "invalid_count": invalid,
        "unknown_field_count": unknown,
        "redacted_field_count": redacted,
    }
