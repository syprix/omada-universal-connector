"""Bounded, identity-safe projection for site incident notification settings."""
from __future__ import annotations

from typing import Any


MAX_INT32 = 2_147_483_647
MAX_MAP_ENTRIES = 64
MAX_RECIPIENTS = 100
MAX_FIELD_LENGTH = 254

EVENT_LEVELS = ("critical", "error", "warning", "info")
EVENT_OBJECT_TYPES = ("gateway", "switch", "ap", "wiredClient", "wirelessClient")
EVENT_CATEGORIES = (
    "networking", "mesh", "access", "roaming", "networkService", "software",
    "hardware", "security", "throughput", "cover",
)


class SiteIncidentNotificationError(ValueError):
    """Raised when the notification response cannot be safely summarized."""


def _flag_map(value: Any, allowed: tuple[str, ...], counts: dict[str, int]) -> dict[str, bool] | None:
    if not isinstance(value, dict) or len(value) > MAX_MAP_ENTRIES:
        counts["invalid_count"] += 1
        return None
    out: dict[str, bool] = {}
    for key, enabled in value.items():
        if key not in allowed:
            counts["unknown_field_count"] += 1
        elif type(enabled) is not bool:
            counts["invalid_count"] += 1
        else:
            out[key] = enabled
    return dict(sorted(out.items()))


def project_site_incident_notification(result: Any) -> dict[str, object]:
    """Normalize the three documented response variants without returning addresses."""
    if not isinstance(result, dict) or len(result) > 16:
        raise SiteIncidentNotificationError("response_invalid")

    counts = {"invalid_count": 0, "unknown_field_count": 0}
    data: dict[str, object] = {}
    known_top = {"alertEmailSetting", "email", "Email Alerts", "resource", "recipients"}
    counts["unknown_field_count"] += len(set(result) - known_top)

    resource = result.get("resource")
    if "resource" in result:
        if type(resource) is int and 0 <= resource <= 2:
            data["resource_code"] = resource
        else:
            counts["invalid_count"] += 1

    alert = result.get("alertEmailSetting")
    if "alertEmailSetting" in result:
        if not isinstance(alert, dict) or len(alert) > 8:
            counts["invalid_count"] += 1
        else:
            safe_alert: dict[str, object] = {}
            recognized_alert = {"alertEmailEnable", "delayEnable", "delay"}
            counts["unknown_field_count"] += len(set(alert) - recognized_alert)
            for source, target in (("alertEmailEnable", "enabled"),
                                   ("delayEnable", "delay_enabled")):
                if source in alert:
                    if type(alert[source]) is bool:
                        safe_alert[target] = alert[source]
                    else:
                        counts["invalid_count"] += 1
            if "delay" in alert:
                value = alert["delay"]
                if type(value) is int and 1 <= value <= MAX_INT32:
                    safe_alert["delay_seconds"] = value
                else:
                    counts["invalid_count"] += 1
            data["alert_email_setting"] = safe_alert

    config_keys = [key for key in ("email", "Email Alerts") if key in result]
    if len(config_keys) > 1:
        counts["unknown_field_count"] += 1
    if config_keys:
        config = result[config_keys[0]]
        if not isinstance(config, dict) or len(config) > 8:
            counts["invalid_count"] += 1
        else:
            counts["unknown_field_count"] += len(
                set(config) - {"eventLevel", "eventObjectType", "eventCategory"})
            event_data: dict[str, object] = {}
            for source, target, allowed in (
                ("eventLevel", "level_flags", EVENT_LEVELS),
                ("eventObjectType", "object_type_flags", EVENT_OBJECT_TYPES),
            ):
                if source not in config:
                    counts["invalid_count"] += 1
                    continue
                projected = _flag_map(config[source], allowed, counts)
                if projected is not None:
                    event_data[target] = projected

            if "eventCategory" not in config:
                counts["invalid_count"] += 1
            else:
                category = config["eventCategory"]
                if isinstance(category, dict):
                    projected = _flag_map(category, EVENT_CATEGORIES, counts)
                    if projected is not None:
                        event_data["category_flags"] = projected
                        event_data["category_mode"] = "flags"
                elif isinstance(category, str) and category in EVENT_CATEGORIES:
                    # ER7212PC documents an object but its example uses a single
                    # category string. Preserve that documented variant explicitly.
                    event_data["category_flags"] = {category: True}
                    event_data["category_mode"] = "single_key"
                else:
                    counts["invalid_count"] += 1
            data["event_notifications"] = event_data

    if "recipients" in result:
        recipients = result["recipients"]
        if not isinstance(recipients, list) or len(recipients) > MAX_RECIPIENTS:
            counts["invalid_count"] += 1
        else:
            valid_count = 0
            for item in recipients:
                if (not isinstance(item, dict) or len(item) > 4 or
                        not isinstance(item.get("email"), str) or
                        not 1 <= len(item["email"]) <= MAX_FIELD_LENGTH or
                        any(ord(char) < 0x20 or ord(char) == 0x7f for char in item["email"])):
                    counts["invalid_count"] += 1
                    continue
                valid_count += 1
                counts["unknown_field_count"] += len(set(item) - {"email"})
            data["recipient_count"] = valid_count

    data.update(counts)
    present_count = sum(key in data for key in (
        "resource_code", "alert_email_setting", "event_notifications", "recipient_count"))
    data["present_count"] = present_count
    return {
        "data": data,
        "partial": bool(counts["invalid_count"] or counts["unknown_field_count"]),
    }
