"""Bounded projection for documented WLAN optimization history."""
from __future__ import annotations


class ExperienceIndexError(ValueError):
    """The upstream response does not match the documented shape."""

    def __init__(self, code: str = "experience_index_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 16
_MAX_ROWS = 100
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1
_INT32_MAX = 2**31 - 1
_FIELDS = {
    "beforeIndex": "before_index",
    "afterIndex": "after_index",
    "apNum": "ap_count",
    "length": "duration_seconds",
    "mode": "mode",
}


def project_experience_index(raw: object) -> dict[str, object]:
    """Keep documented optimization timestamps, indices and run metadata."""
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ExperienceIndexError()
    if any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH for key in raw):
        raise ExperienceIndexError()

    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    rows: list[dict[str, object]] = []
    if "lastScan" not in raw:
        missing.append("lastScan")
        omitted_count += 1
    elif not isinstance(raw["lastScan"], list):
        omitted.add("lastScan")
        omitted_count += 1
    else:
        scans = raw["lastScan"]
        if len(scans) > _MAX_ROWS:
            raise ExperienceIndexError()
        for index, scan in enumerate(scans):
            if not isinstance(scan, dict) or len(scan) > _MAX_FIELDS:
                omitted.add("invalid_rows")
                omitted_count += 1
                continue
            if any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH for key in scan):
                raise ExperienceIndexError()

            row: dict[str, object] = {}
            for source, target in (("time", "time_ms"), *tuple(_FIELDS.items()),
                                   ("isAppliedSuccess", "applied_success")):
                if source not in scan:
                    missing.append(f"lastScan[{index}].{source}")
                    omitted_count += 1
                    continue
                value = scan[source]
                if source == "time":
                    valid = type(value) is int and 0 <= value <= _INT64_MAX
                elif source in {"beforeIndex", "afterIndex"}:
                    valid = type(value) is int and 0 <= value <= 100
                elif source == "isAppliedSuccess":
                    valid = type(value) is bool
                elif source == "mode":
                    valid = type(value) is int and value in (0, 1)
                else:
                    valid = type(value) is int and 0 <= value <= _INT32_MAX
                if valid:
                    row[target] = value
                else:
                    omitted.add(f"invalid_{target}")
                    omitted_count += 1
            extras = sum(1 for key in scan if key not in {"time", *_FIELDS, "isAppliedSuccess"})
            if extras:
                omitted.add("unknown_fields")
                omitted_count += extras
            rows.append(row)

    extras = sum(1 for key in raw if key != "lastScan")
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras
    return {
        "status": "ok",
        "resource": "experience_index",
        "data": {"last_scan": rows},
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }
