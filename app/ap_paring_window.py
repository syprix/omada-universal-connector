"""Redacted summary of the saved AP bridge pairing-window result."""
from __future__ import annotations


class ApParingWindowError(ValueError):
    """The pairing-window result exceeds the projection bounds."""


_ROOT = frozenset({"status", "countdown", "clientAps"})
_DEVICE = frozenset({"mac", "status", "rssi", "model", "modelVersion"})
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MAX = 2**63 - 1
_MAX_CLIENT_APS = 256


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def summarize_ap_paring_window(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ApParingWindowError()
    unknown = sum(1 for key in raw if key not in _ROOT)
    invalid = missing = redacted = 0
    status = raw.get("status")
    if "status" not in raw:
        missing += 1
        status = None
    elif not _int32(status):
        invalid += 1
        status = None
    countdown = raw.get("countdown")
    if "countdown" not in raw:
        missing += 1
        countdown = None
    elif type(countdown) is not int or not 0 <= countdown <= _INT64_MAX:
        invalid += 1
        countdown = None

    status_counts: dict[int, int] = {}
    rssi_counts: dict[int, int] = {}
    rows = raw.get("clientAps")
    if "clientAps" not in raw:
        missing += 1
        count = None
    elif not isinstance(rows, list) or len(rows) > _MAX_CLIENT_APS:
        invalid += 1
        count = None
    else:
        count = len(rows)
        for row in rows:
            if not isinstance(row, dict) or len(row) > 16:
                invalid += 1
                continue
            unknown += sum(1 for key in row if key not in _DEVICE)
            for field in ("mac", "model", "modelVersion"):
                if field in row:
                    redacted += 1
                    if not isinstance(row[field], str) or len(row[field]) > 128:
                        invalid += 1
            for field, target in (("status", status_counts), ("rssi", rssi_counts)):
                if field not in row:
                    missing += 1
                elif _int32(row[field]):
                    target[row[field]] = target.get(row[field], 0) + 1
                else:
                    invalid += 1

    return {
        "status": "ok", "resource": "ap_paring_window",
        "window_status_code": status, "countdown_value": countdown,
        "client_ap_count": count,
        "client_status_counts": dict(sorted(status_counts.items())),
        "rssi_value_counts": dict(sorted(rssi_counts.items())),
        "redacted_identity_field_count": redacted,
        "redacted_field_count": redacted, "unknown_field_count": unknown,
        "invalid_field_count": invalid, "missing_field_count": missing,
        "partial": bool(missing or invalid or unknown),
    }
