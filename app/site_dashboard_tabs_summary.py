"""Identity-free counts for the documented dashboard tab lists."""
from __future__ import annotations

from typing import Any


class SiteDashboardTabsSummaryError(ValueError):
    """Raised when the tab response exceeds its source bounds."""


_ROW_FIELDS = {"id", "name", "type", "cards"}
_MAX_TABS = 100
_MAX_CARDS_PER_TAB = 1_000
_INT32_MAX = (1 << 31) - 1


def project_site_dashboard_tabs_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_TABS:
        raise SiteDashboardTabsSummaryError("tabs_invalid")
    missing = invalid = unknown = total_cards = 0
    type_counts: dict[str, int] = {}
    for row in result:
        if not isinstance(row, dict) or len(row) > 8:
            invalid += 1
            continue
        unknown += len(set(row) - _ROW_FIELDS)
        if not isinstance(row.get("id"), str):
            missing += int("id" not in row)
            invalid += int("id" in row)
        if not isinstance(row.get("name"), str):
            missing += int("name" not in row)
            invalid += int("name" in row)
        kind = row.get("type")
        if type(kind) is int and 0 <= kind <= _INT32_MAX:
            key = str(kind)
            type_counts[key] = type_counts.get(key, 0) + 1
        else:
            missing += int("type" not in row)
            invalid += int("type" in row)
        cards = row.get("cards")
        if not isinstance(cards, list) or len(cards) > _MAX_CARDS_PER_TAB:
            invalid += 1
            continue
        for card in cards:
            if type(card) is int and 0 <= card <= _INT32_MAX:
                total_cards += 1
            else:
                invalid += 1
    data = {"tab_count": len(result), "card_count": total_cards,
            "tab_type_counts": type_counts}
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
