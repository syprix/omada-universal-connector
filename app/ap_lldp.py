"""Redacted projection for the documented AP LLDP configuration read."""
from __future__ import annotations


class ApLldpError(ValueError):
    """The AP LLDP response is malformed or outside the documented shape."""


_LLDP_SETTINGS = {0: "off", 1: "on", 2: "site_default"}
_FIELDS = frozenset({"lldpEnable", "supportLldp"})


def project_ap_lldp(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ApLldpError()
    setting_code = raw.get("lldpEnable")
    support = raw.get("supportLldp")
    missing = int("lldpEnable" not in raw) + int("supportLldp" not in raw)
    invalid = 0
    if "lldpEnable" in raw and (type(setting_code) is not int or setting_code not in _LLDP_SETTINGS):
        invalid += 1
    if "supportLldp" in raw and type(support) is not bool:
        invalid += 1
    unknown = sum(1 for key in raw if key not in _FIELDS)
    data: dict[str, object] = {}
    if type(setting_code) is int and setting_code in _LLDP_SETTINGS:
        data["setting_code"] = setting_code
        data["setting"] = _LLDP_SETTINGS[setting_code]
    if type(support) is bool:
        data["supported"] = support
    return {
        "status": "ok",
        "resource": "ap_lldp_config",
        "data": data,
        "partial": bool(missing or invalid or unknown),
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
    }
