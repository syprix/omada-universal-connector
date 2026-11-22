"""Redacted counts for WAN QoS configuration and exact port associations."""
from __future__ import annotations

from collections import Counter
from typing import Any


class SiteWanQosSummaryError(ValueError):
    pass


MAX_ROWS = 10_000
_DIRECTIONS = {0: "inbound", 1: "outbound", 2: "both"}


def summarize_site_wan_qos(wans: list[Any], rules: list[Any]) -> dict[str, object]:
    if len(wans) > MAX_ROWS or len(rules) > MAX_ROWS:
        raise SiteWanQosSummaryError("row_limit")
    configured: Counter[str] = Counter()
    invalid = unknown_fields = invalid_wans = invalid_rules = 0
    wan_id_counts: Counter[str] = Counter()
    wan_configuration_by_id: dict[str, str] = {}
    for row in wans:
        if not isinstance(row, dict) or set(row) - {"id", "name", "configured"}:
            invalid_wans += 1
            if isinstance(row, dict):
                unknown_fields += len(set(row) - {"id", "name", "configured"})
            continue
        ident, enabled = row.get("id"), row.get("configured")
        if not isinstance(ident, str) or not 1 <= len(ident) <= 256:
            invalid_wans += 1
            continue
        configured_key = str(enabled).lower() if isinstance(enabled, bool) else "unknown"
        wan_id_counts[ident] += 1
        wan_configuration_by_id[ident] = configured_key
        configured[configured_key] += 1
        if "name" in row and (not isinstance(row["name"], str) or len(row["name"]) > 256):
            invalid_wans += 1
    counts_by_config: dict[str, Counter[str]] = {
        "true": Counter(), "false": Counter(), "unknown": Counter(), "unmatched": Counter()}
    unique_ids = {ident for ident, count in wan_id_counts.items() if count == 1}
    status_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    matched_rules = unmatched_rules = 0
    allowed = {"id", "wan", "status", "udpBandwidthCtrl", "udpRatio", "outPrioritization",
               "direction", "inBandwidth", "outBandwidth", "classRatio"}
    for rule in rules:
        if not isinstance(rule, dict) or len(rule) > len(allowed):
            invalid_rules += 1
            continue
        unknown_fields += len(set(rule) - allowed)
        status = rule.get("status")
        status_key = str(status).lower() if isinstance(status, bool) else "unknown"
        status_counts[status_key] += 1
        direction = rule.get("direction")
        direction_key = (_DIRECTIONS.get(direction) if isinstance(direction, int)
                         and not isinstance(direction, bool) else None)
        direction_counts[direction_key or "unknown"] += 1
        port_ref = rule.get("wan")
        if isinstance(port_ref, str) and port_ref in unique_ids:
            matched_rules += 1
            configured_key = wan_configuration_by_id[port_ref]
            counts_by_config[configured_key][status_key] += 1
        else:
            unmatched_rules += 1
            counts_by_config["unmatched"][status_key] += 1
        if not isinstance(status, bool):
            invalid_rules += 1
        if direction_key is None:
            invalid_rules += 1
    invalid = invalid_wans + invalid_rules
    return {
        "status": "ok", "resource": "site_wan_qos_summary",
        "wan_count": len(wans), "by_configured": dict(sorted(configured.items())),
        "rule_count": len(rules), "rules_by_enabled_status": dict(sorted(status_counts.items())),
        "rules_by_direction": dict(sorted(direction_counts.items())),
        "rules_by_exact_wan_match_and_configuration": {
            key: dict(sorted(value.items())) for key, value in counts_by_config.items()},
        "rules_with_exact_wan_match": matched_rules,
        "rules_without_unique_wan_match": unmatched_rules,
        "invalid_wan_rows": invalid_wans, "invalid_rule_fields_or_values": invalid_rules,
        "unknown_field_count": unknown_fields,
        "bandwidth_units": "not specified in the three API exports; bandwidth values omitted",
        "partial": bool(invalid or unknown_fields or unmatched_rules or configured["unknown"]),
        "traffic_state": "configuration only; does not indicate measured WAN traffic",
    }
