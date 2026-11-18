"""Project existing per-operation evidence into complete read workflows."""
from __future__ import annotations

import re
from typing import Any


_COMMON_WLAN = (
    "wifi_health", "wifi_subhealth", "site_dashboard_channels",
    "site_client_signal_distribution", "site_6ghz_ap_presence",
    "site_rogue_ap_results", "site_wids_summary", "site_wids_blacklist_summary",
    "band_steering", "rrm_settings", "roaming_settings",
    "site_topology_network_summary",
)
_AP_READS = (
    "sites", "devices", "ap_health", "ap_health_timeline", "ap_radio_config",
    "ap_rf_scan", "ap_wifi_interference", "ap_lan_traffic", "ap_speed_test_results",
    "ap_wired_downlink", "ap_wired_uplink", "ap_ports", "ap_lldp_config",
    "ap_port_vlans", "ap_wlan_overrides",
)
_CLIENT_READS = (
    "sites", "clients", "client_connection_history", "client_history",
    "client_health_timeline", "client_timeline_connect", "client_timeline_association",
    "client_timeline_roaming", "client_timeline_disconnect",
)

WORKFLOWS: tuple[dict[str, object], ...] = (
    {"id": "site_wlan", "label": "Standort-WLAN-Diagnose",
     "entry_point": "omada_wifi_diagnose_site",
     "operations": _COMMON_WLAN},
    {"id": "ap_wlan", "label": "Access-Point-WLAN-Diagnose",
     "entry_point": "omada_wifi_diagnose_ap",
     "operations": tuple(sorted(set(_COMMON_WLAN) | set(_AP_READS)))},
    {"id": "ap_comparison", "label": "Vergleich zweier Access Points",
     "entry_point": "omada_wifi_compare_aps",
     "operations": (
         "sites", "devices", "ap_health", "ap_radio_config", "ap_rf_scan",
         "ap_wifi_interference", "ap_lan_traffic",
     )},
    {"id": "client_wlan", "label": "Client-Verbindungsdiagnose",
     "entry_point": "omada_wifi_diagnose_client",
     "operations": tuple(sorted(set(_COMMON_WLAN) | set(_CLIENT_READS)))},
    {"id": "gateway_network", "label": "Gateway-Netzwerkdiagnose",
     "entry_point": "omada_network_diagnose_gateway",
     "operations": (
         "sites", "devices", "gateway_wan_status", "gateway_wan_health",
         "gateway_health", "gateway_health_timeline", "gateway_ports",
         "gateway_speed_test_results", "gateway_internet_info",
         "site_setting_existence", "site_capabilities",
     )},
    {"id": "switch_network", "label": "Switch-Netzwerkdiagnose",
     "entry_point": "omada_network_diagnose_switch",
     "operations": (
         "sites", "devices", "switch_health", "switch_ports", "switch_port_counters",
         "switch_health_timeline", "switch_sdm_usage", "switch_cable_test_logs",
         "switch_cable_test_full_results", "switch_cable_test_increment_results",
         "switch_cable_test_ports", "switch_dhcp_users", "switch_ospf_neighbors",
         "switch_port_networks", "switch_exist_networks", "switch_networks",
         "switch_interfaces", "switch_routing_table", "switch_static_routes",
         "switch_vrfs", "switch_vlan_interfaces", "switch_statistics",
         "switch_port_poe_info", "switch_vlans", "switch_lldp_neighbors",
     )},
    {"id": "site_network", "label": "Standort-Netzwerkübersicht",
     "entry_point": "omada_network_overview",
     "operations": (
         "devices", "site_overview", "networks", "dhcp_leases", "dns_cache_settings",
         "dns_proxy_settings", "lan_dns_records", "site_events", "site_alerts",
         "site_topology_network_summary", "site_topology_vlan_summary", "site_topology",
     )},
    {"id": "ssid_network", "label": "WLAN-Netzwerkzuordnung",
     "entry_point": "omada_ssid_network_summary",
     "operations": ("sites", "ssids", "networks", "ssid_configuration")},
)

# Source coverage is generated from docs/OPERATION_EVIDENCE.json. The runtime
# catalog is intentionally smaller and does not ship source documents.
_TWO_SOURCE_OPERATIONS = frozenset({
    "site_topology", "site_topology_network_summary", "site_topology_vlan_summary",
    "ssid_configuration", "ssids", "switch_interfaces", "switch_static_routes",
})
_DOCUMENTED_SOURCE_COUNT = 3
_EXPECTED_SOURCE_COUNT = 3
_SAFE_EVIDENCE_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_STATES = {"documented", "observed", "unknown", "failed"}


def _operation_report(operation_id: str,
                      catalog_item: dict[str, object] | None) -> dict[str, object]:
    documented_count = (2 if operation_id in _TWO_SOURCE_OPERATIONS
                        else _DOCUMENTED_SOURCE_COUNT)
    evidence_value = (catalog_item.get("runtime_evidence")
                      if isinstance(catalog_item, dict) else None)
    evidence = [row for row in evidence_value if isinstance(row, dict)] \
        if isinstance(evidence_value, list) else []
    observed_count = sum(
        row.get("result") == "success" and
        row.get("controller_response_observed") is True and
        row.get("response_shape_state") == "response_shape_supported"
        for row in evidence)
    failed_count = sum(row.get("result") == "failure" for row in evidence)
    unknown_count = len(evidence) - observed_count - failed_count
    if catalog_item is None:
        state = "unknown"
    elif failed_count and not observed_count and not unknown_count:
        state = "failed"
    elif observed_count and not failed_count and not unknown_count:
        state = "observed"
    elif not evidence and documented_count:
        state = "documented"
    else:
        state = "unknown"
    failures: dict[str, int] = {}
    for row in evidence:
        if row.get("result") != "failure":
            continue
        failure_class = row.get("failure_class")
        if isinstance(failure_class, str) and _SAFE_EVIDENCE_CODE.fullmatch(failure_class):
            failures[failure_class] = failures.get(failure_class, 0) + 1
    last_at = max((value for row in evidence
                   if isinstance((value := row.get("recorded_at")), str) and
                   len(value) <= 40), default=None)
    error_codes = [row.get("error_code") for row in evidence
                   if row.get("result") == "failure" and
                   isinstance(row.get("error_code"), str) and
                   _SAFE_EVIDENCE_CODE.fullmatch(row["error_code"])]
    item: dict[str, object] = {
        "operation": operation_id,
        "status": state,
        "documented_source_count": documented_count,
        "expected_source_count": _EXPECTED_SOURCE_COUNT,
        "runtime_evidence_count": len(evidence),
        "observed_success_count": observed_count,
        "failed_evidence_count": failed_count,
        "unknown_evidence_count": unknown_count,
        "failure_classes": dict(sorted(failures.items())),
    }
    if last_at:
        item["last_evidence_at"] = last_at
    if error_codes:
        item["error_codes"] = sorted(set(error_codes))[:8]
    if isinstance(catalog_item, dict):
        route = catalog_item.get("route")
        if isinstance(route, str) and len(route) <= 200:
            item["route"] = route
    return item


def project_diagnostic_capability_report(catalog: object) -> dict[str, object]:
    """Summarize workflows from existing evidence only; never invoke operations."""
    if (not isinstance(catalog, dict) or catalog.get("status") != "ok" or
            not isinstance(catalog.get("items"), list) or
            len(catalog["items"]) > 2_000 or
            not all(isinstance(item, dict) and isinstance(item.get("operation"), str)
                    for item in catalog["items"])):
        return {"status": "error", "error": "capability_catalog_invalid"}
    catalog_items = {item["operation"]: item for item in catalog["items"]}
    workflows: list[dict[str, object]] = []
    for workflow in WORKFLOWS:
        operation_ids = workflow["operations"]
        operations = [_operation_report(
            operation_id, catalog_items.get(operation_id)) for operation_id in operation_ids]
        counts = {state: sum(item["status"] == state for item in operations)
                  for state in sorted(_STATES)}
        if counts["failed"]:
            state = "failed"
        elif counts["unknown"]:
            state = "unknown"
        elif counts["observed"] == len(operations):
            state = "observed"
        elif counts["documented"] == len(operations):
            state = "documented"
        else:
            state = "unknown"
        workflows.append({
            "id": workflow["id"], "label": workflow["label"],
            "entry_point": workflow["entry_point"], "status": state,
            "required_operation_count": len(operations),
            "operation_status_counts": counts, "operations": operations,
        })
    return {
        "status": "ok", "resource": "diagnostic_capability_summary",
        "catalog_complete": False,
        "catalog_scope": catalog.get("catalog_scope", "unknown"),
        "network_requests_made": 0,
        "workflows": workflows,
        "status_meanings": {
            "documented": "Source contracts are recorded; this process has no runtime observation.",
            "observed": "Every required read has a successful live response with a supported projected shape.",
            "unknown": "Coverage is incomplete, the evidence is mixed, or response support is unresolved.",
            "failed": "At least one required read has recorded failure evidence.",
        },
        "limitations": [
            "Document counts describe the three bundled source exports, not the controller configured by the operator.",
            "A failure or success is limited to the recorded target and time; no broad probe was run.",
            "Route availability does not establish all per-operation permissions or device support.",
        ],
    }
