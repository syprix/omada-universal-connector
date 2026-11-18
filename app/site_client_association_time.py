"""Bounded, identity-free summary of client association setup times."""
from __future__ import annotations

from typing import Any


class SiteClientAssociationTimeError(ValueError):
    """Raised when association-time data is outside its documented bounds."""


_FIELDS = ("lessThan2sNum", "from2To4sNum", "from4To6sNum", "from6To8sNum",
           "from8To10sNum", "moreThan10sNum", "fails", "lessThan10sPercent")
_OUTPUTS = {
    "lessThan2sNum": "under_2_seconds_count",
    "from2To4sNum": "from_2_to_4_seconds_count",
    "from4To6sNum": "from_4_to_6_seconds_count",
    "from6To8sNum": "from_6_to_8_seconds_count",
    "from8To10sNum": "from_8_to_10_seconds_count",
    "moreThan10sNum": "over_10_seconds_count",
    "fails": "failed_association_count",
    "lessThan10sPercent": "under_10_seconds_percent",
}


def project_site_client_association_time(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 12:
        raise SiteClientAssociationTimeError("response_invalid")
    missing = len(set(_FIELDS) - result.keys())
    invalid = 0
    unknown = len(set(result) - set(_FIELDS))
    data: dict[str, object] = {}
    for field, output in _OUTPUTS.items():
        if field not in result:
            continue
        value = result[field]
        upper = 100 if field == "lessThan10sPercent" else 2 ** 31 - 1
        if type(value) is int and 0 <= value <= upper:
            data[output] = value
        else:
            invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
