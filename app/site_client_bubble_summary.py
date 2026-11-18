"""Redacted traffic and radio-quality aggregates for the site client list."""
from __future__ import annotations

from typing import Any


class SiteClientBubbleSummaryError(ValueError):
    """Raised when the unpaged client bubble response is malformed or oversized."""


_FIELDS = {
    "name", "type", "mac", "apName", "traffic", "trafficPercent", "upload",
    "uploadPercent", "download", "downloadPercent", "healthScore", "txRate",
    "snr", "wifiProtocol", "rssi", "signalLevel", "channel", "radioId",
    "bandWidth", "incidents",
}
_TEXT_FIELDS = {"name", "type", "mac", "apName", "wifiProtocol"}
_INT64_FIELDS = {"traffic", "upload", "download", "txRate"}
_INT32_FIELDS = {
    "trafficPercent", "uploadPercent", "downloadPercent", "healthScore", "snr",
    "rssi", "signalLevel", "channel", "radioId", "bandWidth", "incidents",
}
_MAX_ROWS = 1_000
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def project_site_client_bubble_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteClientBubbleSummaryError("response_invalid")
    metrics: dict[str, list[int]] = {
        key: [] for key in ("traffic", "upload", "download", "rssi", "snr", "healthScore")
    }
    missing = invalid = unknown = 0
    aggregate_complete = {key: True for key in metrics}
    for row in result:
        if not isinstance(row, dict) or len(row) > 25:
            invalid += 1
            for key in aggregate_complete:
                aggregate_complete[key] = False
            continue
        unknown += len(set(row) - _FIELDS)
        for key in _TEXT_FIELDS:
            if key in row and not isinstance(row[key], str):
                invalid += 1
        for key in _INT64_FIELDS | _INT32_FIELDS:
            if key not in row:
                continue
            value = row[key]
            upper = _INT64_MAX if key in _INT64_FIELDS else _INT32_MAX
            if type(value) is not int or not -upper - 1 <= value <= upper:
                invalid += 1
        for key in metrics:
            if key not in row:
                missing += 1
                aggregate_complete[key] = False
            elif type(row[key]) is not int:
                aggregate_complete[key] = False
            elif key in _INT64_FIELDS and not 0 <= row[key] <= _INT64_MAX:
                aggregate_complete[key] = False
            elif key in _INT32_FIELDS and not -_INT32_MAX - 1 <= row[key] <= _INT32_MAX:
                aggregate_complete[key] = False
            else:
                metrics[key].append(row[key])

    def complete(key: str) -> bool:
        return aggregate_complete[key] and len(metrics[key]) == len(result)

    data: dict[str, object] = {
        "client_count": len(result),
        "total_client_traffic_value": (sum(metrics["traffic"])
                                       if complete("traffic") else None),
        "total_client_upload_value": (sum(metrics["upload"])
                                      if complete("upload") else None),
        "total_client_download_value": (sum(metrics["download"])
                                        if complete("download") else None),
        "average_client_rssi_value": (sum(metrics["rssi"]) / len(result)
                                      if result and complete("rssi") else None),
        "minimum_client_rssi_value": (min(metrics["rssi"])
                                      if result and complete("rssi") else None),
        "maximum_client_rssi_value": (max(metrics["rssi"])
                                      if result and complete("rssi") else None),
        "average_client_snr_value": (sum(metrics["snr"]) / len(result)
                                     if result and complete("snr") else None),
        "average_client_health_score_value": (sum(metrics["healthScore"]) / len(result)
                                               if result and complete("healthScore") else None),
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
    }
    partial = bool(missing or invalid or unknown or
                   not all(aggregate_complete.values()))
    return {"data": data, "partial": partial}
