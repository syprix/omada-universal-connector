"""Redacted site remote-logging configuration summary."""
from __future__ import annotations

from typing import Any


class SiteRemoteLoggingSummaryError(ValueError):
    pass


RESOURCE_SOURCES = {0: "new_created", 1: "template", 2: "override"}
ALLOWED_FIELDS = {"enable", "host", "port", "moreClientLog", "resource"}


def summarize_site_remote_logging(remote_log: Any) -> dict[str, object]:
    if not isinstance(remote_log, dict) or len(remote_log) > len(ALLOWED_FIELDS):
        raise SiteRemoteLoggingSummaryError("response_invalid")
    unknown = len(set(remote_log) - ALLOWED_FIELDS)
    enabled = remote_log.get("enable")
    if not isinstance(enabled, bool):
        raise SiteRemoteLoggingSummaryError("response_invalid")
    missing = 0
    client_logs = remote_log.get("moreClientLog")
    if client_logs is not None and not isinstance(client_logs, bool):
        missing += 1
        client_logs = None
    resource = remote_log.get("resource")
    resource_source = RESOURCE_SOURCES.get(resource) if type(resource) is int else None
    if resource is not None and resource_source is None:
        missing += 1
    host = remote_log.get("host")
    if host is not None and not isinstance(host, str):
        missing += 1
        host = None
    port = remote_log.get("port")
    if port is not None and (type(port) is not int or not 1 <= port <= 65535):
        missing += 1
        port = None
    return {
        "status": "ok", "resource": "site_remote_logging_summary",
        "enabled": enabled, "client_logs_enabled": client_logs,
        "resource_source": resource_source,
        "destination_host_configured": bool(host),
        "destination_port_configured": port is not None,
        "destination_values_returned": False,
        "missing_or_invalid_optional_field_count": missing,
        "unknown_field_count": unknown,
        "partial": bool(missing or unknown),
        "delivery_success": "not assessed",
    }
