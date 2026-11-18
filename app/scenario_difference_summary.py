"""Validation and projection for the controller scenario difference list."""
from __future__ import annotations


class ScenarioDifferenceError(ValueError):
    """The documented scenario-difference response is malformed."""


def summarize_scenario_differences(value: object, *, max_items: int = 100
                                   ) -> dict[str, object]:
    if not isinstance(value, list) or type(max_items) is not int or max_items <= 0:
        raise ScenarioDifferenceError("invalid scenario differences")
    items: list[dict[str, object]] = []
    invalid_count = 0
    for row in value[:max_items]:
        if not isinstance(row, dict):
            invalid_count += 1
            continue
        name = row.get("name")
        default = row.get("isDefault")
        if (not isinstance(name, str) or not 1 <= len(name) <= 128 or
                any(ord(char) < 0x21 or ord(char) > 0x7e for char in name) or
                type(default) is not bool):
            invalid_count += 1
            continue
        items.append({"name": name, "is_default": default})
    return {
        "status": "ok",
        "resource": "controller_scenario_differences",
        "scenario_count": len(value),
        "returned_count": len(items),
        "default_count": sum(item["is_default"] is True for item in items),
        "items": items,
        "partial": len(value) > max_items or invalid_count > 0,
    }
