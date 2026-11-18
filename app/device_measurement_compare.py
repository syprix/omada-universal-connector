"""Align imported device observations with offline Omada timeline exports."""
from __future__ import annotations

import argparse
import bisect
import json
import time
from typing import Callable

from app.device_measurement_import import (
    DeviceMeasurementError, _pairs_no_duplicates, _read_input, _reject_constant,
    import_file,
)
from tools.wifi_compare_sessions import SessionCompareError, _read_session

MAX_WINDOW_MS = 86_400_000
MAX_TOLERANCE_MS = 30_000
MAX_TIMELINE_EVENTS = 4096
_TIMELINE_KINDS = ("connect", "association", "roaming", "disconnect")


class DeviceMeasurementCompareError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _validate_window(start_ms: object, end_ms: object, tolerance_ms: object,
                     as_of_ms: object) -> None:
    if (type(start_ms) is not int or type(end_ms) is not int or
            start_ms < 0 or end_ms < start_ms or end_ms - start_ms > MAX_WINDOW_MS):
        raise DeviceMeasurementCompareError("time_window_invalid")
    if type(tolerance_ms) is not int or not 0 <= tolerance_ms <= MAX_TOLERANCE_MS:
        raise DeviceMeasurementCompareError("tolerance_invalid")
    if type(as_of_ms) is not int or as_of_ms < 0:
        raise DeviceMeasurementCompareError("as_of_invalid")


def _load_timeline(path: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    try:
        raw = _read_input(path)
        report = json.loads(raw.decode("utf-8-sig", errors="strict"),
                            object_pairs_hook=_pairs_no_duplicates,
                            parse_constant=_reject_constant)
    except DeviceMeasurementError:
        raise DeviceMeasurementCompareError("timeline_file_invalid") from None
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise DeviceMeasurementCompareError("timeline_file_invalid") from None
    if not isinstance(report, dict):
        raise DeviceMeasurementCompareError("timeline_format_invalid")
    client = report.get("client")
    timelines = client.get("timelines") if isinstance(client, dict) else None
    if not isinstance(timelines, dict) or not set(timelines).intersection(_TIMELINE_KINDS):
        raise DeviceMeasurementCompareError("timeline_format_invalid")

    events: list[dict[str, object]] = []
    source_windows: dict[str, object] = {}
    source_partial = client.get("status") != "ok" if isinstance(client, dict) else True
    for kind in _TIMELINE_KINDS:
        item = timelines.get(kind)
        if not isinstance(item, dict):
            source_windows[kind] = {"status": "unavailable", "partial": True}
            source_partial = True
            continue
        state = item.get("status")
        if not isinstance(state, str) or state not in {"ok", "partial"}:
            source_windows[kind] = {"status": "unavailable", "partial": True}
            source_partial = True
            continue
        window = item.get("window")
        start, end = (window.get("start_ms"), window.get("end_ms")) if isinstance(window, dict) else (None, None)
        if (type(start) is not int or type(end) is not int or start < 0 or end < start or
                end - start > MAX_WINDOW_MS):
            source_windows[kind] = {"status": "invalid_window", "partial": True}
            source_partial = True
            continue
        partial = item.get("partial") is not False or state != "ok"
        source_windows[kind] = {"status": state, "start_ms": start,
                                "end_ms": end, "partial": partial}
        data = item.get("data")
        sessions = data.get("sessions") if isinstance(data, dict) else None
        if not isinstance(sessions, list) or len(sessions) > 128:
            source_windows[kind]["partial"] = True
            source_partial = True
            continue
        for session in sessions:
            rows = session.get("events") if isinstance(session, dict) else None
            if not isinstance(rows, list):
                source_windows[kind]["partial"] = True
                source_partial = True
                continue
            if len(events) + len(rows) > MAX_TIMELINE_EVENTS:
                raise DeviceMeasurementCompareError("timeline_event_limit")
            for row in rows:
                if not isinstance(row, dict):
                    source_windows[kind]["partial"] = True
                    source_partial = True
                    continue
                timestamp = row.get("time_ms")
                code = row.get("event_type")
                if (type(timestamp) is not int or not start <= timestamp <= end):
                    source_windows[kind]["partial"] = True
                    source_partial = True
                    continue
                event: dict[str, object] = {"timestamp_ms": timestamp, "kind": kind}
                if type(code) is int and -(2**31) <= code <= 2**31 - 1:
                    event["event_type_code"] = code
                else:
                    event["event_type_code"] = None
                    source_windows[kind]["partial"] = True
                    source_partial = True
                events.append(event)
        source_partial = source_partial or source_windows[kind]["partial"] is True
    events.sort(key=lambda row: (row["timestamp_ms"], row["kind"],
                                 row["event_type_code"] if type(row["event_type_code"]) is int else -1))
    return events, {"partial": source_partial, "windows": source_windows}


def _window_coverage(source_window: dict[str, object], start_ms: int,
                     end_ms: int) -> str:
    if (type(source_window.get("start_ms")) is int and
            type(source_window.get("end_ms")) is int and
            source_window["start_ms"] <= start_ms and source_window["end_ms"] >= end_ms):
        return "covers_requested_window"
    return "does_not_cover_requested_window"


def _within_window(points: list[dict[str, object]], start_ms: int,
                   end_ms: int) -> list[dict[str, object]]:
    return [point for point in points
            if type(point.get("timestamp_ms")) is int and
            start_ms <= point["timestamp_ms"] <= end_ms]


def _nearest(point_ms: int, points: list[dict[str, object]],
             timestamps: list[int], tolerance_ms: int
             ) -> tuple[str, list[dict[str, object]]]:
    if not points:
        return "no_match_within_tolerance", []
    index = bisect.bisect_left(timestamps, point_ms)
    candidate_times = set()
    if index < len(timestamps):
        candidate_times.add(timestamps[index])
    if index > 0:
        candidate_times.add(timestamps[index - 1])
    nearest_distance = min(abs(value - point_ms) for value in candidate_times)
    if nearest_distance > tolerance_ms:
        return "no_match_within_tolerance", []
    nearest_times = {value for value in candidate_times
                     if abs(value - point_ms) == nearest_distance}
    nearest: list[dict[str, object]] = []
    for value in nearest_times:
        left, right = bisect.bisect_left(timestamps, value), bisect.bisect_right(timestamps, value)
        nearest.extend(points[left:right])
    if len(nearest) > 1:
        return "ambiguous_nearest", nearest
    return "matched", nearest


def _age(latest_ms: int | None, as_of_ms: int) -> dict[str, object]:
    if latest_ms is None:
        return {"latest_observation_ms": None, "age_ms": None,
                "reason": "no_observation_in_requested_window"}
    age = as_of_ms - latest_ms
    return {"latest_observation_ms": latest_ms, "age_ms": age,
            "reason": ("timestamp_after_comparison_time" if age < 0 else
                       "relative_to_comparison_time")}


def compare_device_sources(*, device_path: str, device_format: str,
                           timeline_path: str, session_path: str,
                           start_ms: int, end_ms: int, tolerance_ms: int,
                           as_of_ms: int | None = None,
                           now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000
                           ) -> dict[str, object]:
    if as_of_ms is None:
        as_of_ms = now_ms()
    _validate_window(start_ms, end_ms, tolerance_ms, as_of_ms)
    try:
        imported = import_file(device_path, device_format)
    except DeviceMeasurementError as exc:
        raise DeviceMeasurementCompareError(exc.code) from None
    try:
        timeline_events, timeline_info = _load_timeline(timeline_path)
    except DeviceMeasurementCompareError:
        raise
    try:
        session_header, raw_samples, session_footer = _read_session(session_path)
    except SessionCompareError as exc:
        detail = exc.code.removeprefix("session_")
        raise DeviceMeasurementCompareError("session_" + detail) from None

    device_points = _within_window(imported["observations"], start_ms, end_ms)
    client_events = _within_window(timeline_events, start_ms, end_ms)
    session_points = _within_window(raw_samples, start_ms, end_ms)
    timeline_times = [int(item["timestamp_ms"]) for item in client_events]
    session_times = [int(item["timestamp_ms"]) for item in session_points]
    comparisons: list[dict[str, object]] = []
    agreements = disagreements = unassessable = unmatched = 0
    for point in device_points:
        timestamp = int(point["timestamp_ms"])
        event_state, event_matches = _nearest(timestamp, client_events,
                                              timeline_times, tolerance_ms)
        event_output: dict[str, object] = {"status": event_state}
        if event_state == "matched":
            event = event_matches[0]
            event_output.update({"timestamp_ms": event["timestamp_ms"],
                                 "delta_ms_from_device": int(event["timestamp_ms"]) - timestamp,
                                 "kind": event["kind"],
                                 "event_type_code": event["event_type_code"]})
        elif event_state == "ambiguous_nearest":
            event_output["candidate_count"] = len(event_matches)

        session_state, sample_matches = _nearest(timestamp, session_points,
                                                  session_times, tolerance_ms)
        session_output: dict[str, object] = {"status": session_state}
        if session_state == "matched":
            sample = sample_matches[0]
            sample_time = int(sample["timestamp_ms"])
            session_output.update({
                "timestamp_ms": sample_time,
                "delta_ms_from_device": sample_time - timestamp,
                "sample_status": sample["sample_status"],
                "partial": sample["partial"],
                "metrics": dict(sample["metrics"]),
            })
        elif session_state == "ambiguous_nearest":
            session_output["candidate_count"] = len(sample_matches)

        relation = "unassessable"
        wifi_connected = point["wifi"]["connected"]
        if session_state == "matched":
            state = sample_matches[0]["sample_status"]
            if state in {"ok", "incomplete"}:
                relation = "agrees" if wifi_connected else "disagrees"
            elif state == "not_wireless":
                relation = "agrees" if not wifi_connected else "disagrees"
        if relation == "agrees":
            agreements += 1
        elif relation == "disagrees":
            disagreements += 1
        else:
            unassessable += 1
        if event_state != "matched" or session_state != "matched":
            unmatched += 1
        comparisons.append({
            "timestamp_ms": timestamp,
            "device_observations": {key: value for key, value in point.items()
                                     if key not in {"timestamp_ms", "timestamp_utc"}},
            "client_timeline": event_output,
            "passive_wlan_session": session_output,
            "wifi_state_relation_to_passive_sample": relation,
        })

    session_gap_count = sum(
        int(right["timestamp_ms"]) - int(left["timestamp_ms"]) >
        int(session_header["interval_seconds"]) * 1500
        for left, right in zip(session_points, session_points[1:])
    )
    session_coverage = {
        "window_start_ms": session_header["started_at_ms"],
        "window_end_ms": session_footer["finished_at_ms"],
        "coverage": _window_coverage({"start_ms": session_header["started_at_ms"],
                                       "end_ms": session_footer["finished_at_ms"]},
                                     start_ms, end_ms),
        "stop_reason": session_footer["stop_reason"],
        "partial": (session_footer["stop_reason"] == "source_error" or
                    any(sample["partial"] for sample in session_points) or
                    not session_points or session_gap_count > 0),
        "sample_gap_count": session_gap_count,
    }
    timeline_coverage = {kind: {**item, "coverage": _window_coverage(item, start_ms, end_ms)}
                         if isinstance(item, dict) else {"status": "unavailable", "partial": True}
                         for kind, item in timeline_info["windows"].items()}
    latest_device = max((int(point["timestamp_ms"]) for point in device_points), default=None)
    latest_event = max((int(point["timestamp_ms"]) for point in client_events), default=None)
    latest_session = max((int(point["timestamp_ms"]) for point in session_points), default=None)
    device_partial = not device_points
    partial = (device_partial or
               timeline_info["partial"] or session_coverage["partial"] or
               session_coverage["coverage"] != "covers_requested_window" or
               any(item.get("coverage") != "covers_requested_window" or item.get("partial") is True
                   for item in timeline_coverage.values()))
    return {
        "status": "partial" if partial else "ok",
        "resource": "device_measurement_comparison",
        "interpretation": "observations_only_no_cause_inferred",
        "window": {"start_ms": start_ms, "end_ms": end_ms,
                   "tolerance_ms": tolerance_ms, "as_of_ms": as_of_ms},
        "source_freshness": {
            "device_measurements": _age(latest_device, as_of_ms),
            "client_timeline": {"latest_event_ms": latest_event, "age_ms": None,
                                 "reason": "source_export_has_no_observation_timestamp"},
            "passive_wlan_session": _age(latest_session, as_of_ms),
        },
        "source_coverage": {
            "device_measurements": {"status": "ok" if device_points else "no_samples",
                                    "sample_count_in_window": len(device_points),
                                    "excluded_outside_window_count":
                                    len(imported["observations"]) - len(device_points),
                                    "field_coverage": imported["coverage"],
                                    "source_verification": imported["source_verification"],
                                    "partial": device_partial},
            "client_timeline": {"windows": timeline_coverage,
                                "event_count_in_window": len(client_events),
                                "partial": timeline_info["partial"]},
            "passive_wlan_session": {**session_coverage,
                                     "sample_count_in_window": len(session_points)},
        },
        "comparison": {
            "device_sample_count": len(device_points),
            "wifi_state_agreements": agreements,
            "wifi_state_disagreements": disagreements,
            "wifi_state_unassessable": unassessable,
            "samples_missing_one_or_more_sources": unmatched,
            "observations": comparisons,
            "difference_note": "Only an explicit wireless or not-wireless passive sample is compared with device Wi-Fi state. Event route family and numeric code are preserved as observations; their cause is not inferred.",
        },
        "partial": partial,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-input", required=True)
    parser.add_argument("--device-format", choices=("csv", "json"), required=True)
    parser.add_argument("--client-timeline", required=True,
                        help="sanitized JSON report from tools/wifi_diagnose.py --client-timeline")
    parser.add_argument("--session", required=True, help="local JSONL from wifi_measurement_session.py")
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--tolerance-ms", type=int, required=True)
    parser.add_argument("--as-of-ms", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        result = compare_device_sources(
            device_path=args.device_input, device_format=args.device_format,
            timeline_path=args.client_timeline, session_path=args.session,
            start_ms=args.start_ms, end_ms=args.end_ms, tolerance_ms=args.tolerance_ms,
            as_of_ms=args.as_of_ms,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0 if result["status"] == "ok" else 1
    except DeviceMeasurementCompareError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        print(json.dumps({"status": "error", "error": "comparison_failed"}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
