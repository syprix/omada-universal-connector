"""Bounded identity-redacted summaries for incident-influencing inventories."""
from __future__ import annotations

from typing import Any


MAX_ROWS = 100
MAX_INT32 = 2_147_483_647


class SiteIncidentInfluencesError(ValueError):
    """Raised when an upstream influence page cannot be safely summarized."""


def project_site_incident_influences(result: Any, kind: str,
                                     entity_refs_by_mac: dict[str, str]) -> dict[str, object]:
    """Return opaque inventory references and diagnostic flags, never identity fields."""
    if kind not in {"clients", "devices"}:
        raise SiteIncidentInfluencesError("kind_invalid")
    if not isinstance(result, dict) or len(result) > 12:
        raise SiteIncidentInfluencesError("response_invalid")
    counts = {"invalid_count": 0, "unknown_field_count": 0,
              "unmapped_identity_count": 0}
    data: dict[str, object] = {}
    for source, target, maximum in (("totalRows", "total_rows", 9_223_372_036_854_775_807),
                                    ("currentPage", "current_page", MAX_INT32),
                                    ("currentSize", "current_size", MAX_INT32)):
        if source in result:
            value = result[source]
            minimum = 1 if source != "totalRows" else 0
            if type(value) is int and minimum <= value <= maximum:
                data[target] = value
            else:
                counts["invalid_count"] += 1
    rows = result.get("data")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise SiteIncidentInfluencesError("response_invalid")
    items: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict) or len(row) > 24:
            counts["invalid_count"] += 1
            continue
        common = {"mac", "ip", "deviceName", "clientName", "clientType", "model",
                  "modelVersion", "deviceType", "status", "health", "manager",
                  "active", "authStatus"}
        counts["unknown_field_count"] += len(set(row) - common)
        item: dict[str, object] = {}
        mac = row.get("mac")
        if not isinstance(mac, str) or len(mac) > 32:
            counts["invalid_count"] += 1
        else:
            entity_ref = entity_refs_by_mac.get(mac.lower())
            if entity_ref and len(entity_ref) == 24:
                item["client_ref" if kind == "clients" else "device_ref"] = entity_ref
            else:
                counts["unmapped_identity_count"] += 1
        if kind == "clients":
            for source, target in (("active", "active"), ("manager", "managing_host")):
                if source in row:
                    if type(row[source]) is bool:
                        item[target] = row[source]
                    else:
                        counts["invalid_count"] += 1
            if "authStatus" in row:
                value = row["authStatus"]
                if type(value) is int and 0 <= value <= 4:
                    item["auth_status_code"] = value
                else:
                    counts["invalid_count"] += 1
        elif "status" in row:
            value = row["status"]
            if type(value) is int and 0 <= value <= MAX_INT32:
                item["status_code"] = value
            else:
                counts["invalid_count"] += 1
        if "health" in row:
            value = row["health"]
            if type(value) is int and 0 <= value <= MAX_INT32:
                item["health_score"] = value
            else:
                counts["invalid_count"] += 1
        if kind == "devices" and "deviceType" in row:
            value = row["deviceType"]
            if isinstance(value, str) and value in {"gateway", "switch", "ap"}:
                item["device_type"] = value
            else:
                counts["unknown_field_count"] += 1
        items.append(item)
    data["items"] = items
    data["returned_count"] = len(items)
    data["has_more"] = (data["total_rows"] > len(items)
                        if "total_rows" in data else None)
    counts["omitted_row_count"] = max(0, data["total_rows"] - len(items)) \
        if data.get("has_more") else 0
    data.update(counts)
    data["present_count"] = sum(key in data for key in (
        "total_rows", "current_page", "current_size"))
    return {"data": data,
            "partial": bool(counts["invalid_count"] or counts["unknown_field_count"] or
                             counts["unmapped_identity_count"] or counts["omitted_row_count"])}
