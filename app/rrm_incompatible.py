"""Privacy-preserving projection of documented RRM-incompatible AP rows.

The caller supplies an inventory resolver which receives a normalized AP MAC
and returns that AP's existing site-bound opaque ``device_ref`` or ``None``.
Raw identifiers and descriptive device fields are never returned.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


class RrmIncompatibleProjectionError(ValueError):
    """A page exceeds bounds or cannot be safely traversed."""

    def __init__(self, code: str = "rrm_incompatible_response_invalid") -> None:
        super().__init__(code)
        self.code = code


MAX_ENTRIES = 4000  # OpenApiConfig maximum: page_size 200 * max_pages 20.
MAX_ROW_FIELDS = 32
_MAC = re.compile(r"(?:(?:[0-9A-Fa-f]{2}:){5}|(?:[0-9A-Fa-f]{2}-){5})[0-9A-Fa-f]{2}\Z")
_REF = re.compile(r"[0-9a-f]{24}\Z")
_INT32_MIN, _INT32_MAX = -(2**31), 2**31 - 1
_DOCUMENTED_FIELDS = frozenset({
    "name", "mac", "statusCategory", "status", "version", "type",
    "model", "modelVersion", "showModel",
})
_CATEGORY_VALUES = frozenset({0, 1, 2, 3, 4})


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def project_rrm_incompatible_rows(
    rows: Any,
    ap_ref_for_normalized_mac: Callable[[str], str | None],
    *,
    max_entries: int = MAX_ENTRIES,
) -> dict[str, object]:
    """Project bounded API rows to opaquely identified status scalars.

    ``rows`` is the complete collection gathered from the endpoint's pages.
    It is never truncated: a collection beyond ``max_entries`` fails closed.
    The documented ``status`` field has no documented enum, so it is exposed
    only as a bounded int32 ``status_code`` and is not semantically decoded.
    Missing or invalid statuses become ``None`` and mark the row partial.
    Rows with missing, malformed, unknown, or ambiguous inventory MACs are
    omitted and counted as unknown; the callback must return an existing
    lowercase 24-hex site-bound AP reference, never create one from this row.
    """
    if (not isinstance(rows, list) or type(max_entries) is not int
            or not 1 <= max_entries <= MAX_ENTRIES
            or not callable(ap_ref_for_normalized_mac)):
        raise RrmIncompatibleProjectionError()
    if len(rows) > max_entries:
        raise RrmIncompatibleProjectionError("rrm_incompatible_response_too_large")

    items: list[dict[str, object]] = []
    unknown_entry_count = 0
    unknown_field_count = 0
    partial = False

    for row in rows:
        if not isinstance(row, dict) or len(row) > MAX_ROW_FIELDS:
            unknown_entry_count += 1
            partial = True
            continue

        unknown_field_count += sum(1 for key in row if key not in _DOCUMENTED_FIELDS)
        if any(key not in _DOCUMENTED_FIELDS for key in row):
            partial = True

        raw_mac = row.get("mac")
        if not isinstance(raw_mac, str) or not _MAC.fullmatch(raw_mac):
            unknown_entry_count += 1
            partial = True
            continue
        normalized_mac = raw_mac.replace(":", "").replace("-", "").lower()
        try:
            device_ref = ap_ref_for_normalized_mac(normalized_mac)
        except Exception:
            # A failed lookup must not turn the row's raw identity into output
            # or a new reference.
            device_ref = None
        if not isinstance(device_ref, str) or not _REF.fullmatch(device_ref):
            unknown_entry_count += 1
            partial = True
            continue

        raw_category = row.get("statusCategory")
        category = raw_category if type(raw_category) is int and raw_category in _CATEGORY_VALUES else None
        raw_status = row.get("status")
        status_code = raw_status if _int32(raw_status) else None
        row_partial = category is None or status_code is None
        if row_partial:
            partial = True
        items.append({
            "device_ref": device_ref,
            "status_category": category,
            "status_code": status_code,
            "partial": row_partial,
        })

    return {
        "status": "ok",
        "resource": "rrm_incompatible_aps",
        "count": len(items),
        "items": items,
        "unknown_entry_count": unknown_entry_count,
        "unknown_field_count": unknown_field_count,
        "partial": partial,
    }
