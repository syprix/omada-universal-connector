"""Summarize one selected AP group's documented capacity fields."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_BANDS = (("0", "2g"), ("1", "5g"), ("2", "6g"))


def summarize_ap_group_info(result: object) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("input_invalid")
    primary = result.get("primary")
    if type(primary) is not bool:
        primary = None

    ap_count = result.get("apNum")
    if type(ap_count) is not int or not 0 <= ap_count <= 2**63 - 1:
        ap_count = None

    raw = result.get("remainingBinding")
    bindings: dict[str, int | None] = {}
    invalid = not isinstance(raw, Mapping)
    if isinstance(raw, Mapping):
        invalid = len(raw) > 8 or any(key not in {code for code, _ in _BANDS} for key in raw)
        for code, band in _BANDS:
            value = raw.get(code)
            if type(value) is int and 0 <= value <= 2**31 - 1:
                bindings[band] = value
            else:
                bindings[band] = None
                invalid = invalid or code in raw
    else:
        bindings = {band: None for _, band in _BANDS}

    known_bands = sum(value is not None for value in bindings.values())
    partial = primary is None or ap_count is None or known_bands != len(_BANDS) or invalid
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_ap_group_info_summary",
        "primary": primary,
        "ap_count": ap_count,
        "remaining_ssid_bindings": bindings,
        "partial": partial,
    }
