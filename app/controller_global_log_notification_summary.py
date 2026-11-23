"""Redacted projection of controller-wide log notification settings."""
from __future__ import annotations

from collections.abc import Mapping


class ControllerGlobalLogNotificationError(ValueError):
    pass


def summarize_controller_log_notifications(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 8:
        raise ControllerGlobalLogNotificationError("invalid settings")
    allowed = {"webhookConfig", "logNotifications", "alertEmailSetting"}
    unknown = sum(key not in allowed for key in value)
    invalid = 0
    webhook = value.get("webhookConfig")
    webhook_present = isinstance(webhook, Mapping)
    webhook_enabled: bool | None = None
    if webhook_present:
        if len(webhook) > 8:
            raise ControllerGlobalLogNotificationError("invalid webhook settings")
        unknown += sum(key not in {"webhookEnable", "webhookId"} for key in webhook)
        candidate = webhook.get("webhookEnable")
        if type(candidate) is bool:
            webhook_enabled = candidate
        elif candidate is not None:
            invalid += 1
    elif webhook is not None:
        invalid += 1

    notifications = value.get("logNotifications")
    if not isinstance(notifications, list) or len(notifications) > 10_000:
        raise ControllerGlobalLogNotificationError("invalid notification list")
    keys = {"key", "shortMsg", "alert", "event", "email", "webhook"}
    channel_counts = {name: {"enabled": 0, "disabled": 0, "missing": 0}
                      for name in ("alert", "event", "email", "webhook")}
    invalid_rows = missing_values = 0
    for row in notifications:
        if not isinstance(row, Mapping) or len(row) > 12:
            invalid_rows += 1
            continue
        unknown += sum(key not in keys for key in row)
        for channel, counts in channel_counts.items():
            state = row.get(channel)
            if type(state) is bool:
                counts["enabled" if state else "disabled"] += 1
            elif state is None:
                counts["missing"] += 1
                missing_values += 1
            else:
                invalid += 1

    alert = value.get("alertEmailSetting")
    alert_present = isinstance(alert, Mapping)
    alert_states: dict[str, bool | None] = {"alert_email_enabled": None,
                                            "delay_email_enabled": None}
    delay_present = False
    if alert_present:
        if len(alert) > 8:
            raise ControllerGlobalLogNotificationError("invalid alert settings")
        unknown += sum(key not in {"alertEmailEnable", "delayEnable", "delay"}
                       for key in alert)
        for source, target in (("alertEmailEnable", "alert_email_enabled"),
                               ("delayEnable", "delay_email_enabled")):
            state = alert.get(source)
            if type(state) is bool:
                alert_states[target] = state
            elif state is not None:
                invalid += 1
        delay = alert.get("delay")
        delay_present = type(delay) is int and 0 <= delay <= 99_999
        if delay is not None and not delay_present:
            invalid += 1
    elif alert is not None:
        invalid += 1

    return {
        "status": "ok", "resource": "controller_global_log_notification_summary",
        "notification_category_count": len(notifications),
        "channel_switch_counts": channel_counts,
        "webhook_configuration_present": webhook_present,
        "webhook_enabled": webhook_enabled,
        "alert_email_configuration_present": alert_present,
        **alert_states,
        "alert_email_delay_value_present": delay_present,
        "invalid_record_count": invalid_rows,
        "invalid_field_count": invalid,
        "missing_channel_value_count": missing_values,
        "unknown_field_count": unknown,
        "partial": bool(invalid_rows or invalid or missing_values or unknown or
                         not webhook_present or not alert_present),
    }
