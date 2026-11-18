"""Redacted AP IPv6 management configuration summary."""
from __future__ import annotations


class ApIpv6SettingError(ValueError):
    """The AP IPv6 configuration exceeds the projection contract."""


_ROOT = frozenset({"ipv6Enable", "mode", "dynamicIpv6Setting", "staticIpv6Setting"})
_DYNAMIC = frozenset({"dnsMode", "priDns", "sndDns"})
_STATIC = frozenset({"ipv6Addr", "prefixLen", "defaultGate", "priDns", "sndDns"})


def summarize_ap_ipv6_setting(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ApIpv6SettingError()
    unknown = sum(1 for key in raw if key not in _ROOT)
    invalid = missing = redacted = 0
    enabled = raw.get("ipv6Enable")
    if "ipv6Enable" not in raw:
        missing += 1
    elif type(enabled) is not bool:
        invalid += 1
        enabled = None
    mode = raw.get("mode")
    if "mode" not in raw:
        if enabled is True:
            missing += 1
        mode = None
    elif mode not in ("static", "dynamic") or not isinstance(mode, str):
        invalid += 1
        mode = None

    dynamic_present = "dynamicIpv6Setting" in raw
    static_present = "staticIpv6Setting" in raw
    dns_mode = prefix_len = None
    for key, schema in (("dynamicIpv6Setting", _DYNAMIC),
                        ("staticIpv6Setting", _STATIC)):
        if key not in raw:
            if enabled is True and ((key == "dynamicIpv6Setting" and mode == "dynamic") or
                                    (key == "staticIpv6Setting" and mode == "static")):
                missing += 1
            continue
        section = raw[key]
        if not isinstance(section, dict) or len(section) > 8:
            invalid += 1
            continue
        unknown += sum(1 for field in section if field not in schema)
        if key == "dynamicIpv6Setting":
            if "dnsMode" not in section:
                missing += 1
            elif type(section["dnsMode"]) is int and section["dnsMode"] in (0, 1):
                dns_mode = section["dnsMode"]
            else:
                invalid += 1
            for field in ("priDns", "sndDns"):
                if field in section:
                    redacted += 1
                    if not isinstance(section[field], str) or len(section[field]) > 128:
                        invalid += 1
        else:
            if "ipv6Addr" not in section:
                missing += 1
            else:
                redacted += 1
                if not isinstance(section["ipv6Addr"], str) or len(section["ipv6Addr"]) > 128:
                    invalid += 1
            if "prefixLen" not in section:
                missing += 1
            elif (type(section["prefixLen"]) is int and
                  0 <= section["prefixLen"] <= 128):
                prefix_len = section["prefixLen"]
            else:
                invalid += 1
            for field in ("defaultGate", "priDns", "sndDns"):
                if field in section:
                    redacted += 1
                    if not isinstance(section[field], str) or len(section[field]) > 128:
                        invalid += 1
    partial = bool(missing or invalid or unknown)
    return {
        "status": "ok", "resource": "ap_ipv6_setting",
        "ipv6_enabled": enabled, "mode": mode,
        "dynamic_setting_present": dynamic_present,
        "static_setting_present": static_present,
        "dns_mode": dns_mode, "static_prefix_length": prefix_len,
        "redacted_address_value_count": redacted,
        "redacted_field_count": redacted,
        "unknown_field_count": unknown, "invalid_field_count": invalid,
        "missing_field_count": missing, "partial": partial,
    }
