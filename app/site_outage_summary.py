"""Compact, cautious site outage context from bounded reads."""
from __future__ import annotations

import re


_REF = re.compile(r"[0-9a-f]{24}\Z")
_DEVICE_FIELDS = {
    "access_points": ("aps_total", "aps_connected", "aps_disconnected"),
    "gateways": ("gateways_total", "gateways_connected", "gateways_disconnected"),
    "switches": ("switches_total", "switches_connected", "switches_disconnected"),
}
_KNOWN_OVERVIEW_FIELDS = {field for fields in _DEVICE_FIELDS.values() for field in fields}
_KNOWN_OVERVIEW_FIELDS.update({
    "aps_isolated", "clients_total", "clients_wired", "clients_wireless", "clients_guest",
    "ports_total", "ports_available", "network_capacity_mbps", "network_usage_percent",
    "power_consumption_w",
})


class SiteOutageSummaryError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _log_summary(value: object, resource: str, site_ref: str,
                 start_ms: int, end_ms: int) -> dict[str, object]:
    if (not isinstance(value, dict) or value.get("status") != "ok" or
            value.get("resource") != resource or value.get("site_ref") != site_ref or
            value.get("window_start_ms") != start_ms or
            value.get("window_end_ms") != end_ms):
        raise SiteOutageSummaryError("log_window_unavailable")
    total, returned = value.get("total_count"), value.get("returned_count")
    partial = value.get("partial")
    modules = value.get("module_counts")
    pagination = value.get("pagination")
    pages_fetched = pagination.get("pages_fetched") if isinstance(pagination, dict) else None
    page_size = pagination.get("page_size") if isinstance(pagination, dict) else None
    page_limit = pagination.get("page_limit") if isinstance(pagination, dict) else None
    page_limit_reached = pagination.get("page_limit_reached") if isinstance(pagination, dict) else None
    if (type(total) is not int or total < 0 or type(returned) is not int or
            not 0 <= returned <= total or type(partial) is not bool or
            partial != (returned < total) or not isinstance(modules, dict) or
            len(modules) > 8 or any(not isinstance(key, str) or len(key) > 32 or
                                    type(count) is not int or count < 0
                                    for key, count in modules.items()) or
            sum(modules.values()) != returned or
            not isinstance(pagination, dict) or
            type(pages_fetched) is not int or pages_fetched < 0 or
            type(page_size) is not int or page_size < 1 or
            type(page_limit) is not int or page_limit < 1 or
            type(page_limit_reached) is not bool or
            page_limit_reached != partial):
        raise SiteOutageSummaryError("log_window_invalid")
    clean: dict[str, object] = {
        "status": "partial" if partial else "ok", "total_count": total,
        "returned_count": returned, "module_counts": dict(modules),
        "pagination": {
            key: pagination.get(key) for key in
            ("pages_fetched", "page_size", "page_limit", "page_limit_reached")
        },
        "partial": partial,
    }
    for key in ("first_event_ms", "last_event_ms"):
        timestamp = value.get(key)
        if timestamp is not None:
            if type(timestamp) is not int or not start_ms <= timestamp <= end_ms:
                raise SiteOutageSummaryError("log_window_invalid")
            clean[key] = timestamp
    if resource.endswith("alerts_window_summary"):
        severity = value.get("severity_counts")
        if (not isinstance(severity, dict) or len(severity) > 8 or
                any(not isinstance(key, str) or len(key) > 32 or
                    type(count) is not int or count < 0
                    for key, count in severity.items()) or
                sum(severity.values()) != returned):
            raise SiteOutageSummaryError("log_window_invalid")
        clean["severity_counts"] = dict(severity)
    return clean


def _reachability(value: object, site_ref: str) -> tuple[dict[str, object], bool]:
    if (not isinstance(value, dict) or value.get("status") != "ok" or
            value.get("resource") != "site_overview" or value.get("site_ref") != site_ref or
            not isinstance(value.get("data"), dict)):
        return {"status": "unavailable"}, True
    raw = value["data"]
    if len(raw) > 128:
        raise SiteOutageSummaryError("overview_invalid")
    reachability: dict[str, object] = {"status": "ok", "device_classes": {}}
    partial = False
    for name, fields in _DEVICE_FIELDS.items():
        item: dict[str, int | None] = {}
        for output_key, source_key in zip(("total", "connected", "disconnected"), fields):
            count = raw.get(source_key)
            if count is None:
                item[output_key] = None
                partial = True
            elif type(count) is int and 0 <= count <= 1_000_000_000:
                item[output_key] = count
            else:
                raise SiteOutageSummaryError("overview_invalid")
        total, connected, disconnected = item["total"], item["connected"], item["disconnected"]
        if (type(total) is int and type(connected) is int and type(disconnected) is int and
                connected + disconnected > total):
            raise SiteOutageSummaryError("overview_invalid")
        reachability["device_classes"][name] = item
    isolated = raw.get("aps_isolated")
    if isolated is None:
        reachability["isolated_access_points"] = None
        partial = True
    elif type(isolated) is int and isolated >= 0:
        reachability["isolated_access_points"] = isolated
    else:
        raise SiteOutageSummaryError("overview_invalid")
    unknown_fields = set(raw) - _KNOWN_OVERVIEW_FIELDS
    if unknown_fields:
        partial = True
    reachability["partial"] = partial
    reachability["missing_field_count"] = sum(
        item[key] is None for item in reachability["device_classes"].values()
        for key in ("total", "connected", "disconnected")) + int(isolated is None)
    return reachability, partial


def project_site_outage_summary(site_ref: str, start_ms: int, end_ms: int,
                                overview: object, events: object,
                                alerts: object, observed_at_ms: int | None) -> dict[str, object]:
    if (not isinstance(site_ref, str) or not _REF.fullmatch(site_ref) or
            type(start_ms) is not int or type(end_ms) is not int or
            start_ms > end_ms or
            (observed_at_ms is not None and
             (type(observed_at_ms) is not int or observed_at_ms < 0))):
        raise SiteOutageSummaryError("arguments_invalid")
    reachability, reachability_partial = _reachability(overview, site_ref)
    sections: dict[str, object] = {"current_reachability": reachability}
    partial = reachability_partial
    for name, value, resource in (
        ("events", events, "site_events_window_summary"),
        ("alerts", alerts, "site_alerts_window_summary"),
    ):
        try:
            summary = _log_summary(value, resource, site_ref, start_ms, end_ms)
            sections[name] = summary
            partial = partial or summary["partial"] is True
        except SiteOutageSummaryError:
            sections[name] = {"status": "unavailable", "partial": True}
            partial = True

    return {
        "status": "partial" if partial else "ok",
        "resource": "site_outage_summary",
        "site_ref": site_ref,
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "reachability_observed_at_ms": observed_at_ms,
        "sections": sections,
        "scope_assessment": {
            "status": "indeterminate",
            "notes": [
                "Device reachability is a current snapshot and may be outside the requested log window.",
                "Event and alert counts are not correlated to individual devices or a cause.",
                "A site-wide outage cannot be confirmed from these summaries alone.",
            ],
        },
        "partial": partial,
    }
