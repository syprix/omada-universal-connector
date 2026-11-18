"""Redacted projection of APs omitted from RF planning."""
from __future__ import annotations

import re


class RfExcludedApsError(ValueError):
    """The excluded AP response exceeds safe bounds."""


_MAX_ROWS = 256
_MAX_FIELDS = 24
_REDACTED = {"name", "ip", "mac", "model", "modelVersion", "showModel", "type"}


def project_rf_excluded_aps(raw: object, ap_refs_by_mac: dict[str, list[str]]) -> dict[str, object]:
    """Return only site-bound opaque AP references and documented enum flags."""
    if not isinstance(raw, list) or len(raw) > _MAX_ROWS:
        raise RfExcludedApsError()
    if not isinstance(ap_refs_by_mac, dict):
        raise RfExcludedApsError()
    items: list[dict[str, object]] = []
    omitted_count = 0
    redacted_count = 0
    for row in raw:
        if not isinstance(row, dict) or len(row) > _MAX_FIELDS:
            raise RfExcludedApsError()
        item: dict[str, object] = {}
        mac = row.get("mac")
        if not isinstance(mac, str) or not re.fullmatch(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", mac):
            omitted_count += 1
            continue
        refs = ap_refs_by_mac.get(re.sub(r"[:-]", "", mac).lower(), [])
        if len(refs) != 1 or not re.fullmatch(r"[0-9a-f]{24}", refs[0]):
            omitted_count += 1
            continue
        item["ap_ref"] = refs[0]
        redacted_count += sum(1 for key in row if key in _REDACTED)
        for source, target, allowed in (
            ("unsupportType", "unsupported_reason", {0, 1, 2}),
            ("statusCategory", "status_category", {0, 1, 2, 3, 4}),
        ):
            if source not in row:
                continue
            value = row[source]
            if type(value) is int and value in allowed:
                item[target] = value
            else:
                omitted_count += 1
        if "addedInAdvanced" in row:
            value = row["addedInAdvanced"]
            if type(value) is bool:
                item["added_in_advanced"] = value
            else:
                omitted_count += 1
        known = _REDACTED | {"unsupportType", "statusCategory", "addedInAdvanced"}
        omitted_count += sum(1 for key in row if key not in known)
        items.append(item)
    return {
        "status": "ok",
        "resource": "rf_excluded_aps",
        "count": len(items),
        "items": items,
        "partial": omitted_count > 0,
        "omitted_field_count": omitted_count,
        "redacted_field_count": redacted_count,
    }
