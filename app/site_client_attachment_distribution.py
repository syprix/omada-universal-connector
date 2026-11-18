"""Aggregate client totals by access-point and switch attachment."""
from __future__ import annotations

import math
from typing import Any


class SiteClientAttachmentDistributionError(ValueError):
    """Raised when the documented client distribution response is malformed."""


_MAX_COUNT = 2**31 - 1


def _total(value: Any, field: str, rows_field: str,
           distribution_field: str) -> tuple[int | None, int, int, int]:
    if not isinstance(value, dict) or len(value) > 16:
        raise SiteClientAttachmentDistributionError("distribution_invalid")
    count = value.get(field)
    invalid = int(field in value and (type(count) is not int or not 0 <= count <= _MAX_COUNT))
    missing = int(field not in value)
    unknown = len(set(value) - {field, rows_field, "others", distribution_field})
    if rows_field in value:
        rows = value[rows_field]
        if not isinstance(rows, list) or len(rows) > 1_000 or any(
                not isinstance(row, dict) for row in rows):
            invalid += 1
    if "others" in value and not isinstance(value["others"], dict):
        invalid += 1
    if distribution_field in value:
        distribution = value[distribution_field]
        try:
            finite = type(distribution) in (int, float) and math.isfinite(distribution)
        except (OverflowError, TypeError):
            finite = False
        if not finite:
            invalid += 1
    return (count if not invalid and not missing else None), missing, invalid, unknown


def project_site_client_attachment_distribution(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteClientAttachmentDistributionError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = unknown = 0
    fields = {
        "eapDistribution": ("access_point_attached_client_count", "totalEapClients",
                            "eaps", "totalEapDistribution"),
        "switchDistribution": ("switch_attached_client_count", "totalSwitchClients",
                               "switches", "totalSwitchDistribution"),
    }
    unknown = len(set(result) - set(fields))
    for field, (output, count_field, rows_field, distribution_field) in fields.items():
        if field not in result:
            missing += 1
            continue
        count, absent, malformed, extras = _total(
            result[field], count_field, rows_field, distribution_field)
        missing += absent
        invalid += malformed
        unknown += extras
        if count is not None:
            data[output] = count
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
