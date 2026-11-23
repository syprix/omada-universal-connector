"""Redacted summary of site log notification settings."""
from __future__ import annotations

from collections.abc import Mapping


class SiteLogNotificationSummaryError(ValueError):
    pass


def summarize_site_log_notifications(settings: object) -> dict[str, object]:
    if not isinstance(settings, Mapping) or len(settings) > 4:
        raise SiteLogNotificationSummaryError("settings_invalid")
    allowed = {"webhookConfig", "logNotifications", "alertEmailSetting"}
    partial = bool(set(settings) - allowed)
    channels = {key: {"enabled": 0, "disabled": 0, "unknown": 0}
                for key in ("alert", "event", "email", "webhook")}
    webhook_master = {"enabled": 0, "disabled": 0, "unknown": 0}
    email = {key: {"enabled": 0, "disabled": 0, "unknown": 0}
             for key in ("alert_email", "delay")}
    category_presence = {"key": 0, "missing_key": 0, "short_message": 0,
                         "missing_short_message": 0}
    delay_presence = {"present": 0, "missing": 0}

    def count_flag(target: dict[str, int], value: object) -> None:
        if value is None:
            target["unknown"] += 1
        elif type(value) is bool:
            target["enabled" if value else "disabled"] += 1
        else:
            raise SiteLogNotificationSummaryError("field_invalid")

    rows = settings.get("logNotifications")
    if rows is None:
        rows = []
        partial = True
    elif not isinstance(rows, list) or len(rows) > 10_000:
        raise SiteLogNotificationSummaryError("field_invalid")
    known_row = {"key", "shortMsg", "alert", "event", "email", "webhook"}
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 8:
            raise SiteLogNotificationSummaryError("row_invalid")
        if set(row) - known_row:
            partial = True
        for key, counter in (("key", "key"), ("shortMsg", "short_message")):
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 512):
                raise SiteLogNotificationSummaryError("field_invalid")
            if key in row:
                category_presence[counter] += 1
            else:
                category_presence["missing_" + counter] += 1
                partial = True
        for channel in channels:
            count_flag(channels[channel], row.get(channel))
            partial |= channel not in row

    webhook = settings.get("webhookConfig")
    if webhook is not None and (not isinstance(webhook, Mapping) or len(webhook) > 4 or
                                set(webhook) - {"webhookEnable", "webhookId"}):
        raise SiteLogNotificationSummaryError("field_invalid")
    count_flag(webhook_master,
               webhook.get("webhookEnable") if isinstance(webhook, Mapping) else None)
    partial |= not isinstance(webhook, Mapping) or "webhookEnable" not in webhook
    if isinstance(webhook, Mapping) and "webhookId" in webhook and (
            not isinstance(webhook["webhookId"], str) or len(webhook["webhookId"]) > 512):
        raise SiteLogNotificationSummaryError("field_invalid")

    email_settings = settings.get("alertEmailSetting")
    known_email = {"alertEmailEnable", "delayEnable", "delay"}
    if email_settings is not None and (not isinstance(email_settings, Mapping) or
                                       len(email_settings) > 4 or
                                       set(email_settings) - known_email):
        raise SiteLogNotificationSummaryError("field_invalid")
    count_flag(email["alert_email"], email_settings.get("alertEmailEnable")
               if isinstance(email_settings, Mapping) else None)
    partial |= not isinstance(email_settings, Mapping) or "alertEmailEnable" not in email_settings
    count_flag(email["delay"], email_settings.get("delayEnable")
               if isinstance(email_settings, Mapping) else None)
    partial |= not isinstance(email_settings, Mapping) or "delayEnable" not in email_settings
    delay = email_settings.get("delay") if isinstance(email_settings, Mapping) else None
    if delay is None:
        delay_presence["missing"] += 1
    elif type(delay) is not int or not 0 <= delay <= 99_999:
        raise SiteLogNotificationSummaryError("field_invalid")
    else:
        delay_presence["present"] += 1
    return {
        "notification_category_count": len(rows),
        "category_field_presence": category_presence,
        "channel_enablement_counts": channels,
        "webhook_master_enablement_counts": webhook_master,
        "email_setting_enablement_counts": email,
        "email_delay_value_presence": delay_presence,
        "partial": partial,
        "category_keys_messages_and_webhook_ids_returned": False,
        "external_destination_or_delivery_inferred": False,
    }
