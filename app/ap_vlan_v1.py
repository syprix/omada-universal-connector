"""Redacted projection for the distinct AP VLAN v1 route."""
from __future__ import annotations


class ApVlanV1Error(ValueError):
    """The documented v1 AP VLAN response is invalid or over its bounds."""


_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def summarize_ap_vlan_v1(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ApVlanV1Error()
    invalid = missing = redacted = unknown = 0

    mode = raw.get("mode")
    if "mode" not in raw:
        missing += 1
        mode = None
    elif type(mode) is not int or mode not in (0, 1):
        invalid += 1
        mode = None

    bridge_present = False
    if "bridgeVlan" in raw:
        value = raw["bridgeVlan"]
        if type(value) is int and _INT32_MIN <= value <= _INT32_MAX:
            bridge_present = True
        else:
            invalid += 1

    network_present = False
    if "lanNetworkId" in raw:
        redacted += 1
        value = raw["lanNetworkId"]
        if isinstance(value, str) and len(value) <= 1024:
            network_present = bool(value)
        else:
            invalid += 1

    unknown = sum(1 for field in raw if field not in {"mode", "bridgeVlan", "lanNetworkId"})
    return {
        "status": "ok", "resource": "ap_vlan_v1", "mode_code": mode,
        "bridge_vlan_present": bridge_present,
        "network_binding_present": network_present,
        "redacted_field_count": redacted, "unknown_field_count": unknown,
        "invalid_field_count": invalid, "missing_field_count": missing,
        "partial": bool(invalid or missing or unknown),
    }
