"""Identity-free counts for AP signal-strength bands."""
from __future__ import annotations

from typing import Any


class SiteApRssiDensityError(ValueError):
    """Raised when the documented AP density response exceeds bounds."""


_BUCKETS = {
    "lessThan90": "less_than_90",
    "from90To85": "from_90_to_85",
    "from85To80": "from_85_to_80",
    "from80To75": "from_80_to_75",
    "from75To70": "from_75_to_70",
    "from70To65": "from_70_to_65",
    "from65To60": "from_65_to_60",
    "from60To55": "from_60_to_55",
    "from55To50": "from_55_to_50",
    "from50To45": "from_50_to_45",
    "from45To40": "from_45_to_40",
    "from40To35": "from_40_to_35",
    "from35To30": "from_35_to_30",
    "moreThan30": "more_than_30",
}


def project_site_ap_rssi_density(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 18:
        raise SiteApRssiDensityError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = 0
    known = set(_BUCKETS) | {"existAp", "existApClient"}
    unknown = len(set(result) - known)
    if "existAp" not in result:
        missing += 1
    elif type(result["existAp"]) is bool:
        data["access_points_present"] = result["existAp"]
    else:
        invalid += 1
    if "existApClient" not in result:
        missing += 1
    elif type(result["existApClient"]) is bool:
        data["access_point_client_data_present"] = result["existApClient"]
    else:
        invalid += 1
    counts: dict[str, int] = {}
    for field, name in _BUCKETS.items():
        if field not in result:
            missing += 1
            continue
        rows = result[field]
        if not isinstance(rows, list) or len(rows) > 1_000 or any(
                not isinstance(row, dict) for row in rows):
            invalid += 1
            continue
        counts[name] = len(rows)
    data["ap_count_by_signal_bucket"] = counts
    data["ap_count_in_buckets"] = sum(counts.values())
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
