"""Compact, evidence-aware summary of saved gateway WAN observations."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import math

MAX_WINDOW_MS = 86_400_000
MAX_POINTS = 4096
INT64_MAX = 2**63 - 1


class WanIncidentWindowError(ValueError):
    """A source projection or requested time range is invalid."""


def _window(start_ms: object, end_ms: object) -> None:
    if (type(start_ms) is not int or type(end_ms) is not int or start_ms < 0 or
            end_ms < start_ms or end_ms > INT64_MAX or end_ms - start_ms > MAX_WINDOW_MS):
        raise WanIncidentWindowError("time_window_invalid")


def _series_summary(value: object, start_ms: int, end_ms: int) -> dict[str, object]:
    if not isinstance(value, list) or len(value) > MAX_POINTS:
        raise WanIncidentWindowError("series_invalid")
    values: list[tuple[int, int | float]] = []
    outside = invalid = 0
    for point in value:
        if not isinstance(point, Mapping):
            invalid += 1
            continue
        timestamp, sample = point.get("time_ms"), point.get("value")
        if type(timestamp) is not int or timestamp < 0:
            invalid += 1
            continue
        if not start_ms <= timestamp <= end_ms:
            outside += 1
            continue
        if (isinstance(sample, bool) or not isinstance(sample, (int, float)) or
                not math.isfinite(sample)):
            invalid += 1
            continue
        values.append((timestamp, sample))
    values.sort()
    samples = [item[1] for item in values]
    return {
        "sample_count": len(values),
        "first_sample_ms": values[0][0] if values else None,
        "last_sample_ms": values[-1][0] if values else None,
        "minimum_observed_value": min(samples) if samples else None,
        "maximum_observed_value": max(samples) if samples else None,
        "last_observed_value": samples[-1] if samples else None,
        "omitted_out_of_window_count": outside,
        "omitted_invalid_count": invalid,
        "partial": bool(outside or invalid),
    }


def _health_series(health: object, start_ms: int, end_ms: int
                   ) -> tuple[dict[str, object], int | None, bool]:
    if not isinstance(health, Mapping) or health.get("status") != "ok":
        return {}, None, True
    if (health.get("window_start_ms") != start_ms or
            health.get("window_end_ms") != end_ms):
        return {}, None, True
    data = health.get("data")
    if not isinstance(data, Mapping):
        return {}, None, True
    output: dict[str, object] = {}
    partial = data.get("partial") is not False
    for dimension, field_map in (
        ("wan_latency", {"values": "latency"}),
        ("wan_status", {"latency_values": "latency", "jitter_values": "jitter",
                         "packet_loss_values": "packet_loss", "mos_values": "mos"}),
    ):
        raw = data.get(dimension)
        if raw is None:
            continue
        if not isinstance(raw, Mapping):
            partial = True
            continue
        projected: dict[str, object] = {}
        for source_key, target in field_map.items():
            if source_key not in raw:
                continue
            summary = _series_summary(raw[source_key], start_ms, end_ms)
            projected[target] = summary
            partial = partial or summary["partial"] is True
        if projected:
            output[dimension] = projected
    incidents = data.get("incident")
    incident_count = None
    if isinstance(incidents, Mapping) and type(incidents.get("incident_count")) is int:
        incident_count = incidents["incident_count"]
    else:
        partial = True
    return output, incident_count, partial


def _timeline_summary(timeline: object, start_ms: int, end_ms: int
                      ) -> tuple[dict[str, object], bool]:
    if not isinstance(timeline, Mapping) or timeline.get("status") != "ok":
        return {"status": "unavailable"}, True
    if (timeline.get("window_start_ms") != start_ms or
            timeline.get("window_end_ms") != end_ms):
        return {"status": "window_mismatch"}, True
    data = timeline.get("data")
    scores = data.get("scores") if isinstance(data, Mapping) else None
    if not isinstance(scores, list) or len(scores) > MAX_POINTS:
        return {"status": "invalid_or_unavailable"}, True
    points = []
    invalid = outside = 0
    for item in scores:
        if not isinstance(item, Mapping):
            invalid += 1
            continue
        timestamp, score = item.get("time_ms"), item.get("score")
        if type(timestamp) is not int or type(score) is not int:
            invalid += 1
            continue
        if not start_ms <= timestamp <= end_ms:
            outside += 1
            continue
        points.append((timestamp, score))
    points.sort()
    numbers = [item[1] for item in points]
    partial = timeline.get("partial") is not False or invalid > 0 or outside > 0
    return ({"status": "available", "sample_count": len(points),
             "first_sample_ms": points[0][0] if points else None,
             "last_sample_ms": points[-1][0] if points else None,
             "minimum_observed_score": min(numbers) if numbers else None,
             "maximum_observed_score": max(numbers) if numbers else None,
             "omitted_invalid_count": invalid, "omitted_out_of_window_count": outside,
             "partial": partial}, partial)


def _current_status_summary(current: object) -> tuple[dict[str, object], bool]:
    if not isinstance(current, Mapping) or current.get("status") != "ok":
        return {"status": "unavailable"}, True
    items = current.get("items")
    if not isinstance(items, list) or len(items) > 256:
        return {"status": "invalid_or_unavailable"}, True
    count: defaultdict[str, defaultdict[int, int]] = defaultdict(lambda: defaultdict(int))
    invalid = 0
    for item in items:
        if not isinstance(item, Mapping):
            invalid += 1
            continue
        for field in ("link_status", "internet_state", "health_level"):
            code = item.get(field)
            if type(code) is int:
                count[field][code] += 1
            elif code is not None:
                invalid += 1
    return ({"status": "available", "port_observation_count": len(items),
             "undecoded_status_code_counts": {
                 name: {str(code): n for code, n in sorted(codes.items())}
                 for name, codes in count.items()},
             "captured_at_ms": None, "age_ms": None,
             "age_reason": "upstream_response_has_no_capture_timestamp",
             "invalid_field_count": invalid, "partial": bool(invalid)}, bool(invalid))


def _saved_test_summary(result: object) -> tuple[dict[str, object], bool]:
    if not isinstance(result, Mapping) or result.get("status") != "ok":
        return {"status": "unavailable"}, True
    data = result.get("data")
    if not isinstance(data, Mapping) or type(data.get("count")) is not int:
        return {"status": "invalid_or_unavailable"}, True
    return ({"status": "available", "saved_measurement_count": data["count"],
             "measurement_time_unit": "undocumented_not_used_for_chronology",
             "included_in_time_window": False,
             "partial": data.get("partial") is not False},
            data.get("partial") is not False)


def build_wan_incident_window(*, site_ref: str, gateway_ref: str,
                              start_ms: int, end_ms: int, as_of_ms: int,
                              current_status: object, health: object,
                              health_timeline: object, saved_speed_test: object,
                              load_balance_status: object | None = None
                              ) -> dict[str, object]:
    """Join known observations without classifying undocumented codes or causes."""
    _window(start_ms, end_ms)
    if type(as_of_ms) is not int or as_of_ms < 0 or as_of_ms > INT64_MAX:
        raise WanIncidentWindowError("as_of_invalid")
    if not isinstance(site_ref, str) or not isinstance(gateway_ref, str):
        raise WanIncidentWindowError("reference_invalid")
    present, present_partial = _current_status_summary(current_status)
    history, undated_incident_count, history_partial = _health_series(health, start_ms, end_ms)
    score_timeline, timeline_partial = _timeline_summary(health_timeline, start_ms, end_ms)
    saved, saved_partial = _saved_test_summary(saved_speed_test)
    # The response schema only promises an object here; no internal field is used.
    load_balance_shape = "unavailable"
    if isinstance(load_balance_status, Mapping) and load_balance_status.get("status") == "ok":
        load_balance_shape = "opaque_object_withheld"
    return {
        "status": "ok", "resource": "gateway_wan_incident_window",
        "site_ref": site_ref, "gateway_ref": gateway_ref,
        "window": {"start_ms": start_ms, "end_ms": end_ms,
                   "duration_ms": end_ms - start_ms},
        "current_state": present,
        "historical_health_observations": history,
        "health_score_timeline": score_timeline,
        "undated_incident_count": undated_incident_count,
        "saved_speed_test_observations": saved,
        "load_balance_participation": {
            "status": "unknown", "source_result": load_balance_shape,
            "reason": "documented_response_has_no_status_field_schema"},
        "interpretation": "observations_only_no_outage_or_switch_inference",
        "partial": bool(present_partial or history_partial or timeline_partial or saved_partial or
                         load_balance_shape != "opaque_object_withheld" or
                         undated_incident_count is None),
        "report_as_of_ms": as_of_ms,
    }
