#!/usr/bin/env python3
"""Join a saved passive WLAN session to a site AP quality report offline."""
from pathlib import Path
import argparse
import json
import sys

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.device_measurement_import import (  # noqa: E402
    DeviceMeasurementError, _pairs_no_duplicates, _read_input, _reject_constant,
)
from app.ap_quality_window import (  # noqa: E402
    ApQualityWindowError, compare_passive_session_to_ap_quality,
)
from tools.wifi_compare_sessions import SessionCompareError, _read_session  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality-report", required=True,
                        help="saved output of GET /aps/quality-window or its MCP tool")
    parser.add_argument("--session", required=True,
                        help="owner-only JSONL file made by wifi_measurement_session.py")
    try:
        args = parser.parse_args(argv)
        try:
            quality = json.loads(_read_input(args.quality_report).decode("utf-8-sig", errors="strict"),
                                 object_pairs_hook=_pairs_no_duplicates,
                                 parse_constant=_reject_constant)
        except DeviceMeasurementError:
            raise
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
            raise DeviceMeasurementError("quality_report_invalid") from None
        header, samples, footer = _read_session(args.session)
        result = compare_passive_session_to_ap_quality(quality, header, samples, footer)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False))
        return 0
    except DeviceMeasurementError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except SessionCompareError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except ApQualityWindowError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        print('{"status":"error","error":"comparison_failed"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
