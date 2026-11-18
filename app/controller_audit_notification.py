"""Redacted projection for global audit-log notification settings."""
from __future__ import annotations

import re
from typing import Any


MAX_ITEMS = 256
_KEY = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class ControllerAuditNotificationError(ValueError):
    """Raised when the notification response exceeds safe bounds."""


def project_controller_audit_notification(result: Any) -> dict[str, object]:
    """Return category counts and flags; omit webhook IDs and display labels."""
    if not isinstance(result, dict) or len(result) > 8:
        raise ControllerAuditNotificationError("response_invalid")

    invalid_count = 0
    unknown_field_count = len(set(result) - {"webhookConfig", "auditLogNotifications"})
    omitted_label_count = 0
    data: dict[str, object] = {}

    config = result.get("webhookConfig")
    if "webhookConfig" not in result:
        invalid_count += 1
    elif not isinstance(config, dict) or len(config) > 8:
        invalid_count += 1
    else:
        unknown_field_count += len(set(config) - {"webhookEnable", "webhookId"})
        config_data: dict[str, object] = {}
        if type(config.get("webhookEnable")) is bool:
            config_data["enabled"] = config["webhookEnable"]
        else:
            invalid_count += 1
        if "webhookId" in config:
            if isinstance(config["webhookId"], str) and len(config["webhookId"]) <= 256:
                config_data["webhook_id_present"] = bool(config["webhookId"])
            else:
                invalid_count += 1
        else:
            config_data["webhook_id_present"] = False
        data["webhook"] = config_data

    rows = result.get("auditLogNotifications")
    if not isinstance(rows, list) or len(rows) > MAX_ITEMS:
        invalid_count += 1
        rows = []
    enabled_count = 0
    valid_count = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 8:
            invalid_count += 1
            continue
        unknown_field_count += len(set(row) - {"key", "shortMsg", "webhook"})
        key = row.get("key")
        enabled = row.get("webhook")
        if not isinstance(key, str) or not _KEY.fullmatch(key) or type(enabled) is not bool:
            invalid_count += 1
            continue
        valid_count += 1
        enabled_count += int(enabled)
        if "shortMsg" in row:
            if isinstance(row["shortMsg"], str) and len(row["shortMsg"]) <= 256:
                omitted_label_count += 1
            else:
                invalid_count += 1

    data.update({
        "category_count": valid_count,
        "enabled_category_count": enabled_count,
        "omitted_label_count": omitted_label_count,
        "invalid_count": invalid_count,
        "unknown_field_count": unknown_field_count,
    })
    return {
        "data": data,
        "partial": bool(invalid_count or unknown_field_count),
    }
