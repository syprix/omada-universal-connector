"""Redacted summary of site log notification settings."""
from __future__ import annotations

from collections.abc import Mapping


class SiteLogNotificationSummaryError(ValueError):
    pass


def summarize_site_log_notifications(settings: object) -> dict[str, object]:
    if not isinstance(settings, Mapping) or len(settings) > 8:
        raise SiteLogNotificationSummaryError("settings_invalid")
    allowed = {"webhookConfig", "logNotifications", "alertEmailSetting",
               "eventEmailSetting", "alertNotifications", "eventNotifications"}
    partial = bool(set(settings) - allowed)
    channels = {key: {"enabled": 0, "disabled": 0, "unknown": 0}
                for key in ("alert", "event", "email", "webhook")}
    webhook_master = {"enabled": 0, "disabled": 0, "unknown": 0}
    email = {key: {"enabled": 0, "disabled": 0, "unknown": 0}
             for key in ("alert_email", "event_email", "delay")}
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

    modern_rows = "alertNotifications" in settings or "eventNotifications" in settings
    category_rows: list[tuple[str | None, object]] = []
    if modern_rows:
        for channel, field in (("alert", "alertNotifications"),
                               ("event", "eventNotifications")):
            rows = settings.get(field)
            if rows is None:
                rows = []
                partial = True
            elif not isinstance(rows, list) or len(rows) > 10_000:
                raise SiteLogNotificationSummaryError("field_invalid")
            category_rows.append((channel, rows))
    else:
        rows = settings.get("logNotifications")
        if rows is None:
            rows = []
            partial = True
        elif not isinstance(rows, list) or len(rows) > 10_000:
            raise SiteLogNotificationSummaryError("field_invalid")
        category_rows.append((None, rows))

    category_count = 0
    for category_channel, category_value in category_rows:
        if not isinstance(category_value, list):
            raise SiteLogNotificationSummaryError("field_invalid")
        category_count += len(category_value)
        known_row = ({"key", "shortMsg", "enable", "email", "webhook"}
                     if modern_rows else
                     {"key", "shortMsg", "alert", "event", "email", "webhook"})
        for row in category_value:
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
            if modern_rows:
                assert category_channel is not None
                count_flag(channels[category_channel], row.get("enable"))
                partial |= "enable" not in row
                for channel in ("email", "webhook"):
                    count_flag(channels[channel], row.get(channel))
                    partial |= channel not in row
            else:
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
    email_settings_by_kind = [("alert_email", email_settings)]
    if modern_rows:
        email_settings_by_kind.append(("event_email", settings.get("eventEmailSetting")))
    for kind, item in email_settings_by_kind:
        if item is not None and (not isinstance(item, Mapping) or len(item) > 4 or
                                 set(item) - known_email):
            raise SiteLogNotificationSummaryError("field_invalid")
        count_flag(email[kind], item.get("alertEmailEnable")
                   if isinstance(item, Mapping) else None)
        partial |= not isinstance(item, Mapping) or "alertEmailEnable" not in item
        count_flag(email["delay"], item.get("delayEnable")
                   if isinstance(item, Mapping) else None)
        partial |= not isinstance(item, Mapping) or "delayEnable" not in item
        delay = item.get("delay") if isinstance(item, Mapping) else None
        if delay is None:
            delay_presence["missing"] += 1
        elif type(delay) is not int or not 0 <= delay <= 99_999:
            raise SiteLogNotificationSummaryError("field_invalid")
        else:
            delay_presence["present"] += 1
    return {
        "notification_category_count": category_count,
        "category_field_presence": category_presence,
        "channel_enablement_counts": channels,
        "webhook_master_enablement_counts": webhook_master,
        "email_setting_enablement_counts": email,
        "email_delay_value_presence": delay_presence,
        "partial": partial,
        "category_keys_messages_and_webhook_ids_returned": False,
        "external_destination_or_delivery_inferred": False,
    }
