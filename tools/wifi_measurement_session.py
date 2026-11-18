#!/usr/bin/env python3
"""Record a short WLAN walk session from read-only local connector queries."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import stat
import sys
import threading
import time
from collections.abc import Callable
from typing import TextIO

if __package__:
    from .wifi_diagnose import CliError, DEFAULT_BASE_URL, _load_token, _origin, _request
else:
    from wifi_diagnose import CliError, DEFAULT_BASE_URL, _load_token, _origin, _request


MAX_DURATION_SECONDS = 600
MAX_INTERVAL_SECONDS = 30
MAX_SAMPLES = 180
CLIENT_REF_PATTERN = re.compile(r"[0-9a-f]{24}\Z")
_METRIC_FIELDS = {
    "rssi": (-(2**31), 2**31 - 1),
    "snr": (-(2**31), 2**31 - 1),
    "channel": (-(2**31), 2**31 - 1),
    "radio_id": (0, 3),
    "signal_level": (0, 100),
    "rx_rate_kbps": (0, 2**63 - 1),
    "tx_rate_kbps": (0, 2**63 - 1),
}


class MeasurementSessionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _validate_settings(site_ref: object, client_ref: object, duration_seconds: object,
                       interval_seconds: object, max_samples: object) -> None:
    if (not isinstance(site_ref, str) or not CLIENT_REF_PATTERN.fullmatch(site_ref) or
            not isinstance(client_ref, str) or not CLIENT_REF_PATTERN.fullmatch(client_ref)):
        raise MeasurementSessionError("reference_invalid")
    if (type(duration_seconds) is not int or not 1 <= duration_seconds <= MAX_DURATION_SECONDS or
            type(interval_seconds) is not int or not 1 <= interval_seconds <= MAX_INTERVAL_SECONDS or
            type(max_samples) is not int or not 1 <= max_samples <= MAX_SAMPLES):
        raise MeasurementSessionError("limits_invalid")


def _open_output(path: str) -> TextIO:
    if not isinstance(path, str) or not path or len(path) > 4096:
        raise MeasurementSessionError("output_unavailable")
    if not hasattr(os, "O_NOFOLLOW"):
        raise MeasurementSessionError("output_unavailable")
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_CLOEXEC", 0))
    fd = -1
    try:
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_nlink != 1):
            raise MeasurementSessionError("output_unavailable")
        os.fchmod(fd, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            raise MeasurementSessionError("output_unavailable")
        stream = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
        fd = -1
        return stream
    except MeasurementSessionError:
        raise
    except OSError:
        raise MeasurementSessionError("output_unavailable") from None
    finally:
        if fd >= 0:
            os.close(fd)


def _write_record(stream: TextIO, record: dict[str, object]) -> None:
    try:
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    except (OSError, TypeError, ValueError):
        raise MeasurementSessionError("output_write_failed") from None


def _project_detail(payload: object, client_ref: str) -> dict[str, object]:
    if (not isinstance(payload, dict) or payload.get("status") != "ok" or
            payload.get("resource") != "client_detail" or
            payload.get("client_ref") != client_ref or type(payload.get("wireless")) is not bool):
        raise MeasurementSessionError("client_detail_unavailable")
    if payload["wireless"] is not True:
        raise MeasurementSessionError("client_not_wireless")
    metrics: dict[str, int] = {}
    for field, (minimum, maximum) in _METRIC_FIELDS.items():
        if field not in payload:
            continue
        value = payload[field]
        if type(value) is not int or not minimum <= value <= maximum:
            raise MeasurementSessionError("client_detail_invalid")
        metrics[field] = value
    if not metrics:
        raise MeasurementSessionError("client_detail_invalid")
    ap_ref = payload.get("access_point_ref")
    if ap_ref is not None and (not isinstance(ap_ref, str) or
                               not CLIENT_REF_PATTERN.fullmatch(ap_ref)):
        raise MeasurementSessionError("client_detail_invalid")
    return {"metrics": metrics, "access_point_ref": ap_ref,
            "ap_assignment_status": "mapped" if ap_ref else "unavailable",
            "partial": (not {"rssi", "snr", "channel"}.issubset(metrics) or ap_ref is None)}


def run_session(*, site_ref: str, client_ref: str, output_path: str,
                duration_seconds: int, interval_seconds: int, max_samples: int,
                fetch: Callable[[str], object],
                stop_event: threading.Event | None = None,
                monotonic: Callable[[], float] = time.monotonic,
                sleep: Callable[[float], None] = time.sleep,
                now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000
                ) -> dict[str, object]:
    _validate_settings(site_ref, client_ref, duration_seconds, interval_seconds, max_samples)
    if stop_event is None:
        stop_event = threading.Event()
    device_path = f"/v1/sites/{site_ref}/devices"
    detail_path = f"/v1/sites/{site_ref}/clients/{client_ref}"
    try:
        inventory = fetch(device_path)
    except Exception:
        raise MeasurementSessionError("ap_inventory_unavailable") from None
    if (not isinstance(inventory, dict) or inventory.get("status") != "ok" or
            inventory.get("resource") != "devices" or not isinstance(inventory.get("items"), list)):
        raise MeasurementSessionError("ap_inventory_unavailable")

    stream = _open_output(output_path)
    start_ms = now_ms()
    started = monotonic()
    deadline = started + duration_seconds
    next_tick = started
    count = 0
    reason = "sample_limit"
    try:
        _write_record(stream, {
            "record_type": "session", "schema_version": 1,
            "started_at_ms": start_ms, "duration_limit_seconds": duration_seconds,
            "interval_seconds": interval_seconds, "sample_limit": max_samples,
            "collection": "read_only_connector_poll",
        })
        while count < max_samples:
            now = monotonic()
            if stop_event.is_set():
                reason = "user_stopped"
                break
            if now >= deadline:
                reason = "duration_limit"
                break
            if now < next_tick:
                wait = min(next_tick - now, deadline - now)
                if stop_event.wait(wait):
                    reason = "user_stopped"
                    break
            if stop_event.is_set():
                reason = "user_stopped"
                break
            if monotonic() >= deadline:
                reason = "duration_limit"
                break
            try:
                observation = _project_detail(fetch(detail_path), client_ref)
            except Exception:
                reason = "source_error"
                break
            count += 1
            _write_record(stream, {
                "record_type": "sample", "sample_index": count,
                "timestamp_ms": now_ms(), **observation,
            })
            next_tick = started + count * interval_seconds
            if count == max_samples:
                reason = "sample_limit"
                break
            if monotonic() >= deadline:
                reason = "duration_limit"
                break
        finished_ms = now_ms()
        _write_record(stream, {"record_type": "session_end", "finished_at_ms": finished_ms,
                               "sample_count": count, "stop_reason": reason})
    finally:
        stream.close()
    return {"status": "partial" if reason == "source_error" else "ok",
            "sample_count": count, "stop_reason": reason,
            "output": output_path}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-ref", required=True)
    parser.add_argument("--client-ref", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--duration-seconds", type=int, default=120)
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--max-samples", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        host, port = _origin(args.base_url)
        token = _load_token(args.token_file)
        stop_event = threading.Event()
        previous = {}

        def stop(_signum: int, _frame: object) -> None:
            stop_event.set()

        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, stop)
        try:
            result = run_session(
                site_ref=args.site_ref, client_ref=args.client_ref, output_path=args.output,
                duration_seconds=args.duration_seconds, interval_seconds=args.interval_seconds,
                max_samples=args.max_samples,
                fetch=lambda path: _request(host, port, path, token), stop_event=stop_event)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 1 if result["status"] == "partial" else 0
    except (MeasurementSessionError, CliError) as exc:
        code = exc.code
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        code = "session_failed"
    print(json.dumps({"status": "error", "error": code}, separators=(",", ":")))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
