"""Redacted client signal-strength category counts."""
from __future__ import annotations

from typing import Any


class SiteClientRssiDistributionError(ValueError):
    """Raised when the documented RSSI response is outside its bounds."""


_BUCKETS = {
    "lessThan72": "less_than_72",
    "from71To65": "from_71_to_65",
    "from65To55": "from_65_to_55",
    "from55To45": "from_55_to_45",
    "moreThan45": "more_than_45",
}
_BANDS = {
    "distribution2G": "band_2_4_ghz",
    "distribution5G": "band_5_ghz",
    "distribution6G": "band_6_ghz",
}


def _project_counts(value: Any) -> tuple[dict[str, int], int, int, int]:
    if not isinstance(value, dict) or len(value) > 8:
        raise SiteClientRssiDistributionError("distribution_invalid")
    data: dict[str, int] = {}
    missing = 0
    invalid = 0
    for field, name in _BUCKETS.items():
        if field not in value:
            missing += 1
            continue
        count = value[field]
        if type(count) is int and 0 <= count <= 2**31 - 1:
            data[name] = count
        else:
            invalid += 1
    unknown = len(set(value) - set(_BUCKETS))
    return data, missing, invalid, unknown


def project_site_client_rssi_distribution(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 12:
        raise SiteClientRssiDistributionError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = unknown = 0
    for field, name in _BUCKETS.items():
        if field not in result:
            missing += 1
            continue
        count = result[field]
        if type(count) is int and 0 <= count <= 2**31 - 1:
            data[name] = count
        else:
            invalid += 1
    unknown += len(set(result) - set(_BUCKETS) - set(_BANDS))
    for field, name in _BANDS.items():
        if field not in result:
            missing += len(_BUCKETS)
            continue
        counts, absent, malformed, extras = _project_counts(result[field])
        data[name] = counts
        missing += absent
        invalid += malformed
        unknown += extras
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
