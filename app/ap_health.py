"""Redacted projection helpers for the documented Omada AP health response."""

from __future__ import annotations

from typing import Any


class ApHealthProjectionError(ValueError):
    """The AP health response does not match the documented value shapes."""


MAX_POINTS_PER_SERIES = 256
MAX_INCIDENTS_PER_DIMENSION = 256
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1

# (response key, output key, kind)
DIMENSIONS = (
    ("cpu", "cpu", "common"),
    ("memory", "memory", "common"),
    ("incident", "incident", "incident"),
    ("channelUtil", "channel_utilization", "channel"),
    ("supportedChannelUtil", "supported_channel_utilization", "channel"),
    ("channelInterf", "channel_interference", "channel"),
    ("supportedChannelInterf", "supported_channel_interference", "interference"),
    ("transmission", "transmission", "transmission"),
)


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int32(value: Any) -> int:
    if not _integer(value) or not INT32_MIN <= value <= INT32_MAX:
        raise ApHealthProjectionError("response_invalid")
    return value


def _known_number(value: Any, field: str, unclassified: list[str]) -> int | None:
    number = _int32(value)
    if number == -1:
        unclassified.append(field)
        return None
    return number


def _project_dimension(value: Any, kind: str, start_ms: int, end_ms: int,
                       unclassified: list[str], prefix: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApHealthProjectionError("response_invalid")
    out: dict[str, Any] = {}

    score = value.get("summaryScore")
    if score is not None:
        score = _known_number(score, f"{prefix}.summary_score", unclassified)
        if score is not None:
            out["summary_score"] = score

    if value.get("support") is not None:
        supported = value["support"]
        if not isinstance(supported, bool):
            raise ApHealthProjectionError("response_invalid")
        out["supported"] = supported

    if kind == "incident":
        if value.get("incidentNum") is not None:
            count = _int32(value["incidentNum"])
            if count < 0:
                if count == -1:
                    unclassified.append(f"{prefix}.incident_count")
                else:
                    raise ApHealthProjectionError("response_invalid")
            else:
                out["incident_count"] = count
    else:
        discarded_out_of_window_points = 0
        missing_value_points = 0
        scalar_fields: list[tuple[str, str]] = []
        series_fields: list[tuple[str, str]] = []
        if kind == "common":
            scalar_fields = [("averageNum", "average")]
            series_fields = [("pastNums", "values")]
        elif kind in ("channel", "interference"):
            scalar_fields = [("averageNum2g", "average_2g"),
                             ("averageNum5g", "average_5g"),
                             ("averageNum6g", "average_6g")]
            series_fields = [(f"pastNums{band}", f"values_{band.lower()}")
                             for band in ("2g", "5g", "6g")]
            if kind == "interference":
                scalar_fields.append(("averageNoiseFloor", "average_noise_floor"))
                series_fields.append(("pastNoiseFloor", "noise_floor_values"))
        elif kind == "transmission":
            scalar_fields = [("averageNumTxRetry", "average_tx_retry"),
                             ("averageNumTxDrop", "average_tx_drop")]
            series_fields = [("pastNumsTxRetry", "tx_retry_values"),
                             ("pastNumsTxDrop", "tx_drop_values")]

        for source, target in scalar_fields:
            if value.get(source) is not None:
                number = _known_number(value[source], f"{prefix}.{target}", unclassified)
                if number is not None:
                    out[target] = number
        for source, target in series_fields:
            if source not in value or value[source] is None:
                continue
            points = value[source]
            if not isinstance(points, list) or len(points) > MAX_POINTS_PER_SERIES:
                raise ApHealthProjectionError("response_invalid")
            projected: list[dict[str, int]] = []
            for index, point in enumerate(points):
                if not isinstance(point, dict):
                    raise ApHealthProjectionError("response_invalid")
                timestamp = point.get("time")
                if not _integer(timestamp) or timestamp < 0:
                    raise ApHealthProjectionError("response_invalid")
                if "pastNum" not in point:
                    raise ApHealthProjectionError("response_invalid")
                if not start_ms <= timestamp <= end_ms:
                    discarded_out_of_window_points += 1
                    continue
                raw_number = point.get("pastNum")
                if raw_number is None:
                    missing_value_points += 1
                    continue
                number = _known_number(raw_number, f"{prefix}.{target}[{index}]", unclassified)
                if number is not None:
                    projected.append({"time_ms": timestamp, "value": number})
            out[target] = projected
        if discarded_out_of_window_points:
            out["discarded_out_of_window_points"] = discarded_out_of_window_points
        if missing_value_points:
            out["missing_value_points"] = missing_value_points

    # Incident details are intentionally discarded: they can contain identifiers,
    # names, addresses and free text. The published schema explicitly counts entries.
    if "incidents" in value and value["incidents"] is not None:
        incidents = value["incidents"]
        if not isinstance(incidents, list) or len(incidents) > MAX_INCIDENTS_PER_DIMENSION:
            raise ApHealthProjectionError("response_invalid")
        out["incidents_count"] = len(incidents)
    return out


def project_ap_health_detail(result: Any, start_ms: int, end_ms: int) -> dict[str, Any]:
    """Return a bounded, identifier-free projection of an AP health ``result``.

    ``result`` is the documented ``ApHealthDetailVO`` object. Values outside the
    requested window are omitted from time series. ``-1`` is preserved as a
    field-specific unclassified marker, since the schema does not define it.
    """
    if (not isinstance(result, dict) or not _integer(start_ms) or not _integer(end_ms)
            or start_ms < 0 or end_ms < start_ms):
        raise ApHealthProjectionError("response_invalid")
    out: dict[str, Any] = {}
    unclassified: list[str] = []
    if result.get("score") is not None:
        score = _known_number(result["score"], "score", unclassified)
        if score is not None:
            out["score"] = score
    for source, target, kind in DIMENSIONS:
        if source in result and result[source] is not None:
            out[target] = _project_dimension(result[source], kind, start_ms, end_ms,
                                             unclassified, target)
    if unclassified:
        out["unclassified_minus_one_fields"] = unclassified
    return out
