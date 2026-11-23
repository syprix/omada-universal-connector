"""Redacted summary of site bandwidth-control policies."""
from __future__ import annotations

from collections.abc import Mapping


class SiteBandwidthRulesSummaryError(ValueError):
    pass


def summarize_site_bandwidth_rules(rows: object, total: object,
                                   pages_fetched: int, page_limit: int) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or type(total) is not int or
            total < len(rows) or not 0 <= total < (1 << 63) or
            type(pages_fetched) is not int or not 0 <= pages_fetched <= 10 or
            type(page_limit) is not int or not 1 <= page_limit <= 10):
        raise SiteBandwidthRulesSummaryError("input_invalid")
    active = {"enabled": 0, "disabled": 0, "unknown": 0}
    sources = {"network": 0, "ip_group": 0, "unknown": 0}
    modes = {"shared": 0, "individual": 0, "unknown": 0}
    units = {direction: {"kbps": 0, "mbps": 0, "unknown": 0}
             for direction in ("upstream", "downstream")}
    bandwidth = {direction: {"present": 0, "missing": 0}
                 for direction in ("upstream", "downstream")}
    field_presence = {key: {"present": 0, "missing": 0} for key in (
        "status", "source_type", "mode", "upstream_bandwidth", "downstream_bandwidth")}
    partial = len(rows) < total
    known = {"id", "name", "index", "status", "sourceType", "sourceIds", "wanPortIds",
             "upstreamBandwidth", "upstreamBandwidthUnit", "downstreamBandwidth",
             "downstreamBandwidthUnit", "mode"}
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 16:
            raise SiteBandwidthRulesSummaryError("row_invalid")
        if set(row) - known:
            partial = True
        for key in ("id", "name"):
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 512):
                raise SiteBandwidthRulesSummaryError("field_invalid")
        partial |= "name" not in row
        if "index" in row and (type(row["index"]) is not int or
                                not -(1 << 31) <= row["index"] < (1 << 31)):
            raise SiteBandwidthRulesSummaryError("field_invalid")
        for key in ("sourceIds", "wanPortIds"):
            value = row.get(key)
            partial |= key not in row
            if value is not None and (not isinstance(value, list) or len(value) > 20_000 or
                                      any(not isinstance(item, str) or len(item) > 512
                                          for item in value)):
                raise SiteBandwidthRulesSummaryError("field_invalid")

        status = row.get("status")
        if status is None:
            field_presence["status"]["missing"] += 1
            active["unknown"] += 1
            partial = True
        elif type(status) is not bool:
            raise SiteBandwidthRulesSummaryError("field_invalid")
        else:
            field_presence["status"]["present"] += 1
            active["enabled" if status else "disabled"] += 1

        source_type = row.get("sourceType")
        if source_type is None:
            field_presence["source_type"]["missing"] += 1
            sources["unknown"] += 1
            partial = True
        elif type(source_type) is not int:
            raise SiteBandwidthRulesSummaryError("field_invalid")
        else:
            field_presence["source_type"]["present"] += 1
            sources[{0: "network", 1: "ip_group"}.get(source_type, "unknown")] += 1
            partial |= source_type not in (0, 1)

        mode = row.get("mode")
        if mode is None:
            field_presence["mode"]["missing"] += 1
            modes["unknown"] += 1
            partial = True
        elif type(mode) is not int:
            raise SiteBandwidthRulesSummaryError("field_invalid")
        else:
            field_presence["mode"]["present"] += 1
            modes[{0: "shared", 1: "individual"}.get(mode, "unknown")] += 1
            partial |= mode not in (0, 1)

        for direction in ("upstream", "downstream"):
            value_key = direction + "Bandwidth"
            unit_key = direction + "BandwidthUnit"
            value = row.get(value_key)
            if value is None:
                field_presence[value_key.replace("Bandwidth", "_bandwidth").lower()]["missing"] += 1
                bandwidth[direction]["missing"] += 1
                partial = True
            elif type(value) is not int or not 1 <= value <= 9_999_999:
                raise SiteBandwidthRulesSummaryError("field_invalid")
            else:
                field_presence[value_key.replace("Bandwidth", "_bandwidth").lower()]["present"] += 1
                bandwidth[direction]["present"] += 1
            unit = row.get(unit_key)
            if unit is None:
                units[direction]["unknown"] += 1
                partial = True
            elif type(unit) is not int:
                raise SiteBandwidthRulesSummaryError("field_invalid")
            else:
                units[direction][{1: "kbps", 2: "mbps"}.get(unit, "unknown")] += 1
                partial |= unit not in (1, 2)
    return {
        "rule_count": len(rows), "total_count": total,
        "coverage_complete": len(rows) >= total,
        "activation_counts": active, "source_type_counts": sources,
        "mode_counts": modes, "bandwidth_limit_presence": bandwidth,
        "bandwidth_unit_counts": units, "field_presence": field_presence,
        "pages_fetched": pages_fetched, "page_limit": page_limit,
        "partial": partial,
        "wan_configuration_inferred_from_policy_rules": False,
        "actual_traffic_inferred": False,
        "rule_names_ids_targets_and_rates_returned": False,
    }
