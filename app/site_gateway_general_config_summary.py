"""Redacted counts for documented gateway general settings."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_gateway_general_config(result: object) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("input_invalid")
    value = result.get("ledSetting")
    if "ledSetting" not in result or value is None:
        led = "missing"
    elif type(value) is int and value in (0, 1, 2):
        led = ("off", "on", "site_settings")[value]
    elif type(value) is int:
        led = "unknown"
    else:
        led = "invalid"

    raw_remember = result.get("rememberDevice")
    if "rememberDevice" not in result or raw_remember is None:
        remember = "missing"
    elif type(raw_remember) is int:
        remember = "present"
    else:
        remember = "invalid"

    raw_snmp = result.get("snmp")
    if "snmp" not in result or raw_snmp is None:
        snmp = "missing"
    elif isinstance(raw_snmp, Mapping):
        snmp = "present"
    else:
        snmp = "invalid"

    partial = led in ("missing", "invalid", "unknown") or remember != "present" or snmp != "present"
    return {
        "status": "partial" if partial else "ok",
        "resource": "gateway_general_config_summary",
        "led": led,
        "remember_device": "present_uninterpreted" if remember == "present" else remember,
        "snmp": "present_redacted" if snmp == "present" else snmp,
        "partial": partial,
    }
