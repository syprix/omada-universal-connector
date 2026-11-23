"""Redacted controller-wide summary of documented SD-WAN group rows."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SdWanGroupSummaryError(ValueError):
    """The controller response is outside the bounded documented contract."""


_FIELDS = {
    "hubDeviceType": "hub_device_type",
    "hubModel": "hub_model",
    "hubModelVersion": "hub_model_version",
}
_KNOWN = {"id", "name", "hubDeviceType", "hubModel", "hubModelVersion", "deviceNum"}


def summarize_sdwan_group_rows(rows: object, omitted_rows: int = 0) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > 1000 or
            type(omitted_rows) is not int or omitted_rows < 0):
        raise SdWanGroupSummaryError("input_invalid")

    field_coverage = {
        name: {"reported": 0, "unreported": 0}
        for name in (*_FIELDS.values(), "device_count")
    }
    valid_device_counts = invalid_rows = unknown_fields = 0
    device_membership_sum = 0
    partial = omitted_rows > 0
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            for coverage in field_coverage.values():
                coverage["unreported"] += 1
            partial = True
            continue
        unknown_fields += sum(1 for key in row if key not in _KNOWN)
        for source, target in _FIELDS.items():
            value = row.get(source)
            if isinstance(value, str) and 0 < len(value) <= 256:
                field_coverage[target]["reported"] += 1
            else:
                field_coverage[target]["unreported"] += 1
                partial = True
        count = row.get("deviceNum")
        if type(count) is int and 0 <= count <= 2**31 - 1:
            valid_device_counts += 1
            device_membership_sum += count
            field_coverage["device_count"]["reported"] += 1
        else:
            field_coverage["device_count"]["unreported"] += 1
            partial = True

    if invalid_rows or unknown_fields:
        partial = True
    return {
        "status": "partial" if partial else "ok",
        "resource": "controller_sdwan_group_summary",
        "returned_group_count": len(rows),
        "omitted_group_count": omitted_rows,
        "reported_group_total": len(rows) + omitted_rows,
        "field_coverage": field_coverage,
        "reported_group_device_membership_sum": device_membership_sum,
        "device_count_unreported_groups": len(rows) - valid_device_counts,
        "invalid_rows": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
    }
