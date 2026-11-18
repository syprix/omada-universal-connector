"""Bounded, redacted projection of Omada switch health-detail responses.

The projection follows the common fields in the CBC, ER7212PC and Hardware
Controller OpenAPI exports. Newer exports add float measurements, incidents
and link-error details; older exports omit some of those optional fields.
"""
from __future__ import annotations

import math
from typing import Any


class SwitchHealthProjectionError(ValueError):
    """The switch health response does not match documented value shapes."""


MAX_POINTS_PER_SERIES = 64
MAX_INCIDENTS_PER_DIMENSION = 256
INT32_MIN, INT32_MAX = -(2**31), 2**31 - 1
INT64_MAX = 2**63 - 1
FLOAT32_MAX = 3.4028235e38

# response key, output key, measurement schema
_DIMENSIONS = (
    ("cpu", "cpu", "common"),
    ("memory", "memory", "common"),
    ("temperature", "temperature", "common"),
    ("packetLoss", "packet_loss", "float_optional"),
    ("errorFrame", "error_frame", "float_optional"),
    ("incident", "incident", "incident"),
    ("linkError", "link_error", "link_error"),
)
_CORE_DIMENSIONS = ("cpu", "memory", "temperature", "packetLoss", "errorFrame")


def _int(value: Any, *, bits: int) -> int:
    low, high = (INT32_MIN, INT32_MAX) if bits == 32 else (0, INT64_MAX)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise SwitchHealthProjectionError("response_invalid")
    return value


def _number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SwitchHealthProjectionError("response_invalid")
    try:
        if not math.isfinite(value) or abs(value) > FLOAT32_MAX:
            raise SwitchHealthProjectionError("response_invalid")
    except (OverflowError, TypeError, ValueError):
        raise SwitchHealthProjectionError("response_invalid") from None
    return value


def _int_value(value: Any, name: str, unclassified: list[str]) -> int | None:
    number = _int(value, bits=32)
    if number == -1:
        unclassified.append(name)
        return None
    return number


def _series(value: Any, start_ms: int, end_ms: int, *, floating: bool,
            field: str, unclassified: list[str]) -> tuple[list[dict[str, int | float]], int, int, int]:
    if not isinstance(value, list) or len(value) > MAX_POINTS_PER_SERIES:
        raise SwitchHealthProjectionError("response_invalid")
    points: list[dict[str, int | float]] = []
    outside = missing = omitted_fields = 0
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise SwitchHealthProjectionError("response_invalid")
        omitted_fields += len(set(item) - {"time", "pastNum"})
        timestamp = _int(item.get("time"), bits=64)
        if not start_ms <= timestamp <= end_ms:
            outside += 1
            continue
        if floating:
            number = _number(item.get("pastNum"))
        else:
            number = _int_value(item.get("pastNum"), f"{field}[{index}]", unclassified)
            if number is None:
                missing += 1
                continue
        points.append({"time_ms": timestamp, "value": number})
    return points, outside, missing, omitted_fields


def _project_dimension(value: Any, kind: str, start_ms: int, end_ms: int,
                       unclassified: list[str], prefix: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SwitchHealthProjectionError("response_invalid")
    out: dict[str, Any] = {}
    partial = False
    missing_fields: list[str] = []

    if "summaryScore" in value and value["summaryScore"] is not None:
        number = _int_value(value["summaryScore"], f"{prefix}.summary_score", unclassified)
        if number is not None:
            out["summary_score"] = number
        else:
            partial = True
    else:
        missing_fields.append("summary_score")
    if "support" in value and value["support"] is not None:
        if not isinstance(value["support"], bool):
            raise SwitchHealthProjectionError("response_invalid")
        out["supported"] = value["support"]
    else:
        missing_fields.append("supported")

    if kind == "incident":
        if "incidentNum" in value and value["incidentNum"] is not None:
            count = _int(value["incidentNum"], bits=32)
            if count == -1:
                unclassified.append(f"{prefix}.incident_count")
                partial = True
            elif count < 0:
                raise SwitchHealthProjectionError("response_invalid")
            else:
                out["incident_count"] = count
        else:
            missing_fields.append("incident_count")
    else:
        int_fields: list[tuple[str, str]] = [("averageNum", "average")]
        series_fields: list[tuple[str, str, bool]] = [("pastNums", "values", False)]
        float_fields: list[tuple[str, str]] = []
        float_series: list[tuple[str, str]] = []
        if kind == "float_optional":
            float_fields = [("averageFloat", "average_float")]
            float_series = [("pastFloats", "float_values")]
        elif kind == "link_error":
            int_fields.append(("portNum", "port_count"))

        for source, target in int_fields:
            if source in value and value[source] is not None:
                number = _int_value(value[source], f"{prefix}.{target}", unclassified)
                if number is not None:
                    out[target] = number
                else:
                    partial = True
            else:
                missing_fields.append(target)
        for source, target, floating in series_fields:
            if source in value and value[source] is not None:
                points, outside, absent, omitted = _series(value[source], start_ms, end_ms,
                                                            floating=floating, field=target,
                                                            unclassified=unclassified)
                out[target] = points
                if omitted:
                    out["omitted_field_count"] = out.get("omitted_field_count", 0) + omitted
                    partial = True
                if outside:
                    out["omitted_out_of_window_sample_count"] = out.get("omitted_out_of_window_sample_count", 0) + outside
                    partial = True
                if absent:
                    out["omitted_unclassified_sample_count"] = out.get("omitted_unclassified_sample_count", 0) + absent
                    partial = True
            else:
                missing_fields.append(target)
        for source, target in float_fields:
            if source in value and value[source] is not None:
                out[target] = _number(value[source])
        for source, target in float_series:
            if source in value and value[source] is not None:
                points, outside, _, omitted = _series(value[source], start_ms, end_ms,
                                                       floating=True, field=target,
                                                       unclassified=unclassified)
                out[target] = points
                if omitted:
                    out["omitted_field_count"] = out.get("omitted_field_count", 0) + omitted
                    partial = True
                if outside:
                    out["omitted_out_of_window_sample_count"] = out.get("omitted_out_of_window_sample_count", 0) + outside
                    partial = True

    # Incident payloads may contain IDs, MACs, device maps and arbitrary text.
    # Inspect only the documented list length and never copy individual entries.
    if "incidents" in value and value["incidents"] is not None:
        incidents = value["incidents"]
        if not isinstance(incidents, list) or len(incidents) > MAX_INCIDENTS_PER_DIMENSION:
            raise SwitchHealthProjectionError("response_invalid")
        out["omitted_incident_count"] = len(incidents)
        partial = partial or bool(incidents)

    recognized = {"summaryScore", "support", "incidents"}
    if kind == "incident":
        recognized.add("incidentNum")
    else:
        recognized.update({"averageNum", "pastNums"})
        if kind == "float_optional":
            recognized.update({"averageFloat", "pastFloats"})
        elif kind == "link_error":
            recognized.add("portNum")
    omitted = sum(1 for key in value if key not in recognized)
    if omitted:
        out["omitted_field_count"] = out.get("omitted_field_count", 0) + omitted
        partial = True
    if missing_fields:
        out["missing_fields"] = missing_fields
        partial = True
    out["partial"] = partial
    return out


def project_switch_health_detail(result: Any, start_ms: int,
                                 end_ms: int) -> dict[str, Any]:
    """Return bounded, identifier-free switch health data for a millisecond window.

    ``result`` is the documented ``OswHealthDetailVO``. The ER7212PC export
    documents integer packet-loss/error-frame samples; CBC and Hardware exports
    additionally allow float variants. Unsupported or absent values are listed
    without guessing why the controller omitted them.
    """
    if (not isinstance(result, dict) or isinstance(start_ms, bool)
            or not isinstance(start_ms, int) or isinstance(end_ms, bool)
            or not isinstance(end_ms, int) or start_ms < 0
            or end_ms < start_ms or end_ms > INT64_MAX):
        raise SwitchHealthProjectionError("response_invalid")
    output: dict[str, Any] = {}
    partial = False
    missing_fields: list[str] = []
    unclassified: list[str] = []
    if "score" in result and result["score"] is not None:
        score = _int_value(result["score"], "score", unclassified)
        if score is not None:
            output["score"] = score
        else:
            partial = True
    else:
        missing_fields.append("score")

    for source, target, kind in _DIMENSIONS:
        # incident/linkError are family-specific additions absent from the
        # ER7212PC export, so their absence is not treated as missing data.
        if source not in result or result[source] is None:
            if source in _CORE_DIMENSIONS:
                missing_fields.append(target)
            continue
        projected = _project_dimension(result[source], kind, start_ms, end_ms,
                                       unclassified, target)
        output[target] = projected
        partial = partial or projected["partial"]

    recognized = {source for source, _, _ in _DIMENSIONS} | {"score"}
    omitted = sum(1 for key in result if key not in recognized)
    if omitted:
        output["omitted_field_count"] = omitted
        partial = True
    if missing_fields:
        output["missing_fields"] = missing_fields
        partial = True
    if unclassified:
        output["unclassified_minus_one_fields"] = unclassified
        partial = True
    output["partial"] = partial
    return output
