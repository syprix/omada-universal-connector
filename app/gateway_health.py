"""Redacted projection for documented gateway health-detail responses."""

from __future__ import annotations

import math
from typing import Any


class GatewayHealthProjectionError(ValueError):
    """The gateway health response does not match documented value shapes."""


MAX_POINTS_PER_SERIES = 64
MAX_RAW_POINTS_PER_SERIES = 512
MAX_INCIDENTS_PER_DIMENSION = 256
INT32_MIN, INT32_MAX = -(2**31), 2**31 - 1
INT64_MAX = 2**63 - 1

# source response key, public projection key, dimension type
_DIMENSIONS = (
    ("cpu", "cpu", "common"),
    ("memory", "memory", "common"),
    ("temperature", "temperature", "common"),
    ("wanLatency", "wan_latency", "common"),
    ("channelUtil", "channel_utilization", "channel"),
    ("supportedChannelUtil", "supported_channel_utilization", "channel"),
    ("transmission", "transmission", "transmission"),
    # Present in Hardware Controller 6.3.0 and CBC 6.3.0, absent in
    # ER7212PC 6.2.14. These keys are optional, so one projection fits all.
    ("incident", "incident", "incident"),
    ("wanStatus", "wan_status", "wan_status"),
    ("linkError", "link_error", "link_error"),
)


def _integer(value: Any, bits: int) -> int:
    low, high = (INT32_MIN, INT32_MAX) if bits == 32 else (0, INT64_MAX)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise GatewayHealthProjectionError("response_invalid")
    return value


def _number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GatewayHealthProjectionError("response_invalid")
    try:
        if not math.isfinite(value):
            raise GatewayHealthProjectionError("response_invalid")
    except (OverflowError, TypeError, ValueError):
        raise GatewayHealthProjectionError("response_invalid") from None
    return value


def _bounded_int(value: Any, unclassified: list[str], key: str) -> int | None:
    number = _integer(value, 32)
    # The API documents int32, but does not define the meaning of -1.
    if number == -1:
        unclassified.append(key)
        return None
    return number


def _series(value: Any, start_ms: int, end_ms: int,
            unclassified: list[str], field: str,
            *, floating: bool = False
            ) -> tuple[list[dict[str, int | float]], int, int, int]:
    if not isinstance(value, list) or len(value) > MAX_RAW_POINTS_PER_SERIES:
        raise GatewayHealthProjectionError("response_invalid")
    points: list[dict[str, int | float]] = []
    outside = missing = 0
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise GatewayHealthProjectionError("response_invalid")
        time = _integer(row.get("time"), 64)
        if time < 0:
            raise GatewayHealthProjectionError("response_invalid")
        if time < start_ms or time > end_ms:
            outside += 1
            continue
        sample = row.get("pastNum")
        if sample is None:
            missing += 1
            continue
        if floating:
            number = _number(sample)
        else:
            number = _integer(sample, 32)
            if number == -1:
                if field not in unclassified:
                    unclassified.append(field)
                missing += 1
                continue
            if number < 0:
                raise GatewayHealthProjectionError("response_invalid")
        points.append({"time_ms": time, "value": number})
    points.sort(key=lambda point: point["time_ms"])
    truncated = max(0, len(points) - MAX_POINTS_PER_SERIES)
    if truncated:
        points = points[-MAX_POINTS_PER_SERIES:]
    return points, outside, missing, truncated


def _project_dimension(value: Any, kind: str, start_ms: int, end_ms: int,
                       unclassified: list[str], prefix: str) -> tuple[dict[str, Any], int]:
    if not isinstance(value, dict):
        raise GatewayHealthProjectionError("response_invalid")
    out: dict[str, Any] = {}
    partial = False

    for source, target in (("summaryScore", "summary_score"),):
        if source in value and value[source] is not None:
            number = _bounded_int(value[source], unclassified, f"{prefix}.{target}")
            if number is not None:
                out[target] = number
    if "support" in value and value["support"] is not None:
        if not isinstance(value["support"], bool):
            raise GatewayHealthProjectionError("response_invalid")
        out["supported"] = value["support"]

    scalar_fields: list[tuple[str, str, str]] = []
    series_fields: list[tuple[tuple[str, ...], str, bool]] = []
    if kind == "common":
        scalar_fields = [("averageNum", "average", "int")]
        series_fields = [(('pastNums',), "values", False)]
    elif kind == "channel":
        scalar_fields = [(f"averageNum{band}", f"average_{band}", "int")
                         for band in ("2g", "5g", "6g")]
        series_fields = [((f"pastNums{band}",), f"values_{band.lower()}", False)
                         for band in ("2g", "5g", "6g")]
    elif kind == "transmission":
        scalar_fields = [("averageNumTxRetry", "average_tx_retry", "int"),
                         ("averageNumTxDrop", "average_tx_drop", "int")]
        series_fields = [(('pastNumsTxRetry',), "tx_retry_values", False),
                         (('pastNumsTxDrop',), "tx_drop_values", False)]
    elif kind == "wan_status":
        scalar_fields = [("averageLatency", "average_latency", "int"),
                         ("averageJitter", "average_jitter", "int"),
                         ("averagePktLoss", "average_packet_loss", "float"),
                         ("averageMos", "average_mos", "float")]
        series_fields = [(('pastLatency', 'latency'), "latency_values", False),
                         (('pastJitter', 'jitter'), "jitter_values", False),
                         (('pastPktLoss', 'pktLoss'), "packet_loss_values", True),
                         (('pastMos', 'mos'), "mos_values", True)]
    elif kind == "link_error":
        scalar_fields = [("averageNum", "average", "int"),
                         ("portNum", "port_count", "int")]
        series_fields = [(('pastNums',), "values", False)]
    elif kind == "incident":
        if "incidentNum" in value and value["incidentNum"] is not None:
            number = _integer(value["incidentNum"], 32)
            if number < 0:
                if number == -1:
                    unclassified.append(f"{prefix}.incident_count")
                else:
                    raise GatewayHealthProjectionError("response_invalid")
            else:
                out["incident_count"] = number

    for source, target, numeric_kind in scalar_fields:
        if source not in value or value[source] is None:
            continue
        if numeric_kind == "float":
            out[target] = _number(value[source])
        else:
            number = _bounded_int(value[source], unclassified, f"{prefix}.{target}")
            if number is not None:
                out[target] = number

    outside_total = missing_total = truncated_total = 0
    for sources, target, floating in series_fields:
        source = next((name for name in sources if name in value), None)
        if source is None or value[source] is None:
            continue
        points, outside, missing, truncated = _series(
            value[source], start_ms, end_ms, unclassified, f"{prefix}.{target}",
            floating=floating)
        out[target] = points
        outside_total += outside
        missing_total += missing
        truncated_total += truncated
    if outside_total:
        out["omitted_out_of_window_sample_count"] = outside_total
        partial = True
    if missing_total:
        out["omitted_missing_sample_count"] = missing_total
        partial = True
    if truncated_total:
        out["omitted_point_count"] = truncated_total
        partial = True

    # Incident records contain identifiers and free text. Only their count is
    # exposed; no incident object is inspected or copied into the result.
    if "incidents" in value and value["incidents"] is not None:
        incidents = value["incidents"]
        if not isinstance(incidents, list) or len(incidents) > MAX_INCIDENTS_PER_DIMENSION:
            raise GatewayHealthProjectionError("response_invalid")
        out["omitted_incident_count"] = len(incidents)
        if incidents:
            partial = True

    # Only count keys actually handled for this dimension kind. A field that is
    # known elsewhere in the response schema is still omitted here if it appears
    # in a dimension where we do not interpret it.
    kept = {"summaryScore", "support", "incidents"}
    if kind == "common":
        kept |= {"averageNum", "pastNums"}
    elif kind == "channel":
        kept |= {"averageNum2g", "averageNum5g", "averageNum6g",
                 "pastNums2g", "pastNums5g", "pastNums6g"}
    elif kind == "transmission":
        kept |= {"averageNumTxRetry", "averageNumTxDrop",
                 "pastNumsTxRetry", "pastNumsTxDrop"}
    elif kind == "wan_status":
        kept |= {"averageLatency", "averageJitter", "averagePktLoss", "averageMos",
                 "pastLatency", "pastJitter", "pastPktLoss", "pastMos",
                 "latency", "jitter", "pktLoss", "mos"}
    elif kind == "link_error":
        kept |= {"averageNum", "portNum", "pastNums"}
    elif kind == "incident":
        kept.add("incidentNum")
    omitted_fields = sum(1 for key in value if key not in kept)
    if omitted_fields:
        out["omitted_field_count"] = omitted_fields
        partial = True
    return out, int(partial)


def project_gateway_health_detail(result: Any, start_ms: int, end_ms: int) -> dict[str, Any]:
    """Project gateway health values without identifiers or incident details.

    ``start_ms`` and ``end_ms`` are the caller's fixed, documented millisecond
    query window. Out-of-window samples are omitted and counted. Family-specific
    fields are emitted only when present in the response schema/data.
    """
    if (not isinstance(result, dict) or isinstance(start_ms, bool)
            or not isinstance(start_ms, int) or isinstance(end_ms, bool)
            or not isinstance(end_ms, int) or start_ms < 0 or end_ms < start_ms
            or end_ms > INT64_MAX):
        raise GatewayHealthProjectionError("response_invalid")
    out: dict[str, Any] = {}
    unclassified: list[str] = []
    partial = False
    if "score" in result and result["score"] is not None:
        score = _bounded_int(result["score"], unclassified, "score")
        if score is not None:
            out["score"] = score
    for source, target, kind in _DIMENSIONS:
        if source not in result or result[source] is None:
            continue
        projected, was_partial = _project_dimension(result[source], kind, start_ms,
                                                     end_ms, unclassified, target)
        out[target] = projected
        partial = partial or bool(was_partial)
    if unclassified:
        out["unclassified_minus_one_fields"] = unclassified
        partial = True
    recognized = {source for source, _, _ in _DIMENSIONS} | {"score"}
    omitted_fields = sum(1 for key in result if key not in recognized)
    if omitted_fields:
        out["omitted_field_count"] = omitted_fields
        partial = True
    out["partial"] = partial
    return out
