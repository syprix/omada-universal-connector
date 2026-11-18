"""Bounded redacted projection for the documented AP uplink configuration GET."""
from __future__ import annotations

import re
from typing import Any


class ApUplinkConfigError(ValueError):
    """The response is not a bounded array of uplink configuration rows."""

    def __init__(self, code: str = "ap_uplink_config_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_PORT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}\Z")
_MAX_ROWS = 64


def project_ap_uplink_config(raw: object) -> dict[str, object]:
    """Project only ``auto`` and a bounded port identifier from result rows."""
    if not isinstance(raw, list) or len(raw) > _MAX_ROWS:
        raise ApUplinkConfigError()
    items: list[dict[str, object]] = []
    missing_count = invalid_count = unknown_count = 0
    for row in raw:
        if not isinstance(row, dict) or len(row) > 16:
            raise ApUplinkConfigError()
        item: dict[str, object] = {}
        if "auto" not in row:
            missing_count += 1
        elif type(row["auto"]) is bool:
            item["auto"] = row["auto"]
        else:
            invalid_count += 1
        if "port" in row:
            value = row["port"]
            if isinstance(value, str) and _PORT.fullmatch(value):
                item["port"] = value
            else:
                invalid_count += 1
        unknown_count += sum(1 for key in row if key not in {"auto", "port"})
        items.append(item)
    return {
        "status": "ok",
        "resource": "ap_uplink_config",
        "count": len(items),
        "items": items,
        "partial": bool(missing_count or invalid_count or unknown_count),
        "missing_field_count": missing_count,
        "invalid_field_count": invalid_count,
        "unknown_field_count": unknown_count,
    }
