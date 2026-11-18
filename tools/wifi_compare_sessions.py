#!/usr/bin/env python3
"""Compare two saved WLAN walk sessions offline without controller access."""
from __future__ import annotations

import argparse
import json
import os
import re
import stat


MAX_SESSION_BYTES = 512 * 1024
MAX_SESSION_SAMPLES = 180
AP_REF_PATTERN = re.compile(r"[0-9a-f]{24}\Z")
METRIC_BOUNDS = {
    "rssi": (-(2**31), 2**31 - 1), "snr": (-(2**31), 2**31 - 1),
    "channel": (-(2**31), 2**31 - 1), "radio_id": (0, 3),
    "signal_level": (0, 100), "rx_rate_kbps": (0, 2**63 - 1),
    "tx_rate_kbps": (0, 2**63 - 1),
}
_CATEGORICAL_METRICS = {"channel", "radio_id"}


class SessionCompareError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("invalid_constant")


def _read_session(path: str) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    if (not isinstance(path, str) or not path or len(path) > 4096 or
            not hasattr(os, "O_NOFOLLOW")):
        raise SessionCompareError("session_file_invalid")
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_nlink != 1 or info.st_size > MAX_SESSION_BYTES):
            raise SessionCompareError("session_file_invalid")
        raw = bytearray()
        while len(raw) <= MAX_SESSION_BYTES:
            block = os.read(fd, min(65536, MAX_SESSION_BYTES + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        if len(raw) > MAX_SESSION_BYTES:
            raise SessionCompareError("session_file_invalid")
        text = bytes(raw).decode("utf-8", errors="strict")
    except SessionCompareError:
        raise
    except (OSError, UnicodeError):
        raise SessionCompareError("session_file_invalid") from None
    finally:
        if fd >= 0:
            os.close(fd)

    lines = text.splitlines()
    if len(lines) < 2 or len(lines) > MAX_SESSION_SAMPLES + 2 or any(len(line) > 8192 for line in lines):
        raise SessionCompareError("session_format_invalid")
    try:
        rows = [json.loads(line, object_pairs_hook=_pairs_no_duplicates,
                           parse_constant=_reject_constant) for line in lines]
    except (json.JSONDecodeError, ValueError):
        raise SessionCompareError("session_format_invalid") from None
    if any(not isinstance(row, dict) for row in rows):
        raise SessionCompareError("session_format_invalid")
    header = rows[0]
    footer = rows[-1]
    samples = rows[1:-1]
    if (header.get("record_type") != "session" or header.get("schema_version") != 1 or
            header.get("collection") != "read_only_connector_poll" or
            type(header.get("started_at_ms")) is not int or
            type(header.get("duration_limit_seconds")) is not int or
            not 1 <= header["duration_limit_seconds"] <= 600 or
            type(header.get("interval_seconds")) is not int or
            not 1 <= header["interval_seconds"] <= 30 or
            type(header.get("sample_limit")) is not int or
            not 1 <= header["sample_limit"] <= MAX_SESSION_SAMPLES or
            footer.get("record_type") != "session_end" or
            type(footer.get("finished_at_ms")) is not int or
            type(footer.get("sample_count")) is not int or
            footer["sample_count"] != len(samples) or
            footer.get("stop_reason") not in {"sample_limit", "duration_limit",
                                               "user_stopped", "source_error"} or
            len(samples) > header["sample_limit"]):
        raise SessionCompareError("session_format_invalid")
    previous_time = header["started_at_ms"]
    for index, sample in enumerate(samples, start=1):
        metrics = sample.get("metrics")
        ap_ref = sample.get("access_point_ref")
        if (sample.get("record_type") != "sample" or sample.get("sample_index") != index or
                type(sample.get("sample_index")) is not int or
                type(sample.get("timestamp_ms")) is not int or
                sample["timestamp_ms"] < previous_time or
                not isinstance(metrics, dict) or type(sample.get("partial")) is not bool or
                sample.get("sample_status") not in {"ok", "incomplete", "not_wireless",
                                                     "read_unavailable"} or
                sample.get("ap_assignment_status") not in {"mapped", "unavailable",
                                                           "not_applicable"} or
                (ap_ref is not None and
                 (not isinstance(ap_ref, str) or not AP_REF_PATTERN.fullmatch(ap_ref))) or
                (sample.get("ap_assignment_status") == "mapped") != (ap_ref is not None)):
            raise SessionCompareError("session_format_invalid")
        if set(metrics) - set(METRIC_BOUNDS):
            raise SessionCompareError("session_format_invalid")
        for field, value in metrics.items():
            minimum, maximum = METRIC_BOUNDS[field]
            if type(value) is not int or not minimum <= value <= maximum:
                raise SessionCompareError("session_format_invalid")
        previous_time = sample["timestamp_ms"]
    if (footer["finished_at_ms"] < previous_time or
            previous_time > header["started_at_ms"] +
            header["duration_limit_seconds"] * 1000):
        raise SessionCompareError("session_format_invalid")
    return header, samples, footer


def _signal_summary(samples: list[dict[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for field in METRIC_BOUNDS:
        values = [sample["metrics"][field] for sample in samples
                  if field in sample["metrics"]]
        if values:
            output[field] = {"sample_count": len(values), "minimum": min(values),
                             "maximum": max(values), "average": sum(values) / len(values)}
        else:
            output[field] = {"sample_count": 0}
    mapped = [sample["access_point_ref"] for sample in samples
              if sample["ap_assignment_status"] == "mapped"]
    ap_changes = 0
    last_ref = None
    for sample in samples:
        if sample["ap_assignment_status"] != "mapped":
            last_ref = None
            continue
        current = sample["access_point_ref"]
        if last_ref is not None and current != last_ref:
            ap_changes += 1
        last_ref = current
    return {
        "sample_count": len(samples), "signal_metrics": output,
        "ap_assignment_sample_count": len(mapped),
        "distinct_ap_references": len(set(mapped)), "ap_changes_observed": ap_changes,
        "not_wireless_samples": sum(sample["sample_status"] == "not_wireless"
                                     for sample in samples),
        "unavailable_read_samples": sum(sample["sample_status"] == "read_unavailable"
                                         for sample in samples),
        "partial_sample_count": sum(sample["partial"] for sample in samples),
    }


def compare_sessions(first_path: str, second_path: str) -> dict[str, object]:
    first_header, first_samples, first_footer = _read_session(first_path)
    second_header, second_samples, second_footer = _read_session(second_path)
    conditions_match = all(first_header[field] == second_header[field] for field in (
        "duration_limit_seconds", "interval_seconds", "sample_limit"))
    aligned_count = min(len(first_samples), len(second_samples)) if conditions_match else 0
    metric_deltas: dict[str, object] = {}
    categorical_matches: dict[str, object] = {}
    if conditions_match:
        for field in METRIC_BOUNDS:
            pairs = [(left["metrics"][field], right["metrics"][field])
                     for left, right in zip(first_samples[:aligned_count],
                                            second_samples[:aligned_count])
                     if field in left["metrics"] and field in right["metrics"]]
            if field in _CATEGORICAL_METRICS:
                categorical_matches[field] = {
                    "paired_count": len(pairs),
                    "matching_count": sum(left == right for left, right in pairs),
                    "different_count": sum(left != right for left, right in pairs),
                }
            elif pairs:
                deltas = [right - left for left, right in pairs]
                metric_deltas[field] = {
                    "paired_count": len(deltas), "average_delta_second_minus_first":
                    sum(deltas) / len(deltas), "minimum_delta": min(deltas),
                    "maximum_delta": max(deltas),
                }
            else:
                metric_deltas[field] = {"paired_count": 0}
    coverage_match = len(first_samples) == len(second_samples)
    complete = (conditions_match and coverage_match and not first_footer.get("stop_reason") == "source_error" and
                not second_footer.get("stop_reason") == "source_error" and
                not any(sample["partial"] for sample in first_samples + second_samples))
    return {
        "status": "ok" if complete else "partial",
        "comparison_status": "comparable" if conditions_match else "conditions_differ",
        "conditions_match": conditions_match,
        "conditions": {
            "first": {key: first_header[key] for key in
                      ("duration_limit_seconds", "interval_seconds", "sample_limit")},
            "second": {key: second_header[key] for key in
                       ("duration_limit_seconds", "interval_seconds", "sample_limit")},
        },
        "coverage_match": coverage_match,
        "compared_sample_indices": aligned_count,
        "first": _signal_summary(first_samples),
        "second": _signal_summary(second_samples),
        "metric_deltas_second_minus_first": metric_deltas,
        "categorical_metric_matches": categorical_matches,
        "ap_reference_comparison": "not_performed_across_sessions",
        "interruption_note": "not-wireless states and read gaps are counted as observations; no outage cause is inferred",
        "partial": not complete,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        result = compare_sessions(args.first, args.second)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0 if result["status"] == "ok" else 1
    except SessionCompareError as exc:
        code = exc.code
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        code = "comparison_failed"
    print(json.dumps({"status": "error", "error": code}, separators=(",", ":")))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
