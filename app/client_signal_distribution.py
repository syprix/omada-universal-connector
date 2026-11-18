"""Privacy-preserving projection of documented client signal distribution."""
from __future__ import annotations


class ClientSignalDistributionError(ValueError):
    """Input exceeds safe bounds or is not a result object."""

    def __init__(self, code: str = "client_signal_distribution_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_CATEGORIES = ("poorSignal", "weakSignal", "averageSignal", "stableSignal", "strongSignal")
_FIELDS = ("totalClients", "clientsPercent", "clients2g", "clients5g", "clients6g")
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_CATEGORY_FIELDS = 16
_MAX_RESULT_FIELDS = 16


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def project_client_signal_distribution(raw: object) -> dict[str, object]:
    """Project the five documented categories and optional int32 metrics.

    ``clientsPercent`` is retained as the raw documented integer. No percentage
    scale, signal threshold, or category interpretation is inferred. Unknown
    field names and values are omitted; malformed or incomplete projections
    are marked partial.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_RESULT_FIELDS:
        raise ClientSignalDistributionError()

    data: dict[str, dict[str, int]] = {}
    missing: list[str] = []
    invalid: list[str] = []
    unknown_field_count = 0
    omitted_field_count = 0

    for category in _CATEGORIES:
        if category not in raw:
            missing.append(category)
            omitted_field_count += 1
            continue
        source = raw[category]
        if not isinstance(source, dict):
            invalid.append(category)
            omitted_field_count += 1
            continue
        if len(source) > _MAX_CATEGORY_FIELDS:
            raise ClientSignalDistributionError()

        projected: dict[str, int] = {}
        for field in _FIELDS:
            if field not in source:
                missing.append(f"{category}.{field}")
                omitted_field_count += 1
                continue
            value = source[field]
            if _int32(value):
                projected[field] = value
            else:
                invalid.append(f"{category}.{field}")
                omitted_field_count += 1

        extras = sum(1 for key in source if key not in _FIELDS)
        if extras:
            unknown_field_count += extras
            omitted_field_count += extras
        data[category] = projected

    extras = sum(1 for key in raw if key not in _CATEGORIES)
    if extras:
        unknown_field_count += extras
        omitted_field_count += extras

    return {
        "status": "ok",
        "resource": "client_signal_distribution",
        "data": data,
        "partial": bool(missing or invalid or unknown_field_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_field_count,
        "omitted_field_count": omitted_field_count,
    }
