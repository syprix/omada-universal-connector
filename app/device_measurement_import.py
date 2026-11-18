"""Import a bounded, privacy-filtered device measurement export offline."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import stat
from collections.abc import Mapping

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_SAMPLES = 10_000
MAX_LINE_CHARS = 16_384
_TIMESTAMP = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_SOURCES = {
    "wifi_source": {"system_log", "diagnostic_export"},
    "local_reachability_source": {"reachability_check", "diagnostic_export"},
    "dns_source": {"dns_resolution_check", "diagnostic_export"},
    "ipv4_source": {"interface_status", "diagnostic_export"},
    "ipv6_source": {"interface_status", "diagnostic_export"},
    "cellular_transition_source": {"system_log", "diagnostic_export"},
}
_VALUE_FIELDS = {
    "local_reachability": {"reachable", "unreachable"},
    "dns_status": {"resolved", "failed"},
    "ipv4_status": {"available", "unavailable"},
    "ipv6_status": {"available", "unavailable"},
    "cellular_transition": {"wifi_to_cellular", "cellular_to_wifi"},
}
_REQUIRED = {"timestamp", "wifi_connected", "wifi_source"}
_OPTIONAL_PAIRS = {
    "local_reachability": "local_reachability_source",
    "dns_status": "dns_source",
    "ipv4_status": "ipv4_source",
    "ipv6_status": "ipv6_source",
    "cellular_transition": "cellular_transition_source",
}
_ALLOWED_FIELDS = _REQUIRED | set(_OPTIONAL_PAIRS) | set(_OPTIONAL_PAIRS.values())
_CSV_HEADERS = {"timestamp", "wifi_connected", "wifi_source"} | set(_OPTIONAL_PAIRS) | set(_OPTIONAL_PAIRS.values())


class DeviceMeasurementError(ValueError):
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


def _validate_text(text: str) -> None:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise DeviceMeasurementError("input_invalid")


def _timestamp(value: object) -> tuple[int, str]:
    if not isinstance(value, str) or len(value) > 40 or not _TIMESTAMP.fullmatch(value):
        raise DeviceMeasurementError("timestamp_invalid")
    if value.endswith("Z"):
        normalized = value[:-1] + "+00:00"
    else:
        offset = value[-6:]
        normalized = value
        sign = offset[0]
        try:
            hours, minutes = int(offset[1:3]), int(offset[4:6])
        except (ValueError, IndexError):
            raise DeviceMeasurementError("timestamp_invalid") from None
        if minutes > 59 or hours > 14 or (hours == 14 and minutes != 0):
            raise DeviceMeasurementError("timezone_invalid")
        if sign not in {"+", "-"}:
            raise DeviceMeasurementError("timestamp_invalid")
        if offset == "-00:00":
            raise DeviceMeasurementError("timezone_unknown")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        raise DeviceMeasurementError("timestamp_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DeviceMeasurementError("timezone_required")
    utc = parsed.astimezone(dt.timezone.utc)
    delta = utc - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    if delta.days < 0:
        raise DeviceMeasurementError("timestamp_range_invalid")
    if delta.microseconds % 1000:
        raise DeviceMeasurementError("timestamp_precision_unsupported")
    timestamp_ms = delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000
    return timestamp_ms, utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _optional_pairs(row: Mapping[str, object]) -> dict[str, dict[str, str]]:
    observations: dict[str, dict[str, str]] = {}
    for field, source_field in _OPTIONAL_PAIRS.items():
        value = row.get(field)
        source = row.get(source_field)
        if field not in row and source_field not in row:
            continue
        if (field not in row or source_field not in row or
                value is None or source is None):
            raise DeviceMeasurementError("evidence_pair_incomplete")
        if not isinstance(value, str) or value not in _VALUE_FIELDS[field]:
            raise DeviceMeasurementError("measurement_value_invalid")
        if not isinstance(source, str) or source not in _SOURCES[source_field]:
            raise DeviceMeasurementError("evidence_source_invalid")
        name = {
            "dns_status": "dns",
            "ipv4_status": "ipv4",
            "ipv6_status": "ipv6",
        }.get(field, field)
        observations[name] = {
            "status": value,
            "source_kind": source,
            "verification": "imported_unverified",
        }
    return observations


def _project_rows(rows: list[Mapping[str, object]]) -> dict[str, object]:
    if not rows or len(rows) > MAX_SAMPLES:
        raise DeviceMeasurementError("sample_count_invalid")
    result: list[dict[str, object]] = []
    previous_ms: int | None = None
    coverage = {"wifi": 0, "local_reachability": 0, "dns": 0,
                "ipv4": 0, "ipv6": 0, "cellular_transition": 0}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) - _ALLOWED_FIELDS:
            raise DeviceMeasurementError("schema_invalid")
        if not _REQUIRED.issubset(row):
            raise DeviceMeasurementError("required_field_missing")
        timestamp_ms, timestamp_utc = _timestamp(row.get("timestamp"))
        if previous_ms is not None and timestamp_ms <= previous_ms:
            raise DeviceMeasurementError("timestamps_not_increasing")
        previous_ms = timestamp_ms
        connected = row.get("wifi_connected")
        if type(connected) is not bool:
            raise DeviceMeasurementError("wifi_state_invalid")
        wifi_source = row.get("wifi_source")
        if not isinstance(wifi_source, str) or wifi_source not in _SOURCES["wifi_source"]:
            raise DeviceMeasurementError("evidence_source_invalid")
        observations = _optional_pairs(row)
        record: dict[str, object] = {
            "timestamp_ms": timestamp_ms,
            "timestamp_utc": timestamp_utc,
            "wifi": {
                "connected": connected,
                "source_kind": wifi_source,
                "verification": "imported_unverified",
            },
        }
        record.update(observations)
        coverage["wifi"] += 1
        for key in observations:
            coverage[key] += 1
        result.append(record)
    return {
        "status": "ok",
        "resource": "device_measurements",
        "schema_version": 1,
        "source_verification": "declared_sources_not_independently_verified",
        "sample_count": len(result),
        "window": {"start_utc": result[0]["timestamp_utc"],
                   "end_utc": result[-1]["timestamp_utc"]},
        "coverage": coverage,
        "observations": result,
        "partial": False,
    }


def parse_json(text: str) -> dict[str, object]:
    _validate_text(text)
    try:
        payload = json.loads(text, object_pairs_hook=_pairs_no_duplicates,
                             parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError, RecursionError):
        raise DeviceMeasurementError("json_invalid") from None
    if (not isinstance(payload, dict) or set(payload) != {"schema_version", "samples"} or
            type(payload.get("schema_version")) is not int or payload["schema_version"] != 1 or
            not isinstance(payload.get("samples"), list)):
        raise DeviceMeasurementError("schema_invalid")
    if any(not isinstance(row, dict) for row in payload["samples"]):
        raise DeviceMeasurementError("schema_invalid")
    return _project_rows(payload["samples"])


def parse_csv(text: str) -> dict[str, object]:
    _validate_text(text)
    previous_limit = csv.field_size_limit()
    csv.field_size_limit(MAX_LINE_CHARS)
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames
        if (not headers or any(not isinstance(name, str) or not name for name in headers) or
                len(headers) != len(set(headers)) or set(headers) - _CSV_HEADERS or
                not {"timestamp", "wifi_connected", "wifi_source"}.issubset(headers)):
            raise DeviceMeasurementError("csv_header_invalid")
        if any((name in headers) != (source in headers)
               for name, source in _OPTIONAL_PAIRS.items()):
            raise DeviceMeasurementError("csv_header_invalid")
        rows: list[dict[str, object]] = []
        for row in reader:
            if len(rows) >= MAX_SAMPLES:
                raise DeviceMeasurementError("sample_count_invalid")
            if None in row or any(value is None for value in row.values()):
                raise DeviceMeasurementError("csv_row_invalid")
            normalized: dict[str, object] = {"timestamp": row["timestamp"]}
            bool_value = row["wifi_connected"]
            if bool_value not in {"true", "false"}:
                raise DeviceMeasurementError("wifi_state_invalid")
            normalized["wifi_connected"] = bool_value == "true"
            normalized["wifi_source"] = row["wifi_source"]
            for field, source in _OPTIONAL_PAIRS.items():
                if field not in headers:
                    continue
                value, source_value = row[field], row[source]
                if bool(value) != bool(source_value):
                    raise DeviceMeasurementError("evidence_pair_incomplete")
                if value:
                    normalized[field] = value
                    normalized[source] = source_value
            rows.append(normalized)
        return _project_rows(rows)
    except csv.Error:
        raise DeviceMeasurementError("csv_invalid") from None
    finally:
        csv.field_size_limit(previous_limit)


def _read_input(path: str) -> bytes:
    if not isinstance(path, str) or not path or len(path) > 4096 or not hasattr(os, "O_NOFOLLOW"):
        raise DeviceMeasurementError("input_unavailable")
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_nlink != 1 or info.st_size > MAX_INPUT_BYTES):
            raise DeviceMeasurementError("input_invalid")
        raw = bytearray()
        while len(raw) <= MAX_INPUT_BYTES:
            block = os.read(fd, min(65_536, MAX_INPUT_BYTES + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        if len(raw) > MAX_INPUT_BYTES:
            raise DeviceMeasurementError("input_invalid")
        return bytes(raw)
    except DeviceMeasurementError:
        raise
    except OSError:
        raise DeviceMeasurementError("input_unavailable") from None
    finally:
        if fd >= 0:
            os.close(fd)


def import_file(path: str, input_format: str) -> dict[str, object]:
    if not isinstance(input_format, str) or input_format not in {"csv", "json"}:
        raise DeviceMeasurementError("format_invalid")
    raw = _read_input(path)
    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        raise DeviceMeasurementError("input_encoding_invalid") from None
    return parse_csv(text) if input_format == "csv" else parse_json(text)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--format", choices=("csv", "json"), required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        result = import_file(args.input, args.format)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except DeviceMeasurementError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        print(json.dumps({"status": "error", "error": "import_failed"}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
