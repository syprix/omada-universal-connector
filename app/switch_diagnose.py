"""Bounded, read-only diagnostic bundle for one inventoried switch."""
from __future__ import annotations

import math
import re
from typing import Callable


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAX_ITEMS = 64
_MAX_DEPTH = 8
_MAX_OBJECT_FIELDS = 512


class SwitchDiagnoseError(ValueError):
    """Invalid caller input or an unsafe diagnostic response."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _bound_json(value: object, depth: int = 0) -> tuple[object, int]:
    """Keep projected JSON bounded, counting omitted array entries."""
    if depth > _MAX_DEPTH:
        raise SwitchDiagnoseError("response_invalid")
    if isinstance(value, dict):
        if len(value) > _MAX_OBJECT_FIELDS or any(not isinstance(key, str) for key in value):
            raise SwitchDiagnoseError("response_invalid")
        output: dict[str, object] = {}
        omitted = 0
        for key, item in value.items():
            output[key], child_omitted = _bound_json(item, depth + 1)
            omitted += child_omitted
        return output, omitted
    if isinstance(value, list):
        omitted = max(0, len(value) - _MAX_ITEMS)
        output = []
        for item in value[:_MAX_ITEMS]:
            bounded, child_omitted = _bound_json(item, depth + 1)
            output.append(bounded)
            omitted += child_omitted
        return output, omitted
    if type(value) is float and not math.isfinite(value):
        raise SwitchDiagnoseError("response_invalid")
    if value is None or type(value) in {str, int, float, bool}:
        return value, 0
    raise SwitchDiagnoseError("response_invalid")


def run(site_ref: str, switch_ref: str,
        requester: Callable[[str], object]) -> dict[str, object]:
    """Read six fixed switch routes after checking fresh site/device inventory."""
    if not isinstance(site_ref, str) or not _REF.fullmatch(site_ref):
        raise SwitchDiagnoseError("site_ref_invalid")
    if not isinstance(switch_ref, str) or not _REF.fullmatch(switch_ref):
        raise SwitchDiagnoseError("switch_ref_invalid")
    if not callable(requester):
        raise SwitchDiagnoseError("connector_unavailable")

    try:
        sites = requester("/v1/sites")
        if (not isinstance(sites, dict) or sites.get("status") != "ok" or
                sites.get("resource") != "sites" or
                not isinstance(sites.get("items"), list) or
                not any(isinstance(item, dict) and item.get("site_ref") == site_ref
                        for item in sites["items"])):
            raise SwitchDiagnoseError("site_ref_unknown")
        inventory = requester(f"/v1/sites/{site_ref}/devices")
        if (not isinstance(inventory, dict) or inventory.get("status") != "ok" or
                inventory.get("resource") != "devices" or
                not isinstance(inventory.get("items"), list)):
            raise SwitchDiagnoseError("device_inventory_invalid")
        matches = [item for item in inventory["items"]
                   if isinstance(item, dict) and item.get("device_ref") == switch_ref]
        if not matches:
            raise SwitchDiagnoseError("switch_ref_unknown")
        if len(matches) != 1:
            raise SwitchDiagnoseError("switch_ref_ambiguous")
        device_type = matches[0].get("device_type")
        if not isinstance(device_type, str) or device_type.strip().casefold() not in {"switch", "sw"}:
            raise SwitchDiagnoseError("switch_ref_unknown")
    except SwitchDiagnoseError:
        raise
    except Exception:
        raise SwitchDiagnoseError("connector_unavailable") from None

    root = f"/v1/sites/{site_ref}/switches/{switch_ref}"
    routes = (
        ("health", root + "/health", "switch_health"),
        ("health_timeline", root + "/health/timeline", "switch_health_timeline"),
        ("sdm_usage", root + "/sdm-usage", "switch_sdm_usage"),
        ("cable_test_logs", root + "/cable-test/logs", "switch_cable_test_logs"),
        ("cable_test_full_results", root + "/cable-test/full-results", "switch_cable_test_full_results"),
        ("cable_test_increment_results", root + "/cable-test/increment-results", "switch_cable_test_increment_results"),
        ("cable_test_ports", root + "/cable-test/ports", "switch_cable_test_ports"),
        ("dhcp_users", root + "/dhcp/users", "switch_dhcp_users"),
        ("ospf_neighbors", root + "/ospf-neighbors", "switch_ospf_neighbors"),
        ("port_networks", root + "/port-networks", "switch_port_networks"),
        ("exist_networks", root + "/exist-networks", "switch_exist_networks"),
        ("networks", root + "/networks", "switch_networks"),
        ("interfaces", root + "/interfaces", "switch_interfaces"),
        ("routing_table", root + "/routing-table", "switch_routing_table"),
        ("static_routes", root + "/static-routes", "switch_static_routes"),
        ("vrfs", root + "/vrfs", "switch_vrfs"),
        ("vlan_interfaces", root + "/vlan-interfaces", "switch_vlan_interfaces"),
        ("statistics", root + "/statistics", "switch_statistics"),
        ("ports", root + "/ports", "switch_ports"),
        ("port_counters", root + "/ports/counters", "switch_port_counters"),
        ("poe", root + "/ports/poe-info", "switch_port_poe_info"),
        ("vlans", root + "/vlans", "switch_vlans"),
        ("lldp", root + "/lldp-neighbors", "switch_lldp_neighbors"),
    )
    results: dict[str, object] = {}
    successful = 0
    partial = False
    for name, path, resource in routes:
        try:
            raw = requester(path)
            if not isinstance(raw, dict) or raw.get("status") != "ok" or raw.get("resource") != resource:
                raise SwitchDiagnoseError("response_invalid")
            bound_ref = raw.get("device_ref", raw.get("switch_ref"))
            if bound_ref != switch_ref:
                raise SwitchDiagnoseError("response_invalid")
            if raw.get("site_ref", site_ref) != site_ref:
                raise SwitchDiagnoseError("response_invalid")
            result: dict[str, object] = {"status": "ok"}
            omitted_items = 0
            data = raw.get("data")
            if data is not None:
                if not isinstance(data, dict):
                    raise SwitchDiagnoseError("response_invalid")
                result["data"], omitted_items = _bound_json(data)
            for key in ("partial", "window_start_ms", "window_end_ms", "missing_fields",
                        "omitted_field_count", "omitted_fields", "missing_field_count",
                        "invalid_field_count", "unknown_field_count", "capability_status"):
                value = raw.get(key)
                if value is not None:
                    result[key] = value
            if "items" in raw:
                items, count = raw.get("items"), raw.get("count")
                if (not isinstance(items, list) or
                        type(count) is not int or count != len(items)):
                    raise SwitchDiagnoseError("response_invalid")
                result["items"], item_omitted = _bound_json(items)
                result["count"] = count
                omitted_items += item_omitted
            elif "summary" in raw:
                count = raw.get("count")
                if type(count) is not int or count < 0:
                    raise SwitchDiagnoseError("response_invalid")
                result["count"] = count
            elif data is None:
                raise SwitchDiagnoseError("response_invalid")
            if "summary" in raw:
                summary = raw.get("summary")
                if not isinstance(summary, dict):
                    raise SwitchDiagnoseError("response_invalid")
                result["summary"], summary_omitted = _bound_json(summary)
                omitted_items += summary_omitted
            if "membership_summary" in raw:
                membership_summary = raw.get("membership_summary")
                if not isinstance(membership_summary, dict):
                    raise SwitchDiagnoseError("response_invalid")
                result["membership_summary"], membership_omitted = _bound_json(membership_summary)
                omitted_items += membership_omitted
            if omitted_items:
                result["omitted_entry_count"] = omitted_items
                partial = True
            if result.get("partial") is True:
                partial = True
            results[name] = result
            successful += 1
        except SwitchDiagnoseError as exc:
            results[name] = {"status": "error", "error": exc.code,
                             "capability_status": "unknown"}
            partial = True
        except Exception:
            results[name] = {"status": "error", "error": "diagnostic_unavailable",
                             "capability_status": "unknown"}
            partial = True

    if successful == 0:
        return {"status": "error", "error": "all_diagnostics_failed",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "capability_status": "unknown", "results": results}
    if successful != len(routes):
        partial = True
    return {"status": "partial" if partial else "ok", "site_ref": site_ref,
            "switch_ref": switch_ref, "capability_status": "unknown",
            "results": results}
