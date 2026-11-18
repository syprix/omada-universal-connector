"""Bounded, identity-redacted projections for health incident reads."""
from __future__ import annotations

import re
from typing import Any


MAX_INT32 = 2_147_483_647
MAX_INT64 = 9_223_372_036_854_775_807
MAX_ROWS = 50
_INCIDENT_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_ANOMALY_CODE = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class SiteHealthIncidentError(ValueError):
    """Raised when an incident response cannot be safely projected."""


def _bounded_int(value: Any, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _rows(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        values = result
    elif isinstance(result, dict):
        if len(result) > 16:
            raise SiteHealthIncidentError("response_invalid")
        values = result.get("data", result.get("incidents"))
        if values is None and "incidentId" in result:
            values = [result]
    else:
        values = None
    if not isinstance(values, list) or len(values) > MAX_ROWS:
        raise SiteHealthIncidentError("response_invalid")
    if any(not isinstance(row, dict) or len(row) > 32 for row in values):
        raise SiteHealthIncidentError("response_invalid")
    return values


def extract_incidents(result: Any) -> list[tuple[str, dict[str, object]]]:
    """Return private upstream IDs paired with the small public projection."""
    out: list[tuple[str, dict[str, object]]] = []
    for row in _rows(result):
        incident_id = row.get("incidentId")
        if not isinstance(incident_id, str) or not _INCIDENT_ID.fullmatch(incident_id):
            raise SiteHealthIncidentError("response_invalid")
        item: dict[str, object] = {}
        code = row.get("anomalyCode")
        if code is not None:
            if not isinstance(code, str) or not _ANOMALY_CODE.fullmatch(code):
                raise SiteHealthIncidentError("response_invalid")
            item["anomaly_code"] = code
        for source, target in (("category", "category_code"), ("level", "severity_code"),
                               ("status", "status_code"), ("count", "occurrence_count")):
            if source in row:
                value = row[source]
                if not _bounded_int(value, MAX_INT32):
                    raise SiteHealthIncidentError("response_invalid")
                item[target] = value
        for source, target in (("time", "time_ms"), ("startTime", "start_time_ms"),
                               ("endTime", "end_time_ms")):
            if source in row:
                value = row[source]
                if not _bounded_int(value, MAX_INT64):
                    raise SiteHealthIncidentError("response_invalid")
                item[target] = value
        object_type = row.get("objectType")
        if object_type is not None:
            if not isinstance(object_type, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,48}", object_type):
                raise SiteHealthIncidentError("response_invalid")
            item["object_type"] = object_type
        out.append((incident_id, item))
    return out


def project_incident_detail(result: Any) -> dict[str, object]:
    """Keep documented scalar diagnostics; omit names, detail text and identities."""
    if not isinstance(result, dict) or len(result) > 32:
        raise SiteHealthIncidentError("response_invalid")
    out: dict[str, object] = {}
    code = result.get("anomalyCode")
    if code is not None:
        if not isinstance(code, str) or not _ANOMALY_CODE.fullmatch(code):
            raise SiteHealthIncidentError("response_invalid")
        out["anomaly_code"] = code
    for source, target in (("category", "category_code"), ("level", "severity_code"),
                           ("status", "status_code")):
        if source in result:
            value = result[source]
            if not _bounded_int(value, MAX_INT32):
                raise SiteHealthIncidentError("response_invalid")
            out[target] = value
    for source, target in (("time", "time_ms"), ("startTime", "start_time_ms"),
                           ("endTime", "end_time_ms")):
        if source in result:
            value = result[source]
            if not _bounded_int(value, MAX_INT64):
                raise SiteHealthIncidentError("response_invalid")
            out[target] = value
    object_type = result.get("objectType")
    if object_type is not None:
        if not isinstance(object_type, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,48}", object_type):
            raise SiteHealthIncidentError("response_invalid")
        out["object_type"] = object_type
    if not out:
        raise SiteHealthIncidentError("response_invalid")
    # The upstream detail includes free text and identity maps that this
    # connector intentionally never returns.
    return {"data": out, "partial": True}
