"""Redacted counts for documented standard-switch general settings."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


LED_MODES = ("off", "on", "site_settings")
LAG_MODES = ("src_mac", "dst_mac", "src_mac_and_dst_mac",
             "src_ip", "dst_ip", "src_ip_and_dst_ip")


def _presence(value: object, *, present: bool, valid: bool) -> str:
    if not present or value is None:
        return "missing"
    return "present" if valid else "invalid"


def summarize_switch_general_config(result: object) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("input_invalid")

    value = result.get("ledSetting")
    if "ledSetting" not in result or value is None:
        led = "missing"
    elif type(value) is int and value in (0, 1, 2):
        led = LED_MODES[value]
    elif type(value) is int:
        led = "unknown"
    else:
        led = "invalid"

    follow_site = {}
    for field in ("jumboFollowSite", "lagHashAlgFollowSite"):
        value = result.get(field)
        if field not in result or value is None:
            state = "missing"
        elif type(value) is bool:
            state = "follows_site" if value else "device_specific"
        else:
            state = "invalid"
        follow_site[field] = state

    value = result.get("jumbo")
    if "jumbo" not in result or value is None:
        jumbo = "missing"
    elif type(value) is int and 1518 <= value <= 9216:
        jumbo = "within_documented_range"
    else:
        jumbo = "invalid"

    value = result.get("lagHashAlg")
    if "lagHashAlg" not in result or value is None:
        lag = "missing"
    elif type(value) is int and 0 <= value < len(LAG_MODES):
        lag = LAG_MODES[value]
    elif type(value) is int:
        lag = "unknown"
    else:
        lag = "invalid"

    sdm = _presence(result.get("sdm"), present="sdm" in result,
                    valid=isinstance(result.get("sdm"), Mapping))
    partial = bool(led in ("unknown", "missing", "invalid") or
                   any(value in ("missing", "invalid") for value in follow_site.values()) or
                   jumbo in ("missing", "invalid") or lag in ("unknown", "missing", "invalid") or
                   sdm != "present")
    jumbo_source = follow_site["jumboFollowSite"]
    lag_source = follow_site["lagHashAlgFollowSite"]
    jumbo_summary = f"{jumbo_source}_{'valid' if jumbo == 'within_documented_range' else jumbo}"
    lag_summary = f"{lag_source}_{lag}"
    return {
        "status": "partial" if partial else "ok",
        "resource": "switch_general_config_summary",
        "led": led,
        "jumbo": jumbo_summary,
        "lag_hash": lag_summary,
        "sdm": sdm,
        "partial": partial,
    }
