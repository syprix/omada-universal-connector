"""Redacted summary of configured LAN multicast snooping settings."""
from __future__ import annotations

from collections.abc import Mapping


class SiteLanMulticastSummaryError(ValueError):
    pass


def summarize_site_lan_multicasts(rows: object, total: object,
                                  pages_fetched: int, page_limit: int) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or type(total) is not int or
            total < len(rows) or not 0 <= total < (1 << 63) or
            type(pages_fetched) is not int or not 0 <= pages_fetched <= 10 or
            type(page_limit) is not int or not 1 <= page_limit <= 10):
        raise SiteLanMulticastSummaryError("input_invalid")
    protocols = {"igmp": 0, "mld": 0, "unknown": 0}
    unknown_rules = {"forward": 0, "discard": 0, "router_port_first": 0, "unknown": 0}
    flags = {key: {"enabled": 0, "disabled": 0, "unknown": 0} for key in (
        "flood_known", "querier", "manual_router_port", "unknown_multicast_exception",
        "report_suppression", "report_suppression_exception")}
    field_presence = {key: {"present": 0, "missing": 0} for key in (
        "protocol", "unknown_multicast_rule", "network_associations")}
    partial = len(rows) < total
    known = {"id", "name", "networks", "protocol", "unknownMulticastRule",
             "unknownMulticastExceptDevice", "floodKnownEnable", "querierEnable",
             "routerPortEnable", "resource", "routerPorts", "snoopConfig",
             "igmpQueriers", "mldQueriers"}

    def count_flag(target: str, source: object) -> None:
        if source is None:
            flags[target]["unknown"] += 1
        elif type(source) is bool:
            flags[target]["enabled" if source else "disabled"] += 1
        else:
            raise SiteLanMulticastSummaryError("field_invalid")

    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32 or set(row) - known:
            if not isinstance(row, Mapping) or len(row) > 32:
                raise SiteLanMulticastSummaryError("row_invalid")
            partial = True
        for key in ("id", "name"):
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 512):
                raise SiteLanMulticastSummaryError("field_invalid")
        protocol = row.get("protocol")
        if protocol is None:
            field_presence["protocol"]["missing"] += 1
            protocols["unknown"] += 1
            partial = True
        elif type(protocol) is not int:
            raise SiteLanMulticastSummaryError("field_invalid")
        else:
            field_presence["protocol"]["present"] += 1
            protocols[{0: "igmp", 1: "mld"}.get(protocol, "unknown")] += 1
            partial |= protocol not in (0, 1)
        rule = row.get("unknownMulticastRule")
        if rule is None:
            field_presence["unknown_multicast_rule"]["missing"] += 1
            unknown_rules["unknown"] += 1
            partial = True
        elif type(rule) is not int:
            raise SiteLanMulticastSummaryError("field_invalid")
        else:
            field_presence["unknown_multicast_rule"]["present"] += 1
            unknown_rules[{0: "forward", 1: "discard", 2: "router_port_first"}.get(
                rule, "unknown")] += 1
            partial |= rule not in (0, 1, 2)
        networks = row.get("networks")
        if networks is None:
            field_presence["network_associations"]["missing"] += 1
            partial = True
        elif not isinstance(networks, list) or len(networks) > 20_000:
            raise SiteLanMulticastSummaryError("field_invalid")
        else:
            field_presence["network_associations"]["present"] += 1
            if any(not isinstance(network, Mapping) for network in networks):
                raise SiteLanMulticastSummaryError("field_invalid")
        for collection in ("routerPorts", "igmpQueriers", "mldQueriers"):
            value = row.get(collection)
            if value is not None and (not isinstance(value, list) or len(value) > 20_000 or
                                      any(not isinstance(item, Mapping) for item in value)):
                raise SiteLanMulticastSummaryError("field_invalid")
        if "resource" in row and (type(row["resource"]) is not int or
                                  not -(1 << 31) <= row["resource"] < (1 << 31)):
            raise SiteLanMulticastSummaryError("field_invalid")

        for target, source in (("flood_known", "floodKnownEnable"),
                               ("querier", "querierEnable"),
                               ("manual_router_port", "routerPortEnable")):
            count_flag(target, row.get(source))
            partial |= source not in row
        unknown_except = row.get("unknownMulticastExceptDevice")
        if unknown_except is not None and (not isinstance(unknown_except, Mapping) or
                                            len(unknown_except) > 2 or
                                            set(unknown_except) - {"enable", "deviceList"}):
            raise SiteLanMulticastSummaryError("field_invalid")
        if isinstance(unknown_except, Mapping) and "deviceList" in unknown_except and (
                not isinstance(unknown_except["deviceList"], list) or
                len(unknown_except["deviceList"]) > 20_000 or
                any(not isinstance(device, Mapping) for device in unknown_except["deviceList"])):
            raise SiteLanMulticastSummaryError("field_invalid")
        count_flag("unknown_multicast_exception",
                   unknown_except.get("enable") if isinstance(unknown_except, Mapping) else None)
        partial |= not isinstance(unknown_except, Mapping) or "enable" not in unknown_except
        snoop = row.get("snoopConfig")
        if snoop is not None and (not isinstance(snoop, Mapping) or len(snoop) > 8 or
                                  set(snoop) - {"reportSuppressionEnable", "fastLeaveEnable",
                                                "reportSuppressionExceptDevice", "memberPortAgingTime",
                                                "routerPortAgingTime", "leaveTime"}):
            if not isinstance(snoop, Mapping) or len(snoop) > 8:
                raise SiteLanMulticastSummaryError("field_invalid")
            partial = True
        if isinstance(snoop, Mapping):
            for key in ("memberPortAgingTime", "routerPortAgingTime", "leaveTime"):
                if key in snoop and (type(snoop[key]) is not int or not 0 <= snoop[key] < (1 << 31)):
                    raise SiteLanMulticastSummaryError("field_invalid")
        count_flag("report_suppression",
                   snoop.get("reportSuppressionEnable") if isinstance(snoop, Mapping) else None)
        partial |= not isinstance(snoop, Mapping) or "reportSuppressionEnable" not in snoop
        report_except = snoop.get("reportSuppressionExceptDevice") if isinstance(snoop, Mapping) else None
        if report_except is not None and (not isinstance(report_except, Mapping) or len(report_except) > 2 or
                                          set(report_except) - {"enable", "deviceList"}):
            raise SiteLanMulticastSummaryError("field_invalid")
        if isinstance(report_except, Mapping) and "deviceList" in report_except and (
                not isinstance(report_except["deviceList"], list) or
                len(report_except["deviceList"]) > 20_000 or
                any(not isinstance(device, Mapping) for device in report_except["deviceList"])):
            raise SiteLanMulticastSummaryError("field_invalid")
        count_flag("report_suppression_exception",
                   report_except.get("enable") if isinstance(report_except, Mapping) else None)
        partial |= not isinstance(report_except, Mapping) or "enable" not in report_except
    return {
        "configuration_count": len(rows), "total_count": total,
        "coverage_complete": len(rows) >= total,
        "protocol_counts": protocols, "unknown_multicast_rule_counts": unknown_rules,
        "feature_flag_counts": flags, "field_presence": field_presence,
        "pages_fetched": pages_fetched, "page_limit": page_limit,
        "partial": partial,
        "configuration_only_no_multicast_traffic_inferred": True,
        "addresses_names_and_identifiers_returned": False,
    }
