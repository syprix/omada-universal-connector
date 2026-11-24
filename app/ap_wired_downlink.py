"""Bounded projection of documented AP wired-downlink telemetry."""
from __future__ import annotations

import math
import re
from typing import Any


class ApWiredDownlinkError(ValueError):
    """The wired-downlink response cannot be safely projected."""


_MAC = re.compile(r"(?:(?:[0-9A-Fa-f]{2}:){5}|(?:[0-9A-Fa-f]{2}-){5})[0-9A-Fa-f]{2}\Z")
_STRING = re.compile(r"[^\x00-\x1f\x7f]{0,128}\Z")
_INT32 = frozenset({"portType", "duplex", "link", "speed", "poeState", "voipState"})
_INT64 = frozenset({"rxPkts", "txPkts", "rx", "tx", "rxDropPkts", "txDropPkts",
                    "rxErrPkts", "txErrPkts"})
_NUMBERS = frozenset({"txPower", "rxPower", "temp", "voltage", "current"})
_STRINGS = frozenset({"port", "downLinkPort"})
_REDACTED = frozenset({"ip", "type", "deviceName", "model", "modelVersion"})
_FIELDS = _INT32 | _INT64 | _NUMBERS | _STRINGS | _REDACTED | {"mac", "display"}
_I32_MIN, _I32_MAX = -(2**31), 2**31 - 1
_I64_MIN, _I64_MAX = -(2**63), 2**63 - 1
_MAX_ROWS, _MAX_FIELDS = 256, 64


def _safe_text(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 128 and _STRING.fullmatch(value) is not None


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def project_ap_wired_downlink(raw: object,
                              device_refs_by_normalized_mac: dict[str, str | None]) -> dict[str, Any]:
    """Project rows and replace discovered MACs with site-local opaque refs.

    Identity fields and names are removed. Unknown/ambiguous MACs are not
    exposed; their rows can still carry safe port and counter data, marked
    partial so the caller does not infer a device association.
    """
    if not isinstance(raw, dict) or len(raw) > 16:
        raise ApWiredDownlinkError("response_invalid")
    collection_reported = "wiredDownlinkList" in raw
    partial = not collection_reported
    unknown = redacted = omitted = 0
    if set(raw) - {"wiredDownlinkList"}:
        unknown += sum(1 for key in raw if key != "wiredDownlinkList")
        partial = True
    rows = raw.get("wiredDownlinkList")
    if collection_reported and (not isinstance(rows, list) or len(rows) > _MAX_ROWS):
        raise ApWiredDownlinkError("response_invalid")
    if not collection_reported:
        rows = []

    items: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict) or len(row) > _MAX_FIELDS:
            raise ApWiredDownlinkError("response_invalid")
        item: dict[str, object] = {}
        source_mac = row.get("mac")
        if isinstance(source_mac, str) and _MAC.fullmatch(source_mac):
            normalized = re.sub(r"[:-]", "", source_mac).lower()
            ref = device_refs_by_normalized_mac.get(normalized)
            if ref is not None:
                item["device_ref"] = ref
            else:
                partial = True
        else:
            partial = True
        for field, value in row.items():
            if field not in _FIELDS:
                unknown += 1
                partial = True
            elif field in _REDACTED or field == "mac":
                redacted += 1
            elif field in _INT32:
                if type(value) is int and _I32_MIN <= value <= _I32_MAX:
                    item[field] = value
                else:
                    partial = True
            elif field in _INT64:
                if type(value) is int and _I64_MIN <= value <= _I64_MAX:
                    item[field] = value
                else:
                    partial = True
            elif field in _NUMBERS:
                if _finite_number(value):
                    item[field] = value
                else:
                    partial = True
            elif field in _STRINGS:
                if _safe_text(value):
                    item[field] = value
                else:
                    partial = True
            elif field == "display":
                if type(value) is bool:
                    item[field] = value
                else:
                    partial = True
        if item:
            items.append(item)
        else:
            omitted += 1
            partial = True
    return {"status": "ok", "resource": "ap_wired_downlink", "count": len(items),
            "source_count": len(rows) if collection_reported else None,
            "collection_reported": collection_reported,
            "missing_collection_count": int(not collection_reported),
            "items": items, "partial": partial,
            "omitted_count": omitted, "unknown_field_count": unknown,
            "redacted_field_count": redacted}
