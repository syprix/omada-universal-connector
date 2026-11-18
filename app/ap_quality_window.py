"""Compact, bounded per-AP view of existing health, radio and retry/drop data."""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping

MAX_APS = 32
MAX_SCORES = 256
MAX_RETRY_SAMPLES = 256
_REF = re.compile(r"[0-9a-f]{24}\Z")
_BANDS = {
    "radioSetting2g": "2g", "radioSetting5g": "5g", "radioSetting5g1": "5g1",
    "radioSetting5g2": "5g2", "radioSetting6g": "6g",
}
_RADIO_FIELDS = {"channel", "channelWidth", "freq", "txPower", "txPowerLevel", "radioEnable"}


class ApQualityWindowError(ValueError):
    """Source responses or output bounds cannot be handled safely."""


def _int(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _bucket_values(rows: object, *, start: int, end: int, time_key: str,
                   value_key: str, maximum: int) -> tuple[list[dict[str, object]], bool]:
    if not isinstance(rows, list) or len(rows) > maximum:
        raise ApQualityWindowError("series_invalid")
    buckets: dict[int, list[tuple[int, int | float]]] = {}
    partial = False
    for row in rows:
        if not isinstance(row, Mapping):
            partial = True
            continue
        timestamp, value = row.get(time_key), row.get(value_key)
        valid_value = (_int(value, -(2**31), 2**31 - 1) if value_key == "score" else
                       type(value) in (int, float) and math.isfinite(value))
        if not _int(timestamp, start, end) or not valid_value:
            partial = True
            continue
        index = min(23, max(0, (timestamp - start) // 3_600_000))
        buckets.setdefault(index, []).append((timestamp, value))
    result: list[list[int | float]] = []
    for index, points in sorted(buckets.items()):
        values = [value for _, value in points]
        result.append([index, len(points), min(values), max(values),
                       max(points, key=lambda item: item[0])[1]])
    return result, partial


def _health(payload: object, site_ref: str, device_ref: str,
            start_ms: int, end_ms: int
            ) -> tuple[dict[str, object], bool]:
    if (not isinstance(payload, Mapping) or payload.get("status") != "ok" or
            payload.get("resource") != "ap_health_timeline" or
            payload.get("site_ref") != site_ref or payload.get("device_ref") != device_ref or
            type(payload.get("window_start_ms")) is not int or
            type(payload.get("window_end_ms")) is not int or
            payload["window_start_ms"] != start_ms or payload["window_end_ms"] != end_ms or
            end_ms - start_ms != 86_400_000 or
            not isinstance(payload.get("data"), Mapping)):
        return {"status": "unavailable", "partial": True}, True
    data = payload["data"]
    scores, invalid = _bucket_values(data.get("scores"), start=payload["window_start_ms"],
                                     end=payload["window_end_ms"], time_key="time_ms",
                                     value_key="score", maximum=MAX_SCORES)
    partial = payload.get("partial") is not False or invalid
    return ({"status": "partial" if partial else "ok",
             "window_start_ms": payload["window_start_ms"],
             "window_end_ms": payload["window_end_ms"],
             "hourly_score_summary": scores, "partial": partial}, partial)


def _radio(payload: object, device_ref: str) -> tuple[dict[str, object], bool]:
    if (not isinstance(payload, Mapping) or payload.get("status") != "ok" or
            payload.get("resource") != "radio_config" or
            payload.get("device_ref") != device_ref or
            not isinstance(payload.get("data"), Mapping)):
        return {"status": "unavailable", "bands": {}, "partial": True}, True
    data = payload["data"]
    bands: dict[str, object] = {}
    partial = False
    for source, band in _BANDS.items():
        if source not in data:
            continue
        row = data[source]
        if not isinstance(row, Mapping) or set(row) - _RADIO_FIELDS:
            partial = True
            continue
        values: dict[str, object] = {}
        for key, value in row.items():
            if key == "radioEnable":
                if type(value) is not bool:
                    partial = True
                    continue
            elif type(value) not in (int, str) or (isinstance(value, str) and len(value) > 24):
                partial = True
                continue
            values[key] = value
        bands[band] = values
    if not bands:
        partial = True
    return ({"status": "partial" if partial else "ok", "bands": bands,
             "partial": partial}, partial)


def _retry_rows(payload: object, site_ref: str, start_seconds: int,
                end_seconds: int) -> tuple[dict[str, dict[str, object]], bool]:
    if (not isinstance(payload, Mapping) or payload.get("status") != "ok" or
            payload.get("resource") != "ap_retry_drop" or
            payload.get("site_ref") != site_ref or
            payload.get("window_start_seconds") != start_seconds or
            payload.get("window_end_seconds") != end_seconds or
            not isinstance(payload.get("data"), Mapping)):
        return {}, True
    data = payload["data"]
    mapped: dict[str, dict[str, object]] = {}
    partial = data.get("partial") is not False
    for category in ("retry_aps", "dropped_aps"):
        rows = data.get(category)
        if not isinstance(rows, list) or len(rows) > 128:
            return {}, True
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("device_ref"), str) or not _REF.fullmatch(row["device_ref"]):
                partial = True
                continue
            entry = mapped.setdefault(row["device_ref"], {})
            samples = row.get("samples")
            sample_count = row.get("sample_count")
            start_key, end_key = (payload.get("window_start_seconds"),
                                  payload.get("window_end_seconds"))
            field = "retry" if category == "retry_aps" else "drop"
            if (not isinstance(samples, list) or len(samples) > MAX_RETRY_SAMPLES or
                    type(sample_count) is not int or sample_count < len(samples) or
                    type(start_key) is not int or type(end_key) is not int or
                    end_key - start_key != 86_400):
                entry[field] = {"status": "partial", "sample_count": 0,
                                "hourly_rate_summary": []}
                partial = True
                continue
            series = []
            for point in samples:
                if (not isinstance(point, Mapping) or type(point.get("time_seconds")) is not int or
                        type(point.get("count")) is not int or point["count"] < 0 or
                        type(point.get("rate")) not in (int, float) or
                        not math.isfinite(point["rate"])):
                    partial = True
                    continue
                series.append({"time_ms": point["time_seconds"] * 1000,
                               "rate": point["rate"]})
            hours, bad = _bucket_values(series, start=start_key * 1000, end=end_key * 1000,
                                        time_key="time_ms", value_key="rate",
                                        maximum=MAX_RETRY_SAMPLES)
            status_code = row.get("status")
            status_invalid = status_code is not None and status_code not in (0, 1)
            if status_invalid:
                partial = True
                status_code = None
            average = row.get("average_rate")
            average_valid = type(average) in (int, float) and math.isfinite(average)
            if average is not None and not average_valid:
                partial = True
            row_partial = bad or bool(row.get("missing_fields")) or status_invalid or (
                average is not None and not average_valid)
            entry[field] = {
                "status": "partial" if row_partial else "ok",
                "connection_status_code": status_code,
                "connection_status": ({0: "connected", 1: "disconnected"}.get(status_code)
                                      if status_code is not None else None),
                "average_rate": average if average_valid else None,
                "sample_count": sample_count,
                "included_in_window_count": len(series),
                "hourly_rate_summary": hours,
                "partial": row_partial,
            }
    return mapped, partial


def project_ap_quality_window(site_ref: str, inventory: object,
                              health_by_ref: Mapping[str, object],
                              radio_by_ref: Mapping[str, object],
                              retry_drop: object, window_start_ms: int | None = None,
                              window_end_ms: int | None = None) -> dict[str, object]:
    """Project bounded same-site AP evidence, preserving source windows and gaps."""
    if not isinstance(site_ref, str) or not _REF.fullmatch(site_ref):
        raise ApQualityWindowError("site_ref_invalid")
    if (not isinstance(inventory, Mapping) or inventory.get("status") != "ok" or
            inventory.get("resource") != "devices" or
            not isinstance(inventory.get("items"), list) or
            type(inventory.get("count")) is not int or
            inventory.get("count") != len(inventory["items"])):
        raise ApQualityWindowError("inventory_invalid")
    if window_start_ms is None and window_end_ms is None:
        sample = next((value for value in health_by_ref.values()
                       if isinstance(value, Mapping) and
                       type(value.get("window_start_ms")) is int and
                       type(value.get("window_end_ms")) is int), None)
        if sample is not None:
            window_start_ms, window_end_ms = sample["window_start_ms"], sample["window_end_ms"]
    if (type(window_start_ms) is not int or type(window_end_ms) is not int or
            window_start_ms < 0 or window_end_ms - window_start_ms != 86_400_000 or
            window_start_ms % 1000 or window_end_ms % 1000):
        raise ApQualityWindowError("window_invalid")
    aps = []
    unknown_type_count = 0
    for row in inventory["items"]:
        if not isinstance(row, Mapping):
            unknown_type_count += 1
            continue
        kind = row.get("device_type")
        if not isinstance(kind, str):
            unknown_type_count += 1
            continue
        normalized_kind = kind.strip().casefold()
        if normalized_kind in {"ap", "access point", "accesspoint"}:
            ref = row.get("device_ref")
            if not isinstance(ref, str) or not _REF.fullmatch(ref):
                raise ApQualityWindowError("inventory_invalid")
            aps.append(ref)
        elif normalized_kind not in {"gateway", "router", "gw", "switch", "sw", "olt"}:
            unknown_type_count += 1
    included = aps[:MAX_APS]
    omitted = max(0, len(aps) - len(included))
    start_seconds, end_seconds = window_start_ms // 1000, window_end_ms // 1000
    retries, retry_partial = _retry_rows(retry_drop, site_ref, start_seconds, end_seconds)
    results = []
    partial = bool(unknown_type_count or omitted or retry_partial)
    for ref in included:
        health, hp = _health(health_by_ref.get(ref), site_ref, ref,
                             window_start_ms, window_end_ms)
        radio, rp = _radio(radio_by_ref.get(ref), ref)
        retry = retries.get(ref)
        if retry is None:
            retry = {"status": "not_listed", "partial": True,
                     "interpretation": "absence from the bounded dashboard list is not zero retries or drops"}
        else:
            retry = {"status": "partial" if any(
                isinstance(value, Mapping) and value.get("partial") is True for value in retry.values()
            ) else "ok", **retry,
                "band_mapping": "not_returned_by_source"}
        row_partial = hp or rp or retry.get("partial") is True or retry.get("status") in {"not_listed", "partial"}
        partial = partial or row_partial
        results.append({"device_ref": ref, "health": health, "radio": radio,
                        "retry_drop": retry, "partial": row_partial})
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_ap_quality_window",
        "site_ref": site_ref,
        "window": {"start_ms": window_start_ms, "end_ms": window_end_ms,
                   "start_seconds": start_seconds, "end_seconds": end_seconds,
                   "duration_ms": 86_400_000, "duration_seconds": 86_400},
        "summary": {"inventory_ap_count": len(aps), "checked_ap_count": len(included),
                    "omitted_ap_count": omitted, "unknown_device_type_count": unknown_type_count,
                    "retry_drop_coverage": "bounded_site_dashboard_lists"},
        "data_scope": {
            "hourly_summary_columns": ["hour_index", "sample_count", "minimum", "maximum", "latest"],
            "health_score_scale": "unspecified",
            "retry_drop_rate_scale": "unspecified; source rate is per hour",
            "radio_settings": "current, not historical; raw values preserved",
            "retry_drop_band_mapping": "not_returned_by_source",
            "missing_data_is_not_zero": True,
        },
        "items": results, "partial": partial,
    }


def compare_passive_session_to_ap_quality(quality_report: object,
                                          session_header: object,
                                          session_samples: object,
                                          session_footer: object) -> dict[str, object]:
    """Join a saved passive session to AP report rows by exact opaque AP reference."""
    if (not isinstance(quality_report, Mapping) or
            quality_report.get("resource") != "site_ap_quality_window" or
            not isinstance(quality_report.get("items"), list) or
            len(quality_report["items"]) > MAX_APS):
        raise ApQualityWindowError("quality_report_invalid")
    if (not isinstance(session_header, Mapping) or
            session_header.get("record_type") != "session" or
            type(session_header.get("started_at_ms")) is not int or
            type(session_header.get("duration_limit_seconds")) is not int or
            not 1 <= session_header["duration_limit_seconds"] <= 600 or
            not isinstance(session_samples, list) or len(session_samples) > 180 or
            not isinstance(session_footer, Mapping) or
            session_footer.get("record_type") != "session_end" or
            type(session_footer.get("finished_at_ms")) is not int or
            session_footer["finished_at_ms"] < session_header["started_at_ms"] or
            session_footer["finished_at_ms"] - session_header["started_at_ms"] >
            session_header["duration_limit_seconds"] * 1000 + 1000 or
            session_footer.get("sample_count") != len(session_samples)):
        raise ApQualityWindowError("session_invalid")
    by_ref: dict[str, dict[str, object]] = {}
    for row in quality_report["items"]:
        if not isinstance(row, Mapping) or not isinstance(row.get("device_ref"), str) or not _REF.fullmatch(row["device_ref"]):
            raise ApQualityWindowError("quality_report_invalid")
        if row["device_ref"] in by_ref:
            raise ApQualityWindowError("quality_report_invalid")
        by_ref[row["device_ref"]] = row
    grouped: dict[str, list[Mapping[str, object]]] = {ref: [] for ref in by_ref}
    unassigned = unmatched = invalid = 0
    for sample in session_samples:
        if not isinstance(sample, Mapping):
            invalid += 1
            continue
        timestamp = sample.get("timestamp_ms")
        if type(timestamp) is not int:
            invalid += 1
            continue
        ref = sample.get("access_point_ref")
        if ref is None:
            unassigned += 1
        elif not isinstance(ref, str) or not _REF.fullmatch(ref):
            invalid += 1
        elif ref in grouped:
            grouped[ref].append(sample)
        else:
            unmatched += 1

    items = []
    for ref, row in by_ref.items():
        samples = grouped[ref]
        metrics: dict[str, object] = {}
        for field in ("rssi", "snr", "channel", "radio_id", "signal_level",
                      "rx_rate_kbps", "tx_rate_kbps"):
            values = [sample["metrics"][field] for sample in samples
                      if isinstance(sample.get("metrics"), Mapping) and
                      type(sample["metrics"].get(field)) is int]
            if values:
                if field in {"channel", "radio_id"}:
                    metrics[field] = {"sample_count": len(values),
                                      "value_counts": dict(sorted(Counter(values).items())),
                                      "unit": "categorical code"}
                else:
                    metrics[field] = {"sample_count": len(values), "minimum": min(values),
                                      "maximum": max(values),
                                      "mean": round(sum(values) / len(values), 2),
                                      "unit": "not assigned by this report"}
        health = row.get("health")
        window_start = health.get("window_start_ms") if isinstance(health, Mapping) else None
        window_end = health.get("window_end_ms") if isinstance(health, Mapping) else None
        if type(window_start) is int and type(window_end) is int:
            overlap = max(0, min(session_footer["finished_at_ms"], window_end) -
                          max(session_header["started_at_ms"], window_start))
            relation = "overlap" if overlap else "no_overlap"
        else:
            overlap, relation = None, "unknown"
        items.append({"device_ref": ref, "passive_sample_count": len(samples),
                      "passive_partial_sample_count": sum(sample.get("partial") is True
                                                           for sample in samples),
                      "passive_metrics": metrics, "session_to_health_window": relation,
                      "overlap_duration_ms": overlap,
                      "health": row.get("health"), "radio": row.get("radio"),
                      "retry_drop": row.get("retry_drop")})
    return {
        "status": "partial" if invalid or unmatched or unassigned or
                  quality_report.get("partial") is True else "ok",
        "resource": "ap_quality_session_comparison",
        "site_ref": quality_report.get("site_ref"),
        "session": {"started_at_ms": session_header["started_at_ms"],
                    "finished_at_ms": session_footer["finished_at_ms"],
                    "sample_count": len(session_samples),
                    "stop_reason": session_footer.get("stop_reason"),
                    "site_binding": "not_recorded_in_session_file"},
        "summary": {"matched_ap_count": sum(bool(grouped[ref]) for ref in by_ref),
                    "unmatched_ap_sample_count": unmatched,
                    "unassigned_sample_count": unassigned,
                    "invalid_sample_count": invalid,
                    "quality_report_ap_count": len(by_ref)},
        "items": items,
        "interpretation": "passive signal observations are shown beside AP history; no cause or ranking is inferred",
        "partial": bool(invalid or unmatched or unassigned or quality_report.get("partial") is True),
    }
