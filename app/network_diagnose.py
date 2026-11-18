"""Bounded, read-only bundle of existing gateway and WAN diagnostics."""
from __future__ import annotations

import math
import re
from typing import Callable


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAX_ITEMS = 64
_MAX_SITE_ITEMS = 1024
_MAX_TOPOLOGY_NODES = 128
_MAX_TOPOLOGY_EDGES = 256


class NetworkDiagnoseError(ValueError):
    """Invalid caller input or an unsafe diagnostic response."""

    def __init__(self, code: str, *, upstream_http_status: int | None = None,
                 upstream_error_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.upstream_http_status = upstream_http_status
        self.upstream_error_code = upstream_error_code


def _error_section(exc: NetworkDiagnoseError) -> dict[str, object]:
    result: dict[str, object] = {"status": "error", "error": exc.code,
                                 "capability_status": "unknown"}
    if type(exc.upstream_http_status) is int and 100 <= exc.upstream_http_status <= 599:
        result["upstream_http_status"] = exc.upstream_http_status
    if (type(exc.upstream_error_code) is int and
            -(2**31) <= exc.upstream_error_code <= 2**31 - 1):
        result["upstream_error_code"] = exc.upstream_error_code
    return result


def run(site_ref: str, gateway_ref: str,
        requester: Callable[[str], object]) -> dict[str, object]:
    """Read ten fixed routes for one caller-selected, site-bound gateway."""
    if not isinstance(site_ref, str) or not _REF.fullmatch(site_ref):
        raise NetworkDiagnoseError("site_ref_invalid")
    if not isinstance(gateway_ref, str) or not _REF.fullmatch(gateway_ref):
        raise NetworkDiagnoseError("gateway_ref_invalid")
    if not callable(requester):
        raise NetworkDiagnoseError("connector_unavailable")

    try:
        sites = requester("/v1/sites")
    except Exception:
        raise NetworkDiagnoseError("site_inventory_unavailable") from None
    if (not isinstance(sites, dict) or sites.get("status") != "ok" or
            sites.get("resource") != "sites"):
        raise NetworkDiagnoseError("site_inventory_invalid")
    site_items, site_count = sites.get("items"), sites.get("count")
    if (not isinstance(site_items, list) or len(site_items) > 10000 or
            type(site_count) is not int or site_count != len(site_items)):
        raise NetworkDiagnoseError("site_inventory_invalid")
    if any(not isinstance(item, dict) or not isinstance(item.get("site_ref"), str) or
           not _REF.fullmatch(item["site_ref"]) for item in site_items):
        raise NetworkDiagnoseError("site_inventory_invalid")
    if site_ref not in {item["site_ref"] for item in site_items}:
        raise NetworkDiagnoseError("site_ref_unknown")
    try:
        inventory = requester(f"/v1/sites/{site_ref}/devices")
    except Exception:
        raise NetworkDiagnoseError("gateway_inventory_unavailable") from None
    if (not isinstance(inventory, dict) or inventory.get("status") != "ok" or
            inventory.get("resource") != "devices" or
            inventory.get("site_ref", site_ref) != site_ref):
        raise NetworkDiagnoseError("gateway_inventory_invalid")
    devices, device_count = inventory.get("items"), inventory.get("count")
    if (not isinstance(devices, list) or len(devices) > 10000 or
            type(device_count) is not int or device_count != len(devices)):
        raise NetworkDiagnoseError("gateway_inventory_invalid")
    matched = [item for item in devices if isinstance(item, dict) and
               item.get("device_ref") == gateway_ref]
    if len(matched) != 1:
        raise NetworkDiagnoseError("gateway_ref_unknown")
    device_type = matched[0].get("device_type")
    if not isinstance(device_type, str) or len(device_type) > 64:
        raise NetworkDiagnoseError("gateway_ref_not_gateway")
    if device_type.strip().casefold() not in {"gateway", "router", "gw"}:
        raise NetworkDiagnoseError("gateway_ref_not_gateway")

    root = f"/v1/sites/{site_ref}/gateways/{gateway_ref}"
    routes = (
        ("wan_status", root + "/wan-status", "gateway_wan_status"),
        ("wan_details", root + "/wan-health", "gateway_wan_health"),
        ("health", root + "/health", "gateway_health"),
        ("health_timeline", root + "/health/timeline", "gateway_health_timeline"),
        ("lan_status", root + "/lan-status", "gateway_lan_status"),
        ("ports", root + "/ports", "gateway_ports"),
        ("speed_test_results", root + "/speed-test-results", "gateway_speed_test_results"),
        ("internet_info", root + "/internet-info", "gateway_internet_info"),
        ("site_setting_existence", f"/v1/sites/{site_ref}/settings/existence",
         "site_setting_existence"),
        ("site_capabilities", f"/v1/sites/{site_ref}/capabilities", "site_capabilities"),
    )
    results: dict[str, object] = {}
    successful = 0
    partial = False
    for name, path, resource in routes:
        try:
            raw = requester(path)
            if not isinstance(raw, dict) or raw.get("status") != "ok" or raw.get("resource") != resource:
                raise NetworkDiagnoseError("response_invalid")
            if name in {"site_setting_existence", "site_capabilities"}:
                if raw.get("site_ref") != site_ref:
                    raise NetworkDiagnoseError("response_invalid")
            else:
                bound_ref = raw.get("device_ref", raw.get("gateway_ref"))
                if bound_ref != gateway_ref:
                    raise NetworkDiagnoseError("response_invalid")
            if raw.get("site_ref", site_ref) != site_ref:
                raise NetworkDiagnoseError("response_invalid")
            if name == "wan_details":
                rows, count = raw.get("wan_details"), raw.get("count")
                partial_value = raw.get("partial", False)
                allowed_fields = {"port", "protocol_code", "speed_code", "duplex_code",
                                  "latency", "rx", "tx", "rx_rate", "tx_rate", "loss",
                                  "omitted_field_count"}
                if (not isinstance(rows, list) or len(rows) > 32 or
                        type(count) is not int or count != len(rows) or
                        type(partial_value) is not bool):
                    raise NetworkDiagnoseError("response_invalid")
                for row in rows:
                    if (not isinstance(row, dict) or len(row) > 16 or
                            any(key not in allowed_fields or type(value) not in (int, float) or
                                isinstance(value, bool) or
                                (isinstance(value, float) and not math.isfinite(value))
                                for key, value in row.items())):
                        raise NetworkDiagnoseError("response_invalid")
                result = {"status": "ok", "count": count}
                if partial_value:
                    result["partial"] = True
                    partial = True
                for key in ("omitted_field_count", "omitted_wan_detail_count"):
                    value = raw.get(key)
                    if value is not None:
                        if type(value) is not int or value < 0:
                            raise NetworkDiagnoseError("response_invalid")
                        result[key] = value
                missing_fields = raw.get("missing_fields")
                if missing_fields is not None:
                    if not isinstance(missing_fields, list) or len(missing_fields) > 8 or any(
                            not isinstance(field, str) or len(field) > 64
                            for field in missing_fields):
                        raise NetworkDiagnoseError("response_invalid")
                    result["missing_fields"] = missing_fields
                results[name] = result
                successful += 1
                continue
            data = raw.get("data")
            if data is not None and (not isinstance(data, dict) or len(data) > 512):
                raise NetworkDiagnoseError("response_invalid")
            # These endpoint projections already whitelist controller fields.
            # Keep only the common projected value, window and quality markers.
            result: dict[str, object] = {"status": "ok"}
            if isinstance(data, dict):
                result["data"] = data
            for key in ("partial", "window_start_ms", "window_end_ms", "missing_fields",
                        "omitted_field_count", "omitted_fields", "missing_field_count",
                        "invalid_field_count", "unknown_field_count", "capability_status"):
                value = raw.get(key)
                if value is not None:
                    result[key] = value
            if "items" in raw:
                items, count = raw.get("items"), raw.get("count")
                if (not isinstance(items, list) or len(items) > _MAX_ITEMS or
                        type(count) is not int or count != len(items)):
                    raise NetworkDiagnoseError("response_invalid")
                result["items"] = items
                result["count"] = count
            elif data is None:
                raise NetworkDiagnoseError("response_invalid")
            if result.get("partial") is True:
                partial = True
            results[name] = result
            successful += 1
        except NetworkDiagnoseError as exc:
            results[name] = _error_section(exc)
            partial = True
        except Exception:
            results[name] = {"status": "error", "error": "diagnostic_unavailable",
                             "capability_status": "unknown"}
            partial = True

    if successful == 0:
        return {"status": "error", "error": "all_diagnostics_failed",
                "site_ref": site_ref, "gateway_ref": gateway_ref,
                "capability_status": "unknown", "results": results}
    if successful != len(routes):
        partial = True
    return {"status": "partial" if partial else "ok", "site_ref": site_ref,
            "gateway_ref": gateway_ref, "capability_status": "unknown",
            "results": results}


def run_site(site_ref: str, requester: Callable[[str], object]) -> dict[str, object]:
    """Build a bounded site network overview from fixed reads and current topology."""
    if not isinstance(site_ref, str) or not _REF.fullmatch(site_ref):
        raise NetworkDiagnoseError("site_ref_invalid")
    if not callable(requester):
        raise NetworkDiagnoseError("connector_unavailable")

    root = f"/v1/sites/{site_ref}"
    routes = (
        ("devices", root + "/devices", "devices"),
        ("overview", root + "/health/summary", "site_overview"),
        ("networks", root + "/networks", "networks"),
        ("dhcp", root + "/dhcp/leases", "dhcp_leases"),
        ("topology_network_summary", root + "/topology/network-summary",
         "site_topology_network_summary"),
        ("vlan_summary", root + "/topology/vlan-summary", "site_topology_vlan_summary"),
        ("dns_cache", root + "/dns/cache", "dns_cache_settings"),
        ("dns_proxy", root + "/dns/proxy", "dns_proxy_settings"),
        ("dns_records", root + "/dns/records", "lan_dns_records"),
        ("events", root + "/events", "site_events"),
        ("alerts", root + "/alerts", "site_alerts"),
    )
    results: dict[str, object] = {}
    successful = 0
    partial = False
    device_refs: set[str] = set()
    device_inventory_ok = False

    for name, path, resource in routes:
        try:
            raw = requester(path)
            if (not isinstance(raw, dict) or raw.get("status") != "ok" or
                    raw.get("resource") != resource or
                    raw.get("site_ref", site_ref) != site_ref):
                raise NetworkDiagnoseError("response_invalid")
            if name == "overview":
                data = raw.get("data")
                if not isinstance(data, dict) or len(data) > 128:
                    raise NetworkDiagnoseError("response_invalid")
                section: dict[str, object] = {"status": "ok", "data": data}
                if raw.get("partial") is True:
                    section["partial"] = True
                    partial = True
            elif name == "topology_network_summary":
                data = raw.get("data")
                keys = ("split_network_count", "default_network_count",
                        "configuring_network_count", "ssid_count",
                        "ssid_vlan_enabled_count", "ssid_configuring_count",
                        "ssid_client_count_sum", "ssid_vlan_id_count")
                metadata = ("unknown_field_count", "unknown_network_field_count",
                            "unknown_ssid_field_count")
                if (not isinstance(data, dict) or set(data) != {*keys, *metadata, "partial"} or
                        any(data[key] is not None and
                            (type(data[key]) is not int or data[key] < 0)
                            for key in keys) or
                        any(type(data[key]) is not int or data[key] < 0
                            for key in metadata) or type(data["partial"]) is not bool):
                    raise NetworkDiagnoseError("response_invalid")
                results[name] = {"status": "ok", "data": {
                    key: data[key] for key in (*keys, *metadata, "partial")}}
                if data["partial"]:
                    partial = True
            elif name == "vlan_summary":
                data = raw.get("data")
                keys = ("network_count", "distinct_vlan_count", "default_network_count",
                        "configuring_network_count", "missing_vlan_id_count")
                metadata = ("unknown_network_field_count", "unknown_field_count")
                if (not isinstance(data, dict) or set(data) != {*keys, *metadata, "partial"} or
                        any(data[key] is not None and
                            (type(data[key]) is not int or data[key] < 0)
                            for key in keys) or
                        any(type(data[key]) is not int or data[key] < 0
                            for key in metadata) or type(data["partial"]) is not bool):
                    raise NetworkDiagnoseError("response_invalid")
                results[name] = {"status": "ok", "data": {
                    key: data[key] for key in (*keys, *metadata, "partial")}}
                if data["partial"]:
                    partial = True
            elif name in {"dhcp", "dns_cache", "dns_proxy"}:
                data = raw.get("data")
                if name == "dhcp":
                    summary = raw.get("summary")
                    count = raw.get("count")
                    allowed = {"total", "devices", "clients", "dynamic", "static"}
                    if (not isinstance(summary, dict) or set(summary) != allowed or
                            type(count) is not int or count < 0 or
                            any(type(summary[key]) is not int or summary[key] < 0
                                for key in allowed) or summary["total"] != count):
                        raise NetworkDiagnoseError("response_invalid")
                    results[name] = {"status": "ok", "count": count,
                                     "binding_counts": summary}
                else:
                    if not isinstance(data, dict) or len(data) > 128:
                        raise NetworkDiagnoseError("response_invalid")
                    # These endpoint projections already contain safe boolean/enum fields.
                    results[name] = {"status": "ok", "data": data}
            elif name == "dns_records":
                items, count = raw.get("items"), raw.get("count")
                if (not isinstance(items, list) or len(items) > _MAX_SITE_ITEMS or
                        type(count) is not int or count != len(items)):
                    raise NetworkDiagnoseError("response_invalid")
                counts = {"ip": 0, "cname": 0, "forward": 0, "enabled": 0}
                for item in items:
                    if (not isinstance(item, dict) or item.get("record_type") not in {"ip", "cname", "forward"} or
                            type(item.get("enabled")) is not bool):
                        raise NetworkDiagnoseError("response_invalid")
                    counts[item["record_type"]] += 1
                    counts["enabled"] += int(item["enabled"])
                results[name] = {"status": "ok", "count": count,
                                 "record_counts": counts}
            elif name in {"events", "alerts"}:
                items, count = raw.get("items"), raw.get("count")
                total_count = raw.get("total_count", count)
                start, end = raw.get("window_start_ms"), raw.get("window_end_ms")
                if (not isinstance(items, list) or len(items) > _MAX_SITE_ITEMS or
                        type(count) is not int or count != len(items) or
                        type(total_count) is not int or not count <= total_count <= 2**63 - 1 or
                        type(start) is not int or type(end) is not int or start > end):
                    raise NetworkDiagnoseError("response_invalid")
                modules = {"system": 0, "device": 0, "client": 0, "other": 0}
                severities = {"info": 0, "warning": 0, "error": 0, "critical": 0, "other": 0}
                for item in items:
                    if (not isinstance(item, dict) or type(item.get("time_ms")) is not int or
                            not start <= item["time_ms"] <= end or
                            item.get("module") not in modules):
                        raise NetworkDiagnoseError("response_invalid")
                    modules[item["module"]] += 1
                    if name == "alerts":
                        if item.get("severity") not in severities:
                            raise NetworkDiagnoseError("response_invalid")
                        severities[item["severity"]] += 1
                module_summary = raw.get("module_counts")
                if module_summary is not None:
                    expected_modules = {"system", "device", "client"}
                    if (name != "events" or not isinstance(module_summary, dict) or
                            set(module_summary) != expected_modules or
                            any(type(value) is not int or not 0 <= value <= 2**63 - 1
                                for value in module_summary.values()) or
                            sum(module_summary.values()) != total_count):
                        raise NetworkDiagnoseError("response_invalid")
                    modules.update(module_summary)
                section_partial = raw.get("partial", total_count > count)
                if type(section_partial) is not bool or section_partial != (total_count > count):
                    raise NetworkDiagnoseError("response_invalid")
                results[name] = {"status": "ok", "count": total_count,
                                 "sampled_count": count,
                                 "window_start_ms": start, "window_end_ms": end,
                                 "module_counts": modules}
                if section_partial:
                    results[name]["partial"] = True
                    partial = True
                if name == "alerts":
                    results[name]["severity_counts"] = severities
            else:
                items, count = raw.get("items"), raw.get("count")
                if (not isinstance(items, list) or len(items) > _MAX_SITE_ITEMS or
                        type(count) is not int or count < 0 or count != len(items)):
                    raise NetworkDiagnoseError("response_invalid")
                if name == "devices":
                    type_counts = {"ap": 0, "gateway": 0, "switch": 0, "other": 0}
                    for item in items:
                        if not isinstance(item, dict):
                            raise NetworkDiagnoseError("response_invalid")
                        ref = item.get("device_ref")
                        if not isinstance(ref, str) or not _REF.fullmatch(ref) or ref in device_refs:
                            raise NetworkDiagnoseError("response_invalid")
                        device_refs.add(ref)
                        raw_type = item.get("device_type")
                        if raw_type is None:
                            kind = ""
                        elif isinstance(raw_type, str) and len(raw_type) <= 64:
                            kind = raw_type.strip().casefold()
                        else:
                            raise NetworkDiagnoseError("response_invalid")
                        bucket = ("ap" if kind in {"ap", "access point", "accesspoint"} else
                                  "gateway" if kind in {"gateway", "router", "gw"} else
                                  "switch" if kind in {"switch", "sw"} else "other")
                        type_counts[bucket] += 1
                    results[name] = {"status": "ok", "count": count,
                                     "device_type_counts": type_counts}
                    device_inventory_ok = True
                else:
                    # Network names, IDs, VLANs and addressing are not needed
                    # for the overview; only the validated inventory count is kept.
                    results[name] = {"status": "ok", "count": count}
            if name == "overview":
                results[name] = section
            successful += 1
        except NetworkDiagnoseError as exc:
            results[name] = {"status": "error", "error": exc.code}
            partial = True
        except Exception:
            results[name] = {"status": "error", "error": "diagnostic_unavailable"}
            partial = True

    if not device_inventory_ok:
        results["topology"] = {"status": "error", "error": "device_inventory_required"}
        partial = True
    else:
        try:
            raw = requester(root + "/topology")
            if (not isinstance(raw, dict) or raw.get("status") != "ok" or
                    raw.get("resource") != "site_topology" or raw.get("site_ref") != site_ref):
                raise NetworkDiagnoseError("response_invalid")
            nodes, edges = raw.get("nodes"), raw.get("edges")
            if (not isinstance(nodes, list) or len(nodes) > 1000 or
                    not isinstance(edges, list) or len(edges) > 5000):
                raise NetworkDiagnoseError("response_invalid")
            node_refs: set[str] = set()
            safe_nodes: list[dict[str, object]] = []
            for item in nodes:
                if not isinstance(item, dict):
                    raise NetworkDiagnoseError("response_invalid")
                ref, kind = item.get("device_ref"), item.get("device_type")
                if (not isinstance(ref, str) or not _REF.fullmatch(ref) or ref not in device_refs or
                        ref in node_refs or kind not in {"ap", "gateway", "switch"}):
                    raise NetworkDiagnoseError("response_invalid")
                node_refs.add(ref)
                projected: dict[str, object] = {"device_ref": ref, "device_type": kind}
                for key in ("disconnected", "license_active"):
                    if key in item:
                        if type(item[key]) is not bool:
                            raise NetworkDiagnoseError("response_invalid")
                        projected[key] = item[key]
                safe_nodes.append(projected)
            safe_edges: list[dict[str, str]] = []
            seen_edges: set[tuple[str, str]] = set()
            for item in edges:
                if not isinstance(item, dict):
                    raise NetworkDiagnoseError("response_invalid")
                source, target = item.get("from_device_ref"), item.get("to_device_ref")
                edge = (source, target)
                if (not isinstance(source, str) or not isinstance(target, str) or
                        source not in node_refs or target not in node_refs or source == target or
                        edge in seen_edges):
                    raise NetworkDiagnoseError("response_invalid")
                seen_edges.add(edge)
                safe_edges.append({"from_device_ref": source, "to_device_ref": target})
            safe_nodes.sort(key=lambda item: str(item["device_ref"]))
            safe_edges.sort(key=lambda item: (item["from_device_ref"], item["to_device_ref"]))
            node_count, edge_count = len(safe_nodes), len(safe_edges)
            truncated = node_count > _MAX_TOPOLOGY_NODES or edge_count > _MAX_TOPOLOGY_EDGES
            topology_partial = raw.get("partial", False)
            omitted_nodes, omitted_edges = raw.get("omitted_node_count", 0), raw.get("omitted_edge_count", 0)
            last_update = raw.get("last_update_ms")
            if (type(topology_partial) is not bool or type(omitted_nodes) is not int or omitted_nodes < 0 or
                    type(omitted_edges) is not int or omitted_edges < 0 or
                    (last_update is not None and (type(last_update) is not int or last_update < 0))):
                raise NetworkDiagnoseError("response_invalid")
            results["topology"] = {
                "status": "ok", "node_count": node_count, "edge_count": edge_count,
                "nodes": safe_nodes[:_MAX_TOPOLOGY_NODES],
                "edges": safe_edges[:_MAX_TOPOLOGY_EDGES],
                "omitted_node_count": omitted_nodes + max(0, node_count - _MAX_TOPOLOGY_NODES),
                "omitted_edge_count": omitted_edges + max(0, edge_count - _MAX_TOPOLOGY_EDGES),
                "partial": topology_partial or truncated,
                    "truncated": truncated,
            }
            if last_update is not None:
                results["topology"]["last_update_ms"] = last_update
            if topology_partial or truncated:
                partial = True
            successful += 1
        except NetworkDiagnoseError as exc:
            results["topology"] = {"status": "error", "error": exc.code}
            partial = True
        except Exception:
            results["topology"] = {"status": "error", "error": "diagnostic_unavailable"}
            partial = True

    if successful == 0:
        return {"status": "error", "error": "all_diagnostics_failed", "site_ref": site_ref,
                "capability_status": "unknown", "results": results}
    return {"status": "partial" if partial else "ok", "site_ref": site_ref,
            "capability_status": "unknown", "results": results}
