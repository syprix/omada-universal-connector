"""Bounded projection of the documented site client health distribution timeline."""
from __future__ import annotations


class SiteClientHealthTimelineError(ValueError):
    """The upstream shape or fixed query window is invalid."""

    def __init__(self, code: str = "site_client_health_timeline_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 16
_MAX_POINTS = 256
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1
_INT32_MAX = 2**31 - 1
_COUNT_FIELDS = ("goodCount", "averageCount", "poorCount", "noDataCount")
_OUTPUT_FIELDS = {
    "goodCount": "good_count",
    "averageCount": "average_count",
    "poorCount": "poor_count",
    "noDataCount": "no_data_count",
}


def project_site_client_health_timeline(raw: object, start_ms: int,
                                        end_ms: int) -> dict[str, object]:
    """Keep only documented timestamps and nonnegative health-category counts.

    The source documents four categories and describes their score bands, but
    this projection does not calculate or infer a combined health score.
    Unknown fields are counted without disclosing names or values.
    """
    if (type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms <= end_ms <= _INT64_MAX or
            end_ms - start_ms != 86_400_000):
        raise SiteClientHealthTimelineError()
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise SiteClientHealthTimelineError()
    if any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH for key in raw):
        raise SiteClientHealthTimelineError()

    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    discarded_outside_window = 0
    scores: list[dict[str, object]] = []

    if "scores" not in raw:
        missing.append("scores")
        omitted_count += 1
    elif not isinstance(raw["scores"], list):
        omitted.add("scores")
        omitted_count += 1
    else:
        points = raw["scores"]
        if len(points) > _MAX_POINTS:
            raise SiteClientHealthTimelineError()
        for index, point in enumerate(points):
            if not isinstance(point, dict) or len(point) > _MAX_FIELDS:
                omitted.add("invalid_points")
                omitted_count += 1
                continue
            if any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH for key in point):
                raise SiteClientHealthTimelineError()

            timestamp = point.get("time")
            if "time" not in point:
                missing.append(f"scores[{index}].time")
                omitted_count += 1
                continue
            if type(timestamp) is not int or not 0 <= timestamp <= _INT64_MAX:
                omitted.add("invalid_timestamps")
                omitted_count += 1
                continue
            if not start_ms <= timestamp <= end_ms:
                discarded_outside_window += 1
                omitted.add("out_of_window_points")
                omitted_count += 1
                continue

            projected: dict[str, object] = {"time_ms": timestamp}
            detail = point.get("scoreDetail")
            if "scoreDetail" not in point:
                missing.append(f"scores[{index}].scoreDetail")
                omitted_count += 1
            elif not isinstance(detail, dict) or len(detail) > _MAX_FIELDS:
                omitted.add("invalid_score_details")
                omitted_count += 1
            else:
                if any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH
                       for key in detail):
                    raise SiteClientHealthTimelineError()
                counts: dict[str, int] = {}
                for field in _COUNT_FIELDS:
                    if field not in detail:
                        missing.append(f"scores[{index}].scoreDetail.{field}")
                        omitted_count += 1
                        continue
                    value = detail[field]
                    if type(value) is int and 0 <= value <= _INT32_MAX:
                        counts[_OUTPUT_FIELDS[field]] = value
                    else:
                        omitted.add(f"invalid_{_OUTPUT_FIELDS[field]}")
                        omitted_count += 1
                if counts:
                    projected["score_detail"] = counts
                extras = sum(1 for key in detail if key not in _COUNT_FIELDS)
                if extras:
                    omitted.add("unknown_fields")
                    omitted_count += extras

            extras = sum(1 for key in point if key not in {"time", "scoreDetail"})
            if extras:
                omitted.add("unknown_fields")
                omitted_count += extras
            scores.append(projected)

    extras = sum(1 for key in raw if key != "scores")
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras

    return {
        "status": "ok",
        "resource": "site_client_health_timeline",
        "data": {"scores": scores},
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
        "discarded_outside_window": discarded_outside_window,
    }
