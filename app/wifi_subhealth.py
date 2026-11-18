"""Bounded, privacy-preserving projection for site Wi-Fi sub-health details."""
from __future__ import annotations


class WifiSubhealthError(ValueError):
    """Input or requested time window cannot be projected safely."""

    def __init__(self, code: str = "wifi_subhealth_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_DETAILS = (
    "accessTimeScoreDetail", "channelUtilScoreDetail", "accessCapacityScoreDetail",
    "rssiScoreDetail", "channelInterUtilDetail", "wirelessClientQualityDetail",
)
_COMMON_DETAILS = frozenset({
    "accessTimeScoreDetail", "channelUtilScoreDetail", "accessCapacityScoreDetail",
    "rssiScoreDetail",
})
_CHANNEL_FIELDS = (
    "averageInterf2g", "averageInterf5g", "averageInterf6g", "averageNoiseFloor",
)
_QUALITY_LISTS = ("assocTime", "authTime", "dhcpTime", "dnsTime")
_QUALITY_AVERAGES = (
    "averageAssocTime", "averageAuthTime", "averageDhcpTime", "averageDnsTime",
)
_ROOT_FIELDS = frozenset({"wifiHealthScore", *_DETAILS})
_COMMON_FIELDS = frozenset({"summaryScore", "support", "scores", "incidents"})
_CHANNEL_DETAIL_FIELDS = _COMMON_FIELDS | frozenset(_CHANNEL_FIELDS)
_QUALITY_DETAIL_FIELDS = frozenset({
    "summaryScore", "support", "incidents", *_QUALITY_LISTS, *_QUALITY_AVERAGES,
})
_MAX_ROOT_FIELDS = 16
_MAX_DETAIL_FIELDS = 32
_MAX_POINT_FIELDS = 8
_MAX_LIST_POINTS = 512
_MAX_TOTAL_POINTS = 2048
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_WINDOW_MS = 86_400_000


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def project_wifi_subhealth(raw: object, start_ms: int, end_ms: int) -> dict[str, object]:
    """Project only the six documented detail groups inside a fixed ms window.

    Score and value integers remain raw int32 values, without scale inference.
    The documented `incidents` field is intentionally discarded without being
    inspected or counted as unknown because it can contain identities and text.
    """
    if (type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms <= end_ms <= _INT64_MAX or
            end_ms - start_ms != _WINDOW_MS):
        raise WifiSubhealthError("window_invalid")
    if not isinstance(raw, dict) or len(raw) > _MAX_ROOT_FIELDS:
        raise WifiSubhealthError("result_invalid")

    data: dict[str, object] = {}
    missing: list[str] = []
    invalid: list[str] = []
    unknown_field_count = 0
    omitted_count = 0
    total_points = 0

    def mark_missing(path: str) -> None:
        nonlocal omitted_count
        if path not in missing:
            missing.append(path)
        omitted_count += 1

    def mark_invalid(path: str) -> None:
        nonlocal omitted_count
        if path not in invalid:
            invalid.append(path)
        omitted_count += 1

    def count_unknown(obj: dict[object, object], allowed: frozenset[str]) -> None:
        nonlocal unknown_field_count, omitted_count
        for key in obj:
            if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
                raise WifiSubhealthError("result_invalid")
            if key not in allowed:
                unknown_field_count += 1
                omitted_count += 1

    def project_points(source: object, path: str, value_field: str) -> list[dict[str, int]] | None:
        nonlocal total_points
        if not isinstance(source, list):
            mark_invalid(path)
            return None
        if len(source) > _MAX_LIST_POINTS:
            raise WifiSubhealthError("result_too_large")
        total_points += len(source)
        if total_points > _MAX_TOTAL_POINTS:
            raise WifiSubhealthError("result_too_large")
        allowed = frozenset({"time", value_field})
        points: list[dict[str, int]] = []
        for point in source:
            if not isinstance(point, dict):
                mark_invalid(path + "[].item")
                continue
            if len(point) > _MAX_POINT_FIELDS:
                raise WifiSubhealthError("result_too_large")
            count_unknown(point, allowed)
            projected: dict[str, int] = {}
            time_valid = False
            time_path = f"{path}[].time"
            if "time" not in point:
                mark_missing(time_path)
            else:
                timestamp = point["time"]
                time_valid = (type(timestamp) is int and 0 <= timestamp <= _INT64_MAX and
                              start_ms <= timestamp <= end_ms)
                if time_valid:
                    projected["time_ms"] = timestamp
                else:
                    mark_invalid(time_path)

            value_path = f"{path}[].{value_field}"
            if value_field not in point:
                mark_missing(value_path)
            else:
                value = point[value_field]
                if _int32(value):
                    if time_valid:
                        projected[value_field] = value
                else:
                    mark_invalid(value_path)
            if projected:
                points.append(projected)
        return points

    if "wifiHealthScore" not in raw:
        mark_missing("wifiHealthScore")
    elif _int32(raw["wifiHealthScore"]):
        data["wifiHealthScore"] = raw["wifiHealthScore"]
    else:
        mark_invalid("wifiHealthScore")

    for detail_name in _DETAILS:
        if detail_name not in raw:
            mark_missing(detail_name)
            continue
        detail = raw[detail_name]
        if not isinstance(detail, dict):
            mark_invalid(detail_name)
            continue
        if len(detail) > _MAX_DETAIL_FIELDS:
            raise WifiSubhealthError("result_too_large")

        if detail_name in _COMMON_DETAILS:
            allowed_fields = _COMMON_FIELDS
        elif detail_name == "channelInterUtilDetail":
            allowed_fields = _CHANNEL_DETAIL_FIELDS
        else:
            allowed_fields = _QUALITY_DETAIL_FIELDS
        # incidents are a documented private structure and must be dropped
        # even though they are excluded from the public field allowlist.
        count_unknown(detail, allowed_fields)
        output: dict[str, object] = {}

        for scalar in ("summaryScore", "support"):
            if scalar not in detail:
                mark_missing(f"{detail_name}.{scalar}")
                continue
            value = detail[scalar]
            valid = type(value) is bool if scalar == "support" else _int32(value)
            if valid:
                output[scalar] = value
            else:
                mark_invalid(f"{detail_name}.{scalar}")

        if detail_name in _COMMON_DETAILS or detail_name == "channelInterUtilDetail":
            if "scores" not in detail:
                mark_missing(f"{detail_name}.scores")
            else:
                points = project_points(detail["scores"], f"{detail_name}.scores", "score")
                if points is not None:
                    output["scores"] = points

        if detail_name == "channelInterUtilDetail":
            for field in _CHANNEL_FIELDS:
                if field not in detail:
                    mark_missing(f"{detail_name}.{field}")
                    continue
                value = detail[field]
                if _int32(value):
                    output[field] = value
                else:
                    mark_invalid(f"{detail_name}.{field}")

        if detail_name == "wirelessClientQualityDetail":
            for list_field in _QUALITY_LISTS:
                path = f"{detail_name}.{list_field}"
                if list_field not in detail:
                    mark_missing(path)
                    continue
                points = project_points(detail[list_field], path, "pastNum")
                if points is not None:
                    output[list_field] = points
            for field in _QUALITY_AVERAGES:
                if field not in detail:
                    mark_missing(f"{detail_name}.{field}")
                    continue
                value = detail[field]
                if _int32(value):
                    output[field] = value
                else:
                    mark_invalid(f"{detail_name}.{field}")

        data[detail_name] = output

    count_unknown(raw, _ROOT_FIELDS)
    return {
        "status": "ok",
        "resource": "wifi_subhealth",
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "data": data,
        "partial": bool(missing or invalid or unknown_field_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_field_count,
        "omitted_count": omitted_count,
    }
