"""Aggregate fixed OLT PON-port configuration without returning port identifiers."""
from __future__ import annotations

from typing import Any

MAX_PORTS = 64
MAX_FIELDS = 24
MAX_INT32 = 2_147_483_647
_ENUMS = {
    "status": {"DISABLE", "ENABLE"},
    "downstreamFEC": {"DISABLE", "ENABLE"},
    "dbaCalculateMode": {"MIN_DELAY", "MAX_BW"},
    "portIsolate": {"DISABLE", "ENABLE"},
    "onuIsolate": {"DISABLE", "ENABLE"},
    "longLaserOnuAutoDetect": {"DISABLE", "ENABLE"},
    "type": {"COPPER", "COMBO", "SFP"},
    "linkStatus": {"INACTIVE", "ACTIVE_WORKING", "ACTIVE_WORKING_NONE", "ACTIVE_STANDBY"},
    "duplexLink": {"FULL"},
    "speed": {"GPON", "XG_PON", "XGS_PON", "NONE"},
    "longLaserOnuAutoIsolate": {"DISABLE", "ENABLE"},
}
_NUMERIC_BOUNDS = {
    "keyExchangePeriod": (0, 60), "maxDistance": (1, 60),
    "minDistance": (1, 40), "autoDetectInterval": (1, 100),
    "upLinkSpeed": (0, MAX_INT32), "downLinkSpeed": (0, MAX_INT32),
    "onuNum": (0, 128),
}
_FIELDS = {"portId", "downlinkList", *_ENUMS, *_NUMERIC_BOUNDS}


class OltPonPortConfigError(ValueError):
    """Raised for malformed or unbounded OLT PON-port responses."""


def project_olt_pon_port_config_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_PORTS:
        raise OltPonPortConfigError("response_invalid")
    enum_counts: dict[str, dict[str, int]] = {key: {} for key in _ENUMS}
    numeric_ranges: dict[str, dict[str, int]] = {}
    invalid = missing = unknown = redacted = 0
    downlink_reported = 0
    onu_total = onu_reported = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > MAX_FIELDS:
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        redacted += len(row)
        port_id = row.get("portId")
        if port_id is None:
            missing += 1
        elif not isinstance(port_id, str) or len(port_id) > 128:
            invalid += 1
        downlinks = row.get("downlinkList")
        if downlinks is not None:
            if not isinstance(downlinks, list) or len(downlinks) > MAX_PORTS:
                invalid += 1
            else:
                downlink_reported += 1
        for key, allowed in _ENUMS.items():
            value = row.get(key)
            if value is None:
                missing += 1
            elif isinstance(value, str) and value in allowed:
                counts = enum_counts[key]
                counts[value] = counts.get(value, 0) + 1
            else:
                invalid += 1
        for key, (minimum, maximum) in _NUMERIC_BOUNDS.items():
            value = row.get(key)
            if value is None:
                missing += 1
            elif type(value) is int and minimum <= value <= maximum:
                bounds = numeric_ranges.setdefault(key, {"min": value, "max": value, "count": 0})
                bounds["min"] = min(bounds["min"], value)
                bounds["max"] = max(bounds["max"], value)
                bounds["count"] += 1
                if key == "onuNum":
                    onu_total += value
                    onu_reported += 1
            else:
                invalid += 1
        if (type(row.get("minDistance")) is int and type(row.get("maxDistance")) is int and
                row["minDistance"] >= 1 and row["maxDistance"] >= 1 and
                row["maxDistance"] - row["minDistance"] > 40):
            invalid += 1
    return {
        "data": {"pon_port_count": len(result), "enum_state_counts": enum_counts,
                 "numeric_setting_ranges": numeric_ranges, "onu_count": onu_total,
                 "onu_count_reported_port_count": onu_reported,
                 "downlink_list_reported_port_count": downlink_reported},
        "partial": bool(missing or invalid or unknown),
        "missing_count": missing, "invalid_count": invalid,
        "unknown_field_count": unknown, "redacted_field_count": redacted,
    }


def project_olt_pon_port_config_page_summary(
    result: Any, *, requested_page: int, requested_size: int,
) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 12:
        raise OltPonPortConfigError("response_invalid")
    content = result.get("content")
    total_elements, total_pages = result.get("totalElements"), result.get("totalPages")
    number, size = result.get("number"), result.get("size")
    count = result.get("numberOfElements")
    first, last = result.get("first"), result.get("last")
    if (type(requested_page) is not int or not 0 <= requested_page <= 10_000 or
            type(requested_size) is not int or not 1 <= requested_size <= 100 or
            not isinstance(content, list) or len(content) > requested_size or
            type(total_elements) is not int or not 0 <= total_elements <= 100_000 or
            type(total_pages) is not int or not 0 <= total_pages <= 10_000 or
            number != requested_page or type(number) is not int or
            size != requested_size or type(size) is not int or
            count != len(content) or type(count) is not int or
            type(first) is not bool or type(last) is not bool):
        raise OltPonPortConfigError("response_invalid")
    projected = project_olt_pon_port_config_summary(content)
    return {
        **projected,
        "page": {"page_number": number, "page_size": size,
                 "page_item_count": count, "total_elements": total_elements,
                 "total_pages": total_pages, "first_page": first, "last_page": last},
    }
