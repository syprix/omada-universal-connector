"""Redacted settings summary for a uniquely inventoried Agile switch."""
from __future__ import annotations

from collections.abc import Mapping


class AgileSwitchConfigError(ValueError):
    pass


_FIELDS = frozenset(("name", "ledSetting", "tagIds", "jumboEnable", "location",
                     "remember", "supportPowerAlert", "powerAlertEnable"))


def summarize_agile_switch_config(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 32:
        raise AgileSwitchConfigError("result_invalid")

    unknown = sum(key not in _FIELDS for key in value)
    led_value = value.get("ledSetting")
    led_code: int | None = None
    led_name = "unknown"
    partial = unknown > 0
    if led_value is None:
        partial = True
    elif type(led_value) is not int or not 0 <= led_value < (1 << 31):
        raise AgileSwitchConfigError("led_setting_invalid")
    else:
        led_code = led_value
        led_name = {0: "off", 1: "on", 2: "site_setting"}.get(led_value, "unknown")
        partial |= led_name == "unknown"

    booleans: dict[str, bool | None] = {}
    for source, output in (("jumboEnable", "jumbo_frames_enabled"),
                           ("supportPowerAlert", "power_alert_supported"),
                           ("powerAlertEnable", "power_alert_enabled")):
        raw = value.get(source)
        if raw is None:
            booleans[output] = None
            partial = True
        elif type(raw) is not bool:
            raise AgileSwitchConfigError("boolean_setting_invalid")
        else:
            booleans[output] = raw

    return {
        "led_setting": led_name,
        "led_setting_code": led_code,
        **booleans,
        "unknown_field_count": unknown,
        "partial": partial,
        "device_name_location_tags_and_other_settings_returned": False,
    }
