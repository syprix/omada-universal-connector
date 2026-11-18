"""Redacted projection for the documented site IPTV settings GET."""
from __future__ import annotations

from typing import Any

MAX_PORTS = 128
MAX_FEATURE_DESCRIPTIONS = 64
_TOP_FIELDS = {"enable", "wanPortId", "mode", "customConfig", "portConfig", "dslConfig", "featureDescription"}
_PORT_FIELDS = {"portId", "name", "type"}
_CUSTOM_FIELDS = {"ipPhoneVlanId", "ipPhoneVlanPriority", "iptvVlanId", "iptvVlanPriority"}
_DSL_FIELDS = {"modulationType", "ipPhoneVpi", "ipPhoneVci", "iptvVpi", "iptvVci"}
_FEATURE_FIELDS = {"feature", "description", "support"}
_INT32_MIN = -(2 ** 31)
_INT32_MAX = 2 ** 31 - 1

class SiteIptvSummaryError(ValueError):
    """Raised when the IPTV setting cannot be projected safely."""

def summarize_site_iptv(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise SiteIptvSummaryError("response_invalid")
    missing = invalid = unknown = unknown_types = 0
    unknown += len(set(result) - _TOP_FIELDS)
    data: dict[str, object] = {}
    enabled = result.get("enable")
    if type(enabled) is bool:
        data["enabled"] = enabled
    else:
        data["enabled"] = None
        if "enable" not in result: missing += 1
        else: invalid += 1
    mode = result.get("mode")
    if type(mode) is int and mode in (0, 1):
        data["mode"] = "bridge" if mode == 0 else "custom"
    else:
        data["mode"] = None
        if "mode" not in result: missing += 1
        else: invalid += 1
    wan = result.get("wanPortId")
    if isinstance(wan, str):
        data["wan_port_configured"] = bool(wan.strip())
    else:
        data["wan_port_configured"] = None
        if "wanPortId" not in result: missing += 1
        else: invalid += 1
    for field, output, known in (("customConfig", "custom_vlan_configured", _CUSTOM_FIELDS),
                                 ("dslConfig", "dsl_configured", _DSL_FIELDS)):
        value = result.get(field)
        if isinstance(value, dict):
            data[output] = True
            unknown += len(set(value) - known)
            if field == "customConfig":
                for required in _CUSTOM_FIELDS:
                    raw = value.get(required)
                    if required not in value:
                        missing += 1
                    elif type(raw) is not int or not _INT32_MIN <= raw <= _INT32_MAX:
                        invalid += 1
            else:
                modulation = value.get("modulationType")
                if type(modulation) is int and modulation in (0, 1):
                    data["dsl_modulation_type"] = modulation
                elif "modulationType" not in value:
                    data["dsl_modulation_type"] = None
                    missing += 1
                else:
                    data["dsl_modulation_type"] = None
                    invalid += 1
                for optional in _DSL_FIELDS - {"modulationType"}:
                    raw = value.get(optional)
                    if optional in value and (type(raw) is not int or
                                              not _INT32_MIN <= raw <= _INT32_MAX):
                        invalid += 1
        elif value is None:
            data[output] = False if field in result else None
        else:
            data[output] = None
            invalid += 1
    ports = result.get("portConfig")
    type_counts = {"internet": 0, "iptv": 0, "ip_phone": 0}
    type_map = {1: "internet", 2: "iptv", 3: "ip_phone"}
    if isinstance(ports, list) and len(ports) <= MAX_PORTS:
        for row in ports:
            if not isinstance(row, dict):
                invalid += 1
                continue
            unknown += len(set(row) - _PORT_FIELDS)
            port_id = row.get("portId")
            if not isinstance(port_id, str) or not port_id:
                if "portId" not in row: missing += 1
                else: invalid += 1
            port_type = row.get("type")
            if type(port_type) is int and port_type in type_map:
                type_counts[type_map[port_type]] += 1
            elif type(port_type) is int:
                unknown_types += 1
            elif "type" not in row: missing += 1
            else: invalid += 1
        data["port_type_counts"] = type_counts
        data["port_count"] = len(ports)
    else:
        data["port_type_counts"] = None
        data["port_count"] = None
        if "portConfig" not in result: missing += 1
        else: invalid += 1
    features = result.get("featureDescription")
    if "featureDescription" not in result or features is None:
        data["feature_description_count"] = None
    elif isinstance(features, list) and len(features) <= MAX_FEATURE_DESCRIPTIONS and all(
            isinstance(row, dict) for row in features):
        data["feature_description_count"] = len(features)
        unknown += sum(len(set(row) - _FEATURE_FIELDS) for row in features)
    else:
        data["feature_description_count"] = None
        invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "unknown_port_type_count": unknown_types,
            "partial": bool(missing or invalid or unknown or unknown_types)}
