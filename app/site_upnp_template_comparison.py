"""Compare common redacted UPnP setting fields for an explicitly selected site/template."""
from __future__ import annotations


_FIELDS = (
    "enabled", "wan_port_count", "network_count", "supports_ds_lite_or_map_e",
)


def compare_site_and_template_upnp(
        site_summary: dict[str, object], template_summary: dict[str, object]) -> dict[str, object]:
    site_data = site_summary.get("data")
    template_data = template_summary.get("data")
    if not isinstance(site_data, dict) or not isinstance(template_data, dict):
        raise ValueError("comparison_data_invalid")
    by_field: dict[str, str] = {}
    for field in _FIELDS:
        left, right = site_data.get(field), template_data.get(field)
        if left is None or right is None:
            by_field[field] = "unknown"
        elif left == right:
            by_field[field] = "same"
        else:
            by_field[field] = "different"
    return {
        "status": "ok", "resource": "site_upnp_template_comparison",
        "compared_fields": list(_FIELDS), "by_field": by_field,
        "same_count": sum(value == "same" for value in by_field.values()),
        "different_count": sum(value == "different" for value in by_field.values()),
        "unknown_count": sum(value == "unknown" for value in by_field.values()),
        "partial": bool(by_field and any(value == "unknown" for value in by_field.values())
                        or site_summary.get("partial") or template_summary.get("partial")),
        "selection": "compares only the caller-selected site and template; assignment is not inferred",
        "source_coverage": "template UPnP GET is documented in CBC Standard 6.3.0; not present in the Hardware Controller or ER7212PC exports",
    }
