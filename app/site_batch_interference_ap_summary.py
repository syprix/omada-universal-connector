"""Aggregate one batch interference scan's AP list without device identity."""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Callable


class SiteBatchInterferenceApSummaryError(ValueError):
    """The documented batch AP response is malformed."""


_FIELDS = frozenset(("scanApNum", "deviceInfoList"))
_DEVICE_FIELDS = frozenset((
    "name", "mac", "model", "modelVersion", "type", "time", "hasResult",
    "support2g", "support5g", "support6g", "supportWifiInterf",
    "supportNonWifiInterf", "supportChannelUtil", "supportReturnBandWidth",
    "actualChannel2g", "bandWidth2g", "actualChannel5g", "bandWidth5g",
    "actualChannel6g", "bandWidth6g",
))
_STRING_FIELDS = frozenset(("name", "mac", "model", "modelVersion", "type"))
_SUPPORT_FIELDS = (
    "support2g", "support5g", "support6g",
    "supportWifiInterf", "supportNonWifiInterf", "supportChannelUtil",
    "supportReturnBandWidth",
)
MAX_ROWS = 500
MAX_INT32 = 2_147_483_647
_MAC = re.compile(r"(?:(?:[0-9A-Fa-f]{2}:){5}|(?:[0-9A-Fa-f]{2}-){5})[0-9A-Fa-f]{2}")


def summarize_site_batch_interference_ap_list(
        value: object, *, device_ref_for: Callable[[str], str] | None = None
        ) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 8:
        raise SiteBatchInterferenceApSummaryError("result must be a bounded object")
    if device_ref_for is not None and not callable(device_ref_for):
        raise SiteBatchInterferenceApSummaryError("device reference mapper is invalid")
    unknown = sum(key not in _FIELDS for key in value)
    invalid = missing = 0

    reported = value.get("scanApNum")
    if reported is None:
        missing += 1
    elif type(reported) is not int or not 0 <= reported <= MAX_INT32:
        invalid += 1
        reported = None

    devices = value.get("deviceInfoList")
    if devices is None:
        missing += 1
        devices = []
    if not isinstance(devices, list):
        raise SiteBatchInterferenceApSummaryError("deviceInfoList must be a list")
    truncated = len(devices) > MAX_ROWS
    rows = devices[:MAX_ROWS]
    support_counts = {field: {"true": 0, "false": 0, "unreported": 0}
                      for field in _SUPPORT_FIELDS}
    result_counts = {"true": 0, "false": 0, "unreported": 0}
    row_unknown = 0
    valid = 0
    device_refs: list[str] = []
    seen_macs: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid += 1
            for counts in support_counts.values():
                counts["unreported"] += 1
            continue
        valid += 1
        row_unknown += sum(key not in _DEVICE_FIELDS for key in row)
        for key in _STRING_FIELDS:
            if key in row and not isinstance(row[key], str):
                invalid += 1
        mac = row.get("mac")
        if device_ref_for is not None and isinstance(mac, str) and _MAC.fullmatch(mac):
            normalized_mac = mac.casefold().replace("-", ":")
            if normalized_mac not in seen_macs:
                ref = device_ref_for(mac)
                if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{24}", ref):
                    raise SiteBatchInterferenceApSummaryError("device reference is invalid")
                device_refs.append(ref)
                seen_macs.add(normalized_mac)
        for field, counts in support_counts.items():
            flag = row.get(field)
            if flag is True:
                counts["true"] += 1
            elif flag is False:
                counts["false"] += 1
            elif field in row:
                invalid += 1
                counts["unreported"] += 1
            else:
                counts["unreported"] += 1
        has_result = row.get("hasResult")
        if has_result is True:
            result_counts["true"] += 1
        elif has_result is False:
            result_counts["false"] += 1
        elif "hasResult" in row:
            invalid += 1
            result_counts["unreported"] += 1
        else:
            result_counts["unreported"] += 1

    return {
        "data": {
            "reported_scan_ap_count": reported,
            "returned_device_count": len(devices),
            "valid_device_count": valid,
            "result_counts": result_counts,
            "support_counts": support_counts,
            "truncated": truncated,
            "device_refs": device_refs,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown + row_unknown,
        "partial": bool(missing or invalid or unknown or row_unknown or truncated),
    }
