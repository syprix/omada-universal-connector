#!/usr/bin/env python3
"""Diagnose imported DNS observations using saved, redacted local context."""
from pathlib import Path
import argparse
import json
import sys

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.device_measurement_import import (  # noqa: E402
    DeviceMeasurementError, _pairs_no_duplicates, _read_input, _reject_constant,
    import_file,
)
from app.dns_incident_diagnosis import (  # noqa: E402
    DnsIncidentDiagnosisError, diagnose_dns_incident,
)


def _read_json(path: str) -> object:
    try:
        return json.loads(_read_input(path).decode("utf-8-sig", errors="strict"),
                          object_pairs_hook=_pairs_no_duplicates,
                          parse_constant=_reject_constant)
    except DeviceMeasurementError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise DeviceMeasurementError("context_file_invalid") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", required=True,
                        help="local CSV/JSON input previously supported by the device importer")
    parser.add_argument("--format", choices=("csv", "json"), required=True)
    parser.add_argument("--dns-snapshot", help="optional redacted config_snapshot.py output")
    parser.add_argument("--network-summary", help="optional ssid_network_summary JSON output")
    parser.add_argument("--start-ms", type=int)
    parser.add_argument("--end-ms", type=int)
    parser.add_argument("--include-observations", action="store_true",
                        help="include allow-listed per-sample detail in the local report")
    try:
        args = parser.parse_args(argv)
        if (args.start_ms is None) != (args.end_ms is None):
            raise DnsIncidentDiagnosisError("time_window_invalid")
        measurements = import_file(args.measurements, args.format)
        rows = measurements.get("observations")
        if not isinstance(rows, list) or not rows:
            raise DnsIncidentDiagnosisError("measurements_invalid")
        start_ms = args.start_ms if args.start_ms is not None else rows[0]["timestamp_ms"]
        end_ms = args.end_ms if args.end_ms is not None else rows[-1]["timestamp_ms"]
        snapshot = _read_json(args.dns_snapshot) if args.dns_snapshot else None
        network_summary = _read_json(args.network_summary) if args.network_summary else None
        result = diagnose_dns_incident(
            measurements, start_ms=start_ms, end_ms=end_ms,
            snapshot=snapshot, network_summary=network_summary,
            include_observations=args.include_observations)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False))
        return 0
    except DeviceMeasurementError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except DnsIncidentDiagnosisError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        print('{"status":"error","error":"diagnosis_failed"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
