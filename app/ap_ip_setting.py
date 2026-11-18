"""Redacted AP management-IP configuration summary."""
from __future__ import annotations


class ApIpSettingError(ValueError):
    """The AP IP configuration exceeds the projection contract."""


_ROOT = frozenset({"mode", "dhcpIpSetting", "staticIpSetting"})
_DHCP = frozenset({"fallback", "fallbackIp", "fallbackMask", "fallbackGate",
                   "useFixedAddr", "netId", "dhcpIp", "serverType", "serverMac",
                   "serverStackId"})
_STATIC = frozenset({"configIp", "configMask", "configGate", "preferredDNS",
                     "alternateDNS"})
_DHCP_SECRET = _DHCP - {"fallback", "useFixedAddr"}


def _section(value: object, fields: frozenset[str], secret_fields: frozenset[str]
             ) -> tuple[dict[str, object], int, int, int, int]:
    if not isinstance(value, dict) or len(value) > 16:
        return {}, 1, 0, 0
    output: dict[str, object] = {}
    invalid = missing = 0
    unknown = sum(1 for key in value if key not in fields)
    redacted = 0
    for key in secret_fields:
        if key in value:
            redacted += 1
            raw = value[key]
            if not isinstance(raw, str) or len(raw) > 256:
                invalid += 1
    for key in ("fallback", "useFixedAddr"):
        if key not in fields:
            continue
        if key not in value:
            continue
        if type(value[key]) is bool:
            output[key] = value[key]
        else:
            invalid += 1
    return output, invalid, missing, unknown, redacted


def summarize_ap_ip_setting(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ApIpSettingError()
    unknown = sum(1 for key in raw if key not in _ROOT)
    missing = int("mode" not in raw)
    invalid = 0
    mode = raw.get("mode")
    if mode not in ("Static", "DHCP") or not isinstance(mode, str):
        invalid += 1
        mode = None

    dhcp_present = "dhcpIpSetting" in raw
    static_present = "staticIpSetting" in raw
    dhcp_output: dict[str, object] = {}
    static_output: dict[str, object] = {}
    redacted = 0
    if dhcp_present:
        try:
            dhcp_output, bad, _, extra, private = _section(
                raw["dhcpIpSetting"], _DHCP, _DHCP_SECRET)
        except ValueError:
            raise ApIpSettingError() from None
        invalid += bad
        unknown += extra
        redacted += private
    elif mode == "DHCP":
        missing += 1
    if static_present:
        _, bad, _, extra, private = _section(raw["staticIpSetting"], _STATIC,
                                             _STATIC)
        invalid += bad
        unknown += extra
        redacted += private
    elif mode == "Static":
        missing += 1
    partial = bool(missing or invalid or unknown)
    return {
        "status": "ok", "resource": "ap_ip_setting", "mode": mode,
        "dhcp_setting_present": dhcp_present,
        "static_setting_present": static_present,
        "fallback_enabled": dhcp_output.get("fallback"),
        "reserved_address_enabled": dhcp_output.get("useFixedAddr"),
        "redacted_value_count": redacted,
        "redacted_field_count": redacted,
        "unknown_field_count": unknown, "invalid_field_count": invalid,
        "missing_field_count": missing, "partial": partial,
    }
