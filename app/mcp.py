"""Small, stateless MCP Streamable HTTP surface for registered read routes.

This adapter intentionally exposes only the connector's fixed GET registry.
It never accepts an upstream URL, method, or arbitrary route from a caller.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.parse import urlsplit

try:
    from .olt_onu_inventory_summary import OltOnuInventoryError, validate_pon_port_selector
except ImportError:
    from olt_onu_inventory_summary import OltOnuInventoryError, validate_pon_port_selector
try:
    from .site_log_window_summary import SiteLogWindowError, resolve_local_site_log_window
except ImportError:
    from site_log_window_summary import SiteLogWindowError, resolve_local_site_log_window

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", PROTOCOL_VERSION}
TOOLS_PER_PAGE = 25
_SAFE_REF = re.compile(r"[0-9a-f]{24}\Z")
_SAFE_MSP_REF = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_SAFE_CURSOR = re.compile(r"0|[1-9][0-9]{0,8}\Z")
_SAFE_OPERATION_ID = re.compile(r"[a-z][a-z0-9_]{0,95}\Z")
_ALLOWED_ORIGIN_HOSTS = {"localhost", "127.0.0.1", "::1"}
_CAPABILITY_SUMMARY_TOOL = {
    "name": "omada_capability_summary",
    "description": (
        "Summarize the connector's in-process partial capability catalog without contacting the controller. "
        "Optionally inspect one exact operation by operation_id. Runtime target references are never returned."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"operation_id": {
            "type": "string", "pattern": "^[a-z][a-z0-9_]{0,95}$",
            "description": "Optional exact operation_id from the connector capability catalog.",
        }},
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_CAPABILITY_SUMMARY_NAME = str(_CAPABILITY_SUMMARY_TOOL["name"])
_DIAGNOSTIC_CAPABILITY_SUMMARY_TOOL = {
    "name": "omada_diagnostic_capability_summary",
    "description": (
        "Summarize existing evidence for complete WLAN and network diagnostic workflows. "
        "Separates source documentation, observed successes, unknown coverage and recorded failures. "
        "Reads the local capability catalog only; it does not contact the controller or probe routes."
    ),
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_DIAGNOSTIC_CAPABILITY_SUMMARY_NAME = str(
    _DIAGNOSTIC_CAPABILITY_SUMMARY_TOOL["name"])
_SITE_CAPABILITY_COMPARISON_TOOL = {
    "name": "omada_compare_site_capabilities",
    "description": (
        "Compare documented Boolean capability flags for 2–16 explicitly selected sites. "
        "Each site reference is refreshed against the current site inventory. Missing values, "
        "permission errors and unavailable sites remain unknown; no discovery probes are run."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"site_refs": {
            "type": "array", "minItems": 2, "maxItems": 16,
            "uniqueItems": True,
            "items": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "description": "Explicit site references returned by the connector's site inventory.",
        }},
        "required": ["site_refs"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_SITE_CAPABILITY_COMPARISON_NAME = str(_SITE_CAPABILITY_COMPARISON_TOOL["name"])
_INCIDENT_REPORT_COMPARISON_TOOL = {
    "name": "omada_compare_incident_reports",
    "description": (
        "Compare 2–8 existing redacted site-outage report documents. The operation does not "
        "contact the controller. It compares event and alert totals only for identical time "
        "windows and complete reports, exposes gaps and unsupported report schemas, and omits "
        "all report text, identifiers, names and raw observations."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"reports": {
            "type": "array", "minItems": 2, "maxItems": 8,
            "items": {"type": "object"},
            "description": "Existing redacted JSON reports produced by the site outage report workflow.",
        }},
        "required": ["reports"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_INCIDENT_REPORT_COMPARISON_NAME = str(_INCIDENT_REPORT_COMPARISON_TOOL["name"])
_CHANGE_JOURNAL_SUMMARY_TOOL = {
    "name": "omada_change_journal_summary",
    "description": (
        "Summarize status counts from the connector's already-bound local change journal. "
        "Returns no plan identifiers, target references, before/after settings, or credentials; it does not "
        "open caller-selected paths, contact the controller, or change journal state."
    ),
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_CHANGE_JOURNAL_SUMMARY_NAME = str(_CHANGE_JOURNAL_SUMMARY_TOOL["name"])
_WIFI_DIAGNOSE_TOOL = {
    "name": "omada_wifi_diagnose_site",
    "description": (
        "Run the fixed read-only site WLAN diagnostic. Returns bounded health timeline, "
        "health details, channel overview, client signal distribution, 6-GHz and stored "
        "rogue-AP summaries, plus band-steering, RRM and roaming policy context in one result. "
        "No RF scan or network change is started."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {
                "type": "string",
                "pattern": "^[0-9a-f]{24}$",
                "description": "Opaque site reference returned by the connector's site inventory.",
            },
        },
        "required": ["site_ref"],
        "additionalProperties": False,
    },
    "annotations": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
}
_WIFI_DIAGNOSE_NAME = str(_WIFI_DIAGNOSE_TOOL["name"])
_WIFI_DIAGNOSE_CLIENT_TOOL = {
    "name": "omada_wifi_diagnose_client",
    "description": (
        "Run a fixed read-only site WLAN and client-connectivity diagnostic. Verify a site-bound client_ref "
        "against the current client inventory, then return recent connections, compact summaries of four "
        "event timelines, health timeline and redacted history. Numeric event codes are not interpreted. "
        "No connection, scan or network setting is changed."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                         "description": "Opaque site reference returned by the connector."},
            "client_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                           "description": "Opaque client reference from that site's current inventory."},
        },
        "required": ["site_ref", "client_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_WIFI_DIAGNOSE_CLIENT_NAME = str(_WIFI_DIAGNOSE_CLIENT_TOOL["name"])
_WIFI_DIAGNOSE_AP_TOOL = {
    "name": "omada_wifi_diagnose_ap",
    "description": (
        "Run a fixed read-only site and access-point WLAN diagnostic. Reads existing "
        "AP health, radio configuration, saved RF scan and speed-test results, nearby "
        "WLAN measurements, LAN traffic and wired-downlink counters; it does not "
        "start a scan or change network settings."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                          "description": "Opaque site reference returned by the connector's site inventory."},
            "ap_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                        "description": "Opaque AP reference returned by the selected site's device inventory."},
        },
        "required": ["site_ref", "ap_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_WIFI_DIAGNOSE_AP_NAME = str(_WIFI_DIAGNOSE_AP_TOOL["name"])
_WIFI_COMPARE_APS_TOOL = {
    "name": "omada_wifi_compare_aps",
    "description": (
        "Compare exactly two access points in one site using fixed health, radio, "
        "existing RF scan result, nearby WLAN channel/signal context and LAN counter reads. "
        "Returns compact side-by-side "
        "measurements without a quality ranking or network changes."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                          "description": "Opaque site reference returned by the connector."},
            "ap_ref_a": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                         "description": "First AP reference in the site's device inventory."},
            "ap_ref_b": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                         "description": "Second, distinct AP reference in the site's device inventory."},
        },
        "required": ["site_ref", "ap_ref_a", "ap_ref_b"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_WIFI_COMPARE_APS_NAME = str(_WIFI_COMPARE_APS_TOOL["name"])
_NETWORK_DIAGNOSE_GATEWAY_TOOL = {
    "name": "omada_network_diagnose_gateway",
    "description": (
        "Run a fixed read-only gateway diagnostic using WAN port status and details, "
        "gateway LAN counters and port types, health and its 24-hour score timeline, plus previously saved WAN "
        "speed-test results and WAN capability/online-detection codes. The gateway_ref is checked against "
        "the selected site's fresh device inventory. No test, probe or "
        "configuration change is started."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                          "description": "Opaque site reference returned by the connector."},
            "gateway_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                             "description": "Opaque gateway reference from the selected site's device inventory."},
        },
        "required": ["site_ref", "gateway_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_NETWORK_DIAGNOSE_GATEWAY_NAME = str(_NETWORK_DIAGNOSE_GATEWAY_TOOL["name"])
_NETWORK_DIAGNOSE_SWITCH_TOOL = {
    "name": "omada_network_diagnose_switch",
    "description": (
        "Run a fixed read-only switch diagnostic using 24-hour health and score timeline, SDM category and entry-capacity values, stored cable-test logs and full/incremental results, port state, port counters, PoE, VLAN "
        "membership and LLDP summaries. Verify the switch_ref against the selected site's current inventory. "
        "No port, PoE or network setting is changed."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                         "description": "Opaque site reference returned by the connector."},
            "switch_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                            "description": "Opaque switch reference from that site's current device inventory."},
        },
        "required": ["site_ref", "switch_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_NETWORK_DIAGNOSE_SWITCH_NAME = str(_NETWORK_DIAGNOSE_SWITCH_TOOL["name"])
_NETWORK_OVERVIEW_TOOL = {
    "name": "omada_network_overview",
    "description": (
        "Build a fixed, read-only site network overview from health, device/network counts, "
        "DHCP binding classifications, DNS cache/proxy flags, LAN DNS record types and "
        "event/alert counts by module and severity, and bounded current topology. Names, "
        "addresses, event details and record values are omitted; no "
        "tests or settings changes are made."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                                      "description": "Opaque site reference returned by the connector."}},
        "required": ["site_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_NETWORK_OVERVIEW_NAME = str(_NETWORK_OVERVIEW_TOOL["name"])
_SITE_OUTAGE_SUMMARY_TOOL = {
    "name": "omada_site_outage_summary",
    "description": (
        "Summarize event and alert counts for one UTC time window alongside the current AP, "
        "gateway and switch reachability snapshot. The snapshot is timestamped separately; "
        "events are not assigned to individual devices and no outage cause is inferred."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                          "description": "Opaque site reference returned by the connector."},
            "start_ms": {"type": "integer", "minimum": 946684800000,
                         "maximum": 4102444800000},
            "end_ms": {"type": "integer", "minimum": 946684800000,
                       "maximum": 4102444800000},
        },
        "required": ["site_ref", "start_ms", "end_ms"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_SITE_OUTAGE_SUMMARY_NAME = str(_SITE_OUTAGE_SUMMARY_TOOL["name"])
_SITE_CLIENT_OUTAGE_OVERLAP_TOOL = {
    "name": "omada_site_client_outage_overlap_summary",
    "description": (
        "Compare documented wireless disconnect/connect events for 2–16 explicitly selected clients "
        "in one site and one UTC window of up to 24 hours. Counts only closed intervals whose "
        "documented AP mapping is known and whose time ranges overlap for distinct clients on the "
        "same AP. Unknown AP mappings, open intervals and source gaps remain separate. No client "
        "identifiers or connection cause are returned; this read-only report starts no scan."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "client_refs": {"type": "array", "minItems": 2, "maxItems": 16,
                            "uniqueItems": True,
                            "items": {"type": "string", "pattern": "^[0-9a-f]{24}$"}},
            "start_ms": {"type": "integer", "minimum": 946684800000,
                         "maximum": 4102444800000},
            "end_ms": {"type": "integer", "minimum": 946684800000,
                       "maximum": 4102444800000},
        },
        "required": ["site_ref", "client_refs", "start_ms", "end_ms"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_SITE_CLIENT_OUTAGE_OVERLAP_NAME = str(_SITE_CLIENT_OUTAGE_OVERLAP_TOOL["name"])
_SITE_CLIENT_ROAMING_BACKTRACK_TOOL = {
    "name": "omada_site_client_roaming_backtrack_summary",
    "description": (
        "Summarize reciprocal roaming sequences (AP A to B, then B to A) for 1–16 explicitly "
        "selected clients in one site and one UTC window of up to 24 hours. Compare roaming, "
        "disconnect and connect timelines to distinguish a return roam from a full separation or "
        "an event gap. AP references must bind to current site inventory. It returns pair counts and "
        "coverage without client identities or inferred cause. "
        "Read-only; no scan or network change is started."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "client_refs": {"type": "array", "minItems": 1, "maxItems": 16,
                            "uniqueItems": True,
                            "items": {"type": "string", "pattern": "^[0-9a-f]{24}$"}},
            "start_ms": {"type": "integer", "minimum": 946684800000,
                         "maximum": 4102444800000},
            "end_ms": {"type": "integer", "minimum": 946684800000,
                       "maximum": 4102444800000},
        },
        "required": ["site_ref", "client_refs", "start_ms", "end_ms"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_SITE_CLIENT_ROAMING_BACKTRACK_NAME = str(_SITE_CLIENT_ROAMING_BACKTRACK_TOOL["name"])
_SITE_AP_UPLINK_PATH_TOOL = {
    "name": "omada_site_ap_uplink_path_summary",
    "description": (
        "Summarize wired and mesh uplink evidence for 1–16 explicitly selected APs in one site. "
        "Joins current inventory references with documented wired-uplink and mesh reads, reports "
        "the mapped next hop when known, and keeps unknown path segments, unavailable sources, "
        "nonzero link counters and documented device-state concerns visible. It does not infer "
        "unobserved path segments or start scans or network changes. Read-only."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "device_refs": {"type": "array", "minItems": 1, "maxItems": 16,
                            "uniqueItems": True,
                            "items": {"type": "string", "pattern": "^[0-9a-f]{24}$"}},
        },
        "required": ["site_ref", "device_refs"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_SITE_AP_UPLINK_PATH_NAME = str(_SITE_AP_UPLINK_PATH_TOOL["name"])
_SITE_CHANNEL_REUSE_TOOL = {
    "name": "omada_site_channel_reuse_summary",
    "description": (
        "Compare currently reported AP channels, reported bandwidth and matching existing channel-load "
        "values for 1–16 explicitly selected APs. Groups only identical reported channels within a band; "
        "adjacent-channel overlap is left unknown because occupied channel ranges are not documented. "
        "Load values do not establish interference or its cause. Read-only; starts no scan."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "device_refs": {"type": "array", "minItems": 1, "maxItems": 16,
                            "uniqueItems": True,
                            "items": {"type": "string", "pattern": "^[0-9a-f]{24}$"}},
        },
        "required": ["site_ref", "device_refs"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_SITE_CHANNEL_REUSE_NAME = str(_SITE_CHANNEL_REUSE_TOOL["name"])
_SSID_NETWORK_SUMMARY_TOOL = {
    "name": "omada_ssid_network_summary",
    "description": (
        "Reconcile bounded site SSID bindings with the LAN inventory and summarize available per-network VLAN "
        "and DHCP-pool evidence, site-wide DNS settings and bounded gateway inventory details. Returns safe "
        "counts without names or references; DNS-to-WLAN and gateway-to-network associations stay unknown "
        "where the source projections do not expose a link. Read-only; makes no network changes."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$",
                                      "description": "Opaque site reference returned by the connector."}},
        "required": ["site_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_SSID_NETWORK_SUMMARY_NAME = str(_SSID_NETWORK_SUMMARY_TOOL["name"])
_GATEWAY_WAN_INCIDENT_WINDOW_TOOL = {
    "name": "omada_gateway_wan_incident_window",
    "description": (
        "Summarize one gateway's current WAN status codes and saved health observations for a UTC window. "
        "The report separates current status from historical time-stamped data, keeps unknown codes "
        "undecoded, and marks incident counts and saved speed tests without reliable timestamps as "
        "unplaced. Load-balancing participation and outage cause remain unknown."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "gateway_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "start_ms": {"type": "integer", "minimum": 946684800000,
                         "maximum": 4102444800000},
            "end_ms": {"type": "integer", "minimum": 946684800000,
                       "maximum": 4102444800000},
        },
        "required": ["site_ref", "gateway_ref", "start_ms", "end_ms"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_GATEWAY_WAN_INCIDENT_WINDOW_NAME = str(_GATEWAY_WAN_INCIDENT_WINDOW_TOOL["name"])
_SITE_DHCP_POOL_UTILIZATION_TOOL = {
    "name": "omada_site_dhcp_pool_utilization",
    "description": (
        "Summarize documented IPv4 DHCP pool capacity and available-address counts by network, with "
        "dynamic/static lease counts kept separate. Pool boundaries, network names, client addresses "
        "and hardware identifiers are omitted. Lease membership in pool ranges is not exposed by the "
        "source, so leases are not used to calculate occupancy. A network is marked depleted only "
        "when complete documented range and available-address data report zero addresses remaining."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"}},
        "required": ["site_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_SITE_DHCP_POOL_UTILIZATION_NAME = str(_SITE_DHCP_POOL_UTILIZATION_TOOL["name"])
_SITE_AP_QUALITY_WINDOW_TOOL = {
    "name": "omada_site_ap_quality_window",
    "description": (
        "Compare the last 24 hours of existing AP health-score and retry/drop samples, with current "
        "radio settings, for up to 32 inventoried access points. Results use separate source windows; "
        "the source does not map retry/drop values to bands or define their numeric scale. Missing "
        "rows mean not listed, not zero. This read-only report does not run a scan."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"}},
        "required": ["site_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_SITE_AP_QUALITY_WINDOW_NAME = str(_SITE_AP_QUALITY_WINDOW_TOOL["name"])
_SITE_FIRMWARE_SUMMARY_TOOL = {
    "name": "omada_site_firmware_summary",
    "description": (
        "Group current and latest firmware versions for up to 64 devices in one site by type and model. "
        "A differing version string is not ordered or treated as proof that an update is available. "
        "This read-only tool never starts a firmware upgrade."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"}},
        "required": ["site_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}
_SITE_FIRMWARE_SUMMARY_NAME = str(_SITE_FIRMWARE_SUMMARY_TOOL["name"])
_SITE_SWITCH_PORT_ANOMALY_SUMMARY_TOOL = {
    "name": "omada_site_switch_port_anomaly_summary",
    "description": (
        "Compare current switch port status codes with cumulative transmit/receive error counters "
        "for up to 32 inventoried switches. Nonzero counters are review signals, not fault diagnoses. "
        "Status codes remain uninterpreted. The available port counter schema does not provide "
        "drop counts; one snapshot cannot establish a rate or trend. Field-level schemas are specific "
        "only in the ER7212PC export; live support remains unknown."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"}},
        "required": ["site_ref"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
}
_SITE_SWITCH_PORT_ANOMALY_SUMMARY_NAME = str(_SITE_SWITCH_PORT_ANOMALY_SUMMARY_TOOL["name"])
_SWITCH_CABLE_TEST_TOOL = {
    "name": "omada_switch_cable_test",
    "description": (
        "Manage one bounded switch cable-test plan. Preview and status are safe reads. "
        "Start and cancel require the connector's exact short-lived operator approval; "
        "the preview must be inspected and the signed approval supplied. No retry is made."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["preview", "status", "cancel_preview", "apply", "cancel_apply"]},
            "site_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "switch_ref": {"type": "string", "pattern": "^[0-9a-f]{24}$"},
            "port": {"type": "integer", "minimum": 1, "maximum": 4096},
            "disruption_confirmed": {"type": "boolean"},
            "plan_id": {"type": "string", "pattern": "^[0-9a-f]{48}$"},
            "approval": {"type": "object"},
        },
        "required": ["action"], "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": True,
                     "idempotentHint": False, "openWorldHint": False},
}
_SWITCH_CABLE_TEST_NAME = str(_SWITCH_CABLE_TEST_TOOL["name"])
_CONTROLLER_RADIUS_PROXY_CHANGE_TOOL = {
    "name": "omada_controller_radius_proxy_change",
    "description": (
        "Prepare a limited controller RADIUS proxy setting change or apply it with the "
        "exact short-lived one-time approval returned in the preview. The change is "
        "journaled, state-checked and read back; configuration changes may interrupt "
        "RADIUS authentication. Writes must be explicitly enabled by the operator."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["preview", "apply"]},
            "changes": {"type": "object", "properties": {
                "enable": {"type": "boolean"},
                "port": {"type": "integer", "minimum": -2147483648,
                          "maximum": 2147483647},
                "requireMessageAuthenticator": {"type": "boolean"},
                "limitProxyState": {"type": "boolean"},
            }, "additionalProperties": False},
            "plan_id": {"type": "string", "pattern": "^[0-9a-f]{48}$"},
            "approval": {"type": "object"},
        },
        "required": ["action"], "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": True,
                     "idempotentHint": False, "openWorldHint": False},
}
_CONTROLLER_RADIUS_PROXY_CHANGE_NAME = str(_CONTROLLER_RADIUS_PROXY_CHANGE_TOOL["name"])


class McpRequestError(ValueError):
    """A rejected MCP request with a stable code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _rpc_error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _origin_allowed(origin: str | None) -> bool:
    if origin is None:
        return True
    try:
        parts = urlsplit(origin)
        # Accessing .port also rejects malformed/out-of-range port values.
        _ = parts.port
    except ValueError:
        return False
    return (parts.scheme in {"http", "https"} and parts.hostname in _ALLOWED_ORIGIN_HOSTS
            and parts.username is None and parts.password is None
            and parts.path == "" and not parts.query and not parts.fragment)


def _tool(operation: Any) -> dict[str, object]:
    properties: dict[str, object] = {}
    required: list[str] = []
    for name in re.findall(r"\{([a-z][a-z0-9_]*)\}", operation.public_template):
        if name not in {"site_ref", "history_ref", "incident_ref", "device_ref", "gateway_ref", "switch_ref", "client_ref", "ssid_ref", "wlan_group_ref", "network_ref", "wan_port_ref", "site_template_ref", "msp_ref", "customer_ref", "family_id", "application_id"}:
            if name != "port":
                continue
        if name == "port":
            properties[name] = {"type": "integer", "minimum": 0, "maximum": 4096,
                                "description": "Switch port index accepted by the controller API (0–4096)."}
            required.append(name)
            continue
        properties[name] = {
            "type": "string",
            "pattern": ("^[A-Za-z0-9_-]{1,128}$" if name in {"msp_ref", "customer_ref"} else
                        "^(?:0|[1-9][0-9]{0,9})$" if name == "family_id" else
                        "^[A-Za-z0-9_-]{1,64}$" if name == "application_id" else
                        "^[0-9a-f]{24}$"),
            "description": ("Opaque site reference returned by the connector's site inventory."
                            if name == "site_ref" else
                            "MSP identifier supplied by the caller using safe path characters."
                            if name == "msp_ref" else
                            "Customer identifier supplied by the caller using safe path characters."
                            if name == "customer_ref" else
                            "Numeric category ID returned in the selected site's application-category summary."
                            if name == "family_id" else
                            "Application ID from the caller, restricted to safe path characters."
                            if name == "application_id" else
                            "Opaque incident reference returned by the selected site's latest device incident list."
                            if name == "incident_ref" else
                            "Opaque device reference returned by the selected site's device inventory."
                            if name == "device_ref" and operation.operation_id == "device_health_incidents" else
                            "Opaque access point reference returned by the selected site's device inventory."
                            if name == "device_ref" else
                            "Opaque gateway reference returned by the selected site's device inventory."
                            if name == "gateway_ref" else
                            "Opaque switch reference returned by the selected site's device inventory."
                            if name == "switch_ref" else
                            "Opaque client reference returned by a fresh inventory for the selected site."
                            if name == "client_ref" else
                            "Opaque WLAN group reference returned by the selected site's wireless group inventory."
                            if name == "wlan_group_ref" else
                            "Opaque SSID reference returned by the selected site's wireless-network inventory."
                            if name == "ssid_ref" else
                            "Opaque network reference returned by the selected site's network inventory."
                            if name == "network_ref" else
                            "Opaque site-template reference returned by the site-template inventory."
                            if name == "site_template_ref" else
                            "Opaque history reference returned by the planning history read."),
        }
        required.append(name)
    for name in getattr(operation, "extra_arguments", ()):
        if name == "pon_port":
            properties[name] = {
                "type": "string",
                "pattern": "^GPON [1-9][0-9]{0,2}/[1-9][0-9]{0,2}/[1-9][0-9]{0,2}(?:-[1-9][0-9]{0,2})?(?:,GPON [1-9][0-9]{0,2}/[1-9][0-9]{0,2}/[1-9][0-9]{0,2}(?:-[1-9][0-9]{0,2})?)*$",
                "description": "Required ONU inventory PON selector from the documented GPON port syntax.",
            }
            required.append(name)
        elif name == "page_number":
            properties[name] = {"type": "integer", "minimum": 0, "maximum": 10000,
                                "description": "Zero-based page number for a bounded paginated read."}
            required.append(name)
        elif name == "page_size":
            properties[name] = {"type": "integer", "minimum": 1, "maximum": 100,
                                "description": "Page size, capped at 100 rows."}
            required.append(name)
        elif name == "vpn_type":
            if operation.operation_id == "site_vpn_server_status_summary":
                properties[name] = {"type": "integer", "enum": list(range(6)),
                                    "description": "VPN protocol: 0 L2TP, 1 PPTP, 2 IPsec, 3 OpenVPN, 4 WireGuard, 5 SSL VPN."}
            elif operation.operation_id == "site_vpn_client_status_summary":
                properties[name] = {"type": "integer", "enum": [0, 1, 3, 4],
                                    "description": "VPN protocol: 0 L2TP, 1 PPTP, 3 OpenVPN, 4 WireGuard."}
            else:
                properties[name] = {"type": "integer", "enum": [0, 1],
                                    "description": "VPN type: 0 server or 1 client."}
            required.append(name)
        elif name == "function":
            properties[name] = {"type": "integer", "enum": list(range(16)),
                                "description": "Documented WAN-port query function code (0–15)."}
            required.append(name)
    base_local = tuple(getattr(operation, "local_arguments", ()))
    alternatives = tuple(getattr(operation, "local_argument_alternatives", ()))
    local_names = set(base_local).union(*(set(group) for group in alternatives))
    for name in local_names:
        if name in {"client_name", "ssid_name"}:
            properties[name] = {
                "type": "string", "minLength": 1, "maxLength": 128,
                "description": ("Exact client name, host name, or model to match in memory."
                                if name == "client_name" else
                                "Exact current SSID name to match in memory."),
            }
        elif name in {"start_ms", "end_ms"}:
            properties[name] = {
                "type": "integer", "minimum": 946684800000, "maximum": 4102444800000,
                "description": "UTC epoch milliseconds; both bounds are required and the window is capped at 24 hours.",
            }
        elif name in {"start_local", "end_local"}:
            properties[name] = {
                "type": "string", "minLength": 16, "maxLength": 23,
                "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,3})?)?$",
                "description": "Local wall time in the supplied IANA time_zone, without an offset.",
            }
        elif name == "time_zone":
            properties[name] = {
                "type": "string", "minLength": 1, "maxLength": 64,
                "pattern": r"^[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*$",
                "description": "IANA time zone used to convert the local bounds to UTC.",
            }
        elif name == "archived":
            properties[name] = {
                "type": "boolean",
                "description": "Include archived threat records; false returns active records only.",
            }
        elif name == "vlan_id":
            properties[name] = {
                "type": "integer", "minimum": 1, "maximum": 4094,
                "description": "VLAN ID selected for the site-bound summary.",
            }
        elif name == "type" and operation.operation_id == "site_mac_auth_ssid_inventory":
            properties[name] = {
                "type": "integer", "enum": [1, 2, 3],
                "description": "Device type: 1 access points, 2 wireless routers, 3 both.",
            }
        elif name == "device_type" and operation.operation_id == "site_routing_table_summary":
            properties[name] = {
                "type": "string", "enum": ["gateway", "switch"],
                "description": "Documented route table scope.",
            }
        if not alternatives:
            required.append(name)
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    if alternatives:
        groups = (base_local, *alternatives)
        branches = []
        for group in groups:
            other_groups = [other for other in groups if other != group]
            branch: dict[str, object] = {"required": list(group)}
            if other_groups:
                branch["not"] = {"anyOf": [{"required": list(other)} for other in other_groups]}
            branches.append(branch)
        input_schema["oneOf"] = branches
    return {
        "name": f"omada_{operation.operation_id}",
        "description": f"Read-only connector operation: {operation.operation_id}.",
        "inputSchema": input_schema,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }


def _tools_page(registry: Any, cursor: object) -> dict[str, object]:
    offset = 0
    if cursor is not None:
        if not isinstance(cursor, str) or not _SAFE_CURSOR.fullmatch(cursor):
            raise McpRequestError("cursor_invalid")
        offset = int(cursor)
    tools = [_tool(item) for item in registry.entries]
    tools.append(_WIFI_DIAGNOSE_TOOL)
    tools.append(_WIFI_DIAGNOSE_CLIENT_TOOL)
    tools.append(_WIFI_DIAGNOSE_AP_TOOL)
    tools.append(_WIFI_COMPARE_APS_TOOL)
    tools.append(_NETWORK_DIAGNOSE_GATEWAY_TOOL)
    tools.append(_NETWORK_DIAGNOSE_SWITCH_TOOL)
    tools.append(_NETWORK_OVERVIEW_TOOL)
    tools.append(_SITE_OUTAGE_SUMMARY_TOOL)
    tools.append(_SITE_CLIENT_OUTAGE_OVERLAP_TOOL)
    tools.append(_SITE_CLIENT_ROAMING_BACKTRACK_TOOL)
    tools.append(_SITE_AP_UPLINK_PATH_TOOL)
    tools.append(_SITE_CHANNEL_REUSE_TOOL)
    tools.append(_SSID_NETWORK_SUMMARY_TOOL)
    tools.append(_GATEWAY_WAN_INCIDENT_WINDOW_TOOL)
    tools.append(_SITE_DHCP_POOL_UTILIZATION_TOOL)
    tools.append(_SITE_AP_QUALITY_WINDOW_TOOL)
    tools.append(_SITE_FIRMWARE_SUMMARY_TOOL)
    tools.append(_SITE_SWITCH_PORT_ANOMALY_SUMMARY_TOOL)
    tools.append(_DIAGNOSTIC_CAPABILITY_SUMMARY_TOOL)
    tools.append(_SITE_CAPABILITY_COMPARISON_TOOL)
    tools.append(_INCIDENT_REPORT_COMPARISON_TOOL)
    tools.append(_CHANGE_JOURNAL_SUMMARY_TOOL)
    tools.append(_SWITCH_CABLE_TEST_TOOL)
    tools.append(_CONTROLLER_RADIUS_PROXY_CHANGE_TOOL)
    tools.append(_CAPABILITY_SUMMARY_TOOL)
    tools.sort(key=lambda item: str(item["name"]))
    page = tools[offset:offset + TOOLS_PER_PAGE]
    result: dict[str, object] = {"tools": page}
    next_offset = offset + len(page)
    if next_offset < len(tools):
        result["nextCursor"] = str(next_offset)
    return result


def _invoke_tool(registry: Any, name: object, arguments: object,
                 invoke_read: Callable[[str, dict[str, str]], dict[str, object]],
                 invoke_action: Callable[[str, dict[str, object]], dict[str, object]] | None = None) -> dict[str, object]:
    if not isinstance(name, str) or not name.startswith("omada_"):
        raise McpRequestError("tool_unknown")
    if name == _DIAGNOSTIC_CAPABILITY_SUMMARY_NAME:
        if not isinstance(arguments, dict) or arguments:
            raise McpRequestError("arguments_invalid")
        value = invoke_read("diagnostic_capability_summary", {})
        return _tool_result(value)
    if name == _SITE_CAPABILITY_COMPARISON_NAME:
        refs = arguments.get("site_refs") if isinstance(arguments, dict) else None
        if (not isinstance(arguments, dict) or set(arguments) != {"site_refs"} or
                not isinstance(refs, list) or not 2 <= len(refs) <= 16 or
                any(not isinstance(ref, str) or not _SAFE_REF.fullmatch(ref) for ref in refs) or
                len(set(refs)) != len(refs)):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_capability_comparison", {
            "site_refs": ",".join(refs)})
        return _tool_result(value)
    if name == _INCIDENT_REPORT_COMPARISON_NAME:
        reports = arguments.get("reports") if isinstance(arguments, dict) else None
        if not isinstance(arguments, dict) or set(arguments) != {"reports"}:
            raise McpRequestError("arguments_invalid")
        try:
            from .incident_report_comparison import (
                IncidentReportComparisonError, compare_incident_reports,
            )
        except ImportError:
            from incident_report_comparison import (
                IncidentReportComparisonError, compare_incident_reports,
            )
        try:
            value = compare_incident_reports(reports)
        except IncidentReportComparisonError as exc:
            raise McpRequestError("arguments_invalid") from exc
        return _tool_result(value)
    if name == _CHANGE_JOURNAL_SUMMARY_NAME:
        if not isinstance(arguments, dict) or arguments:
            raise McpRequestError("arguments_invalid")
        value = invoke_read("change_journal_summary", {})
        return _tool_result(value)
    if name == _CAPABILITY_SUMMARY_NAME:
        if (not isinstance(arguments, dict) or
                set(arguments) - {"operation_id"} or
                ("operation_id" in arguments and
                 (not isinstance(arguments["operation_id"], str) or
                  not _SAFE_OPERATION_ID.fullmatch(arguments["operation_id"])) )):
            raise McpRequestError("arguments_invalid")
        catalog = invoke_read("capability_catalog", {})
        if catalog.get("status") != "ok" or not isinstance(catalog.get("items"), list):
            return _tool_result({"status": "error", "error": "capability_catalog_unavailable"})
        items = catalog["items"]
        if not all(isinstance(item, dict) for item in items):
            return _tool_result({"status": "error", "error": "capability_catalog_invalid"})
        if "operation_id" in arguments:
            operation_id = arguments["operation_id"]
            matches = [item for item in items if item.get("operation") == operation_id]
            if not matches:
                raise McpRequestError("operation_unknown")
            item = matches[0]
            evidence = item.get("runtime_evidence", [])
            if not isinstance(evidence, list):
                evidence = []
            result = {
                "status": "ok", "catalog_complete": catalog.get("catalog_complete") is True,
                "operation": item.get("operation"), "route": item.get("route"),
                "implementation_state": item.get("implementation_state", "unknown"),
                "support_state": item.get("support_state", "unknown"),
                "runtime_evidence_count": len(evidence),
                "controller_response_evidence_count": sum(
                    entry.get("controller_response_observed") is True
                    for entry in evidence if isinstance(entry, dict)),
                "observed_response_shape_states": _evidence_counts(
                    evidence, "response_shape_state"),
                "observed_support_states": _evidence_counts(evidence, "support_state"),
                "observed_permission_states": _evidence_counts(evidence, "permission_state"),
            }
        else:
            result = {
                "status": "ok", "catalog_scope": catalog.get("catalog_scope"),
                "catalog_complete": catalog.get("catalog_complete") is True,
                "operation_count": len(items),
                "operations_with_runtime_evidence": sum(
                    bool(item.get("runtime_evidence")) for item in items),
                "operations_with_controller_responses": sum(
                    item.get("controller_response_evidence_count", 0) > 0
                    for item in items if type(item.get("controller_response_evidence_count", 0)) is int),
                "support_state_counts": _item_counts(items, "support_state"),
                "implementation_state_counts": _item_counts(items, "implementation_state"),
            }
        return _tool_result(result)
    if name == _SWITCH_CABLE_TEST_NAME:
        if not isinstance(arguments, dict) or not isinstance(arguments.get("action"), str):
            raise McpRequestError("arguments_invalid")
        action = arguments["action"]
        allowed = {
            "preview": {"action", "site_ref", "switch_ref", "port", "disruption_confirmed"},
            "status": {"action", "plan_id"},
            "cancel_preview": {"action", "plan_id", "disruption_confirmed"},
            "apply": {"action", "plan_id", "approval"},
            "cancel_apply": {"action", "plan_id", "approval"},
        }
        if action not in allowed or set(arguments) != allowed[action]:
            raise McpRequestError("arguments_invalid")
        if action == "preview":
            if (any(not isinstance(arguments.get(k), str) or not _SAFE_REF.fullmatch(arguments[k])
                    for k in ("site_ref", "switch_ref")) or
                    type(arguments.get("port")) is not int or not 1 <= arguments["port"] <= 4096 or
                    type(arguments.get("disruption_confirmed")) is not bool):
                raise McpRequestError("arguments_invalid")
        else:
            if not isinstance(arguments.get("plan_id"), str) or not re.fullmatch(r"[0-9a-f]{48}", arguments["plan_id"]):
                raise McpRequestError("arguments_invalid")
            if action == "cancel_preview" and arguments.get("disruption_confirmed") is not True:
                raise McpRequestError("arguments_invalid")
            if action in {"apply", "cancel_apply"}:
                token = arguments.get("approval")
                token_keys = {"version", "operation", "plan_id", "plan_digest", "operator_id",
                              "expires_at", "nonce", "signature"}
                if (not isinstance(token, dict) or set(token) != token_keys or
                        type(token.get("version")) is not int or token.get("version") != 1 or
                        token.get("plan_id") != arguments["plan_id"] or
                        not isinstance(token.get("plan_digest"), str) or
                        not re.fullmatch(r"[0-9a-f]{64}", token["plan_digest"]) or
                        not isinstance(token.get("operator_id"), str) or
                        not re.fullmatch(r"op_[0-9a-f]{24}", token["operator_id"]) or
                        type(token.get("expires_at")) is not int or
                        not isinstance(token.get("nonce"), str) or
                        not re.fullmatch(r"[0-9a-f]{32}", token["nonce"]) or
                        not isinstance(token.get("signature"), str) or
                        not re.fullmatch(r"[0-9a-f]{64}", token["signature"])):
                    raise McpRequestError("arguments_invalid")
        if invoke_action is None:
            raise McpRequestError("action_unavailable")
        return _tool_result(invoke_action(action, arguments))
    if name == _CONTROLLER_RADIUS_PROXY_CHANGE_NAME:
        if not isinstance(arguments, dict) or not isinstance(arguments.get("action"), str):
            raise McpRequestError("arguments_invalid")
        action = arguments["action"]
        if action == "preview":
            changes = arguments.get("changes")
            allowed = {"enable", "port", "requireMessageAuthenticator", "limitProxyState"}
            if (set(arguments) != {"action", "changes"} or not isinstance(changes, dict) or
                    not changes or set(changes) - allowed or
                    any(type(value) is not int if key == "port" else type(value) is not bool
                        for key, value in changes.items()) or
                    ("port" in changes and not -2147483648 <= changes["port"] <= 2147483647)):
                raise McpRequestError("arguments_invalid")
            action_name = "controller_radius_proxy_preview"
        elif action == "apply":
            if (set(arguments) != {"action", "plan_id", "approval"} or
                    not isinstance(arguments.get("plan_id"), str) or
                    not re.fullmatch(r"[0-9a-f]{48}", arguments["plan_id"])):
                raise McpRequestError("arguments_invalid")
            token = arguments.get("approval")
            token_keys = {"version", "operation", "plan_id", "plan_digest", "operator_id",
                          "expires_at", "nonce", "signature"}
            if (not isinstance(token, dict) or set(token) != token_keys or
                    type(token.get("version")) is not int or token.get("version") != 1 or
                    token.get("operation") != "controller-radius-proxy" or
                    token.get("plan_id") != arguments["plan_id"] or
                    not isinstance(token.get("plan_digest"), str) or
                    not re.fullmatch(r"[0-9a-f]{64}", token["plan_digest"]) or
                    not isinstance(token.get("operator_id"), str) or
                    not re.fullmatch(r"op_[0-9a-f]{24}", token["operator_id"]) or
                    type(token.get("expires_at")) is not int or
                    not isinstance(token.get("nonce"), str) or
                    not re.fullmatch(r"[0-9a-f]{32}", token["nonce"]) or
                    not isinstance(token.get("signature"), str) or
                    not re.fullmatch(r"[0-9a-f]{64}", token["signature"])):
                raise McpRequestError("arguments_invalid")
            action_name = "controller_radius_proxy_apply"
        else:
            raise McpRequestError("arguments_invalid")
        if invoke_action is None:
            raise McpRequestError("action_unavailable")
        return _tool_result(invoke_action(action_name, arguments))
    if name == _WIFI_DIAGNOSE_NAME:
        if (not isinstance(arguments, dict) or set(arguments) != {"site_ref"} or
                not isinstance(arguments["site_ref"], str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"])
        ):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("wifi_diagnose_site", {"site_ref": arguments["site_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _WIFI_DIAGNOSE_CLIENT_NAME:
        keys = ("site_ref", "client_ref")
        if (not isinstance(arguments, dict) or set(arguments) != set(keys) or
                any(not isinstance(arguments[key], str) or not _SAFE_REF.fullmatch(arguments[key])
                    for key in keys)):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("wifi_diagnose_client", {
            "site_ref": arguments["site_ref"], "client_ref": arguments["client_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _WIFI_DIAGNOSE_AP_NAME:
        if (not isinstance(arguments, dict) or set(arguments) != {"site_ref", "ap_ref"} or
                any(not isinstance(arguments[key], str) or not _SAFE_REF.fullmatch(arguments[key])
                    for key in ("site_ref", "ap_ref"))):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("wifi_diagnose_ap", {
            "site_ref": arguments["site_ref"], "ap_ref": arguments["ap_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _WIFI_COMPARE_APS_NAME:
        keys = ("site_ref", "ap_ref_a", "ap_ref_b")
        if (not isinstance(arguments, dict) or set(arguments) != set(keys) or
                any(not isinstance(arguments[key], str) or not _SAFE_REF.fullmatch(arguments[key])
                    for key in keys)):
            raise McpRequestError("arguments_invalid")
        if arguments["ap_ref_a"] == arguments["ap_ref_b"]:
            raise McpRequestError("arguments_invalid")
        value = invoke_read("wifi_compare_aps", {
            "site_ref": arguments["site_ref"], "ap_ref_a": arguments["ap_ref_a"],
            "ap_ref_b": arguments["ap_ref_b"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _NETWORK_DIAGNOSE_GATEWAY_NAME:
        keys = ("site_ref", "gateway_ref")
        if (not isinstance(arguments, dict) or set(arguments) != set(keys) or
                any(not isinstance(arguments[key], str) or not _SAFE_REF.fullmatch(arguments[key])
                    for key in keys)):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("network_diagnose_gateway", {
            "site_ref": arguments["site_ref"],
            "gateway_ref": arguments["gateway_ref"],
        })
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _NETWORK_DIAGNOSE_SWITCH_NAME:
        keys = ("site_ref", "switch_ref")
        if (not isinstance(arguments, dict) or set(arguments) != set(keys) or
                any(not isinstance(arguments[key], str) or not _SAFE_REF.fullmatch(arguments[key])
                    for key in keys)):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("network_diagnose_switch", {
            "site_ref": arguments["site_ref"], "switch_ref": arguments["switch_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _NETWORK_OVERVIEW_NAME:
        keys = ("site_ref",)
        if (not isinstance(arguments, dict) or set(arguments) != set(keys) or
                any(not isinstance(arguments[key], str) or not _SAFE_REF.fullmatch(arguments[key])
                    for key in keys)):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("network_overview", {"site_ref": arguments["site_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _SITE_OUTAGE_SUMMARY_NAME:
        keys = ("site_ref", "start_ms", "end_ms")
        if (not isinstance(arguments, dict) or set(arguments) != set(keys) or
                not isinstance(arguments.get("site_ref"), str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"]) or
                type(arguments.get("start_ms")) is not int or
                type(arguments.get("end_ms")) is not int):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_outage_summary", {
            "site_ref": arguments["site_ref"],
            "start_ms": str(arguments["start_ms"]),
            "end_ms": str(arguments["end_ms"]),
        })
        return _tool_result(value)
    if name == _SITE_CLIENT_OUTAGE_OVERLAP_NAME:
        keys = {"site_ref", "client_refs", "start_ms", "end_ms"}
        refs = arguments.get("client_refs") if isinstance(arguments, dict) else None
        if (not isinstance(arguments, dict) or set(arguments) != keys or
                not isinstance(arguments.get("site_ref"), str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"]) or
                not isinstance(refs, list) or not 2 <= len(refs) <= 16 or
                any(not isinstance(ref, str) or not _SAFE_REF.fullmatch(ref) for ref in refs) or
                len(set(refs)) != len(refs) or
                type(arguments.get("start_ms")) is not int or
                type(arguments.get("end_ms")) is not int):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_client_outage_overlap_summary", {
            "site_ref": arguments["site_ref"], "client_refs": ",".join(refs),
            "start_ms": str(arguments["start_ms"]), "end_ms": str(arguments["end_ms"])})
        return _tool_result(value)
    if name == _SITE_CLIENT_ROAMING_BACKTRACK_NAME:
        keys = {"site_ref", "client_refs", "start_ms", "end_ms"}
        refs = arguments.get("client_refs") if isinstance(arguments, dict) else None
        if (not isinstance(arguments, dict) or set(arguments) != keys or
                not isinstance(arguments.get("site_ref"), str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"]) or
                not isinstance(refs, list) or not 1 <= len(refs) <= 16 or
                any(not isinstance(ref, str) or not _SAFE_REF.fullmatch(ref) for ref in refs) or
                len(set(refs)) != len(refs) or
                type(arguments.get("start_ms")) is not int or
                type(arguments.get("end_ms")) is not int):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_client_roaming_backtrack_summary", {
            "site_ref": arguments["site_ref"], "client_refs": ",".join(refs),
            "start_ms": str(arguments["start_ms"]), "end_ms": str(arguments["end_ms"])})
        return _tool_result(value)
    if name == _SITE_AP_UPLINK_PATH_NAME:
        keys = {"site_ref", "device_refs"}
        refs = arguments.get("device_refs") if isinstance(arguments, dict) else None
        if (not isinstance(arguments, dict) or set(arguments) != keys or
                not isinstance(arguments.get("site_ref"), str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"]) or
                not isinstance(refs, list) or not 1 <= len(refs) <= 16 or
                any(not isinstance(ref, str) or not _SAFE_REF.fullmatch(ref) for ref in refs) or
                len(set(refs)) != len(refs)):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_ap_uplink_path_summary", {
            "site_ref": arguments["site_ref"], "device_refs": ",".join(refs)})
        return _tool_result(value)
    if name == _SITE_CHANNEL_REUSE_NAME:
        keys = {"site_ref", "device_refs"}
        refs = arguments.get("device_refs") if isinstance(arguments, dict) else None
        if (not isinstance(arguments, dict) or set(arguments) != keys or
                not isinstance(arguments.get("site_ref"), str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"]) or
                not isinstance(refs, list) or not 1 <= len(refs) <= 16 or
                any(not isinstance(ref, str) or not _SAFE_REF.fullmatch(ref) for ref in refs) or
                len(set(refs)) != len(refs)):
            raise McpRequestError("arguments_invalid")
        return _tool_result(invoke_read("site_channel_reuse_summary", {
            "site_ref": arguments["site_ref"], "device_refs": ",".join(refs)}))
    if name == _SSID_NETWORK_SUMMARY_NAME:
        keys = ("site_ref",)
        if (not isinstance(arguments, dict) or set(arguments) != set(keys) or
                any(not isinstance(arguments[key], str) or not _SAFE_REF.fullmatch(arguments[key])
                    for key in keys)):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("ssid_network_summary", {"site_ref": arguments["site_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _GATEWAY_WAN_INCIDENT_WINDOW_NAME:
        keys = ("site_ref", "gateway_ref", "start_ms", "end_ms")
        if (not isinstance(arguments, dict) or set(arguments) != set(keys) or
                any(not isinstance(arguments[key], str) or not _SAFE_REF.fullmatch(arguments[key])
                    for key in ("site_ref", "gateway_ref")) or
                any(type(arguments[key]) is not int for key in ("start_ms", "end_ms"))):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("gateway_wan_incident_window", {
            "site_ref": arguments["site_ref"], "gateway_ref": arguments["gateway_ref"],
            "start_ms": str(arguments["start_ms"]), "end_ms": str(arguments["end_ms"])})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _SITE_DHCP_POOL_UTILIZATION_NAME:
        if (not isinstance(arguments, dict) or set(arguments) != {"site_ref"} or
                not isinstance(arguments["site_ref"], str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"])):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_dhcp_pool_utilization", {
            "site_ref": arguments["site_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _SITE_AP_QUALITY_WINDOW_NAME:
        if (not isinstance(arguments, dict) or set(arguments) != {"site_ref"} or
                not isinstance(arguments["site_ref"], str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"])):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_ap_quality_window", {"site_ref": arguments["site_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _SITE_FIRMWARE_SUMMARY_NAME:
        if (not isinstance(arguments, dict) or set(arguments) != {"site_ref"} or
                not isinstance(arguments["site_ref"], str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"])):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_firmware_summary", {"site_ref": arguments["site_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    if name == _SITE_SWITCH_PORT_ANOMALY_SUMMARY_NAME:
        if (not isinstance(arguments, dict) or set(arguments) != {"site_ref"} or
                not isinstance(arguments["site_ref"], str) or
                not _SAFE_REF.fullmatch(arguments["site_ref"])):
            raise McpRequestError("arguments_invalid")
        value = invoke_read("site_switch_port_anomaly_summary", {"site_ref": arguments["site_ref"]})
        return {
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                                separators=(",", ":"))}],
            "structuredContent": value,
            "isError": value.get("status") == "error",
        }
    operation_id = name.removeprefix("omada_")
    try:
        operation = registry.get(operation_id)
    except (KeyError, ValueError) as exc:
        raise McpRequestError("tool_unknown") from exc
    if (operation.public_method != "GET" or
            (operation.upstream_method != "GET" and
             not (operation.operation_id == "site_batch_interference_status_summary" and
                  operation.upstream_method == "POST"))):
        raise McpRequestError("tool_not_read_only")
    if not isinstance(arguments, dict):
        raise McpRequestError("arguments_invalid")
    expected = set(re.findall(r"\{([a-z][a-z0-9_]*)\}", operation.public_template))
    extra = set(getattr(operation, "extra_arguments", ()))
    local = set(getattr(operation, "local_arguments", ()))
    alternatives = tuple(getattr(operation, "local_argument_alternatives", ()))
    local_sets = (local, *(set(group) for group in alternatives))
    local_names = set().union(*local_sets)
    allowed_argument_sets = {
        frozenset(expected | extra | set(group)) for group in local_sets
    }
    if frozenset(arguments) not in allowed_argument_sets:
        raise McpRequestError("arguments_invalid")
    safe_arguments: dict[str, str] = {}
    for key in expected:
        value = arguments.get(key)
        if key == "port":
            if type(value) is not int or not 0 <= value <= 4096:
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = str(value)
            continue
        if key in {"msp_ref", "customer_ref"}:
            if not isinstance(value, str) or not _SAFE_MSP_REF.fullmatch(value):
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = value
            continue
        if key == "family_id":
            if (not isinstance(value, str) or
                    not re.fullmatch(r"(?:0|[1-9][0-9]{0,9})", value) or
                    int(value) > (1 << 31) - 1):
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = value
            continue
        if key == "application_id":
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = value
            continue
        if key not in {"site_ref", "history_ref", "incident_ref", "device_ref", "gateway_ref", "switch_ref", "client_ref", "ssid_ref", "wlan_group_ref", "network_ref", "wan_port_ref", "site_template_ref"} or not isinstance(value, str) or not _SAFE_REF.fullmatch(value):
            raise McpRequestError("arguments_invalid")
        safe_arguments[key] = value
    for key in extra:
        if key == "pon_port":
            try:
                safe_arguments[key] = validate_pon_port_selector(arguments.get(key))
            except (TypeError, OltOnuInventoryError) as exc:
                raise McpRequestError("arguments_invalid") from exc
        elif key == "page_number":
            value = arguments.get(key)
            if type(value) is not int or not 0 <= value <= 10_000:
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = str(value)
        elif key == "page_size":
            value = arguments.get(key)
            if type(value) is not int or not 1 <= value <= 100:
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = str(value)
        elif key == "vpn_type":
            value = arguments.get(key)
            allowed_values = (
                range(6) if operation.operation_id == "site_vpn_server_status_summary"
                else (0, 1, 3, 4) if operation.operation_id == "site_vpn_client_status_summary"
                else (0, 1))
            if type(value) is not int or value not in allowed_values:
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = str(value)
        elif key == "function":
            value = arguments.get(key)
            if (type(value) is not int or not 0 <= value <= 15 or
                    operation.operation_id != "site_wan_port_availability_summary"):
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = str(value)
    for key in set(arguments) & local_names:
        value = arguments.get(key)
        if key in {"client_name", "ssid_name"}:
            if (not isinstance(value, str) or not 1 <= len(value) <= 128 or
                    value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = value
        elif key in {"start_ms", "end_ms"}:
            if type(value) is not int or not 946684800000 <= value <= 4102444800000:
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = str(value)
        elif key in {"start_local", "end_local"}:
            if (not isinstance(value, str) or not 16 <= len(value) <= 23 or
                    not re.fullmatch(
                        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
                        r"(?::[0-9]{2}(?:\.[0-9]{1,3})?)?", value)):
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = value
        elif key == "time_zone":
            if (not isinstance(value, str) or not 1 <= len(value) <= 64 or
                    not re.fullmatch(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*", value)):
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = value
        elif key == "archived":
            if type(value) is not bool:
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = "true" if value else "false"
        elif key == "vlan_id":
            if type(value) is not int or not 1 <= value <= 4094:
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = str(value)
        elif key == "type" and operation.operation_id == "site_mac_auth_ssid_inventory":
            if type(value) is not int or value not in (1, 2, 3):
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = str(value)
        elif key == "device_type" and operation.operation_id == "site_routing_table_summary":
            if value not in {"gateway", "switch"}:
                raise McpRequestError("arguments_invalid")
            safe_arguments[key] = value
    if {"start_local", "end_local", "time_zone"} <= set(safe_arguments):
        try:
            resolve_local_site_log_window(
                safe_arguments["start_local"], safe_arguments["end_local"],
                safe_arguments["time_zone"])
        except SiteLogWindowError as exc:
            raise McpRequestError("arguments_invalid") from exc
    value = invoke_read(operation_id, safe_arguments)
    return _tool_result(value)


def _item_counts(items: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        label = value if isinstance(value, str) else "unknown"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _evidence_counts(evidence: list[object], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in evidence:
        value = entry.get(key) if isinstance(entry, dict) else None
        if isinstance(value, str):
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _tool_result(value: dict[str, object]) -> dict[str, object]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False,
                                                            separators=(",", ":"))}],
        "structuredContent": value,
        "isError": value.get("status") == "error",
    }


def handle_mcp_request(request: object, origin: str | None, registry: Any,
                       invoke_read: Callable[[str, dict[str, str]], dict[str, object]],
                       server_version: str = "0.3.0-dev",
                       invoke_action: Callable[[str, dict[str, object]], dict[str, object]] | None = None) -> dict[str, object] | None:
    """Handle one JSON-RPC message. None means an accepted notification."""
    if not _origin_allowed(origin):
        raise McpRequestError("origin_not_allowed")
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or "method" not in request:
        return _rpc_error(request.get("id") if isinstance(request, dict) else None,
                          -32600, "Invalid Request")
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    if not isinstance(method, str) or not isinstance(params, dict):
        return _rpc_error(request_id, -32600, "Invalid Request")
    if request_id is None and method.startswith("notifications/"):
        return None
    if method == "ping":
        result: dict[str, object] = {}
    elif method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "omada-universal-connector", "version": server_version},
        }
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        try:
            result = _tools_page(registry, params.get("cursor"))
        except McpRequestError as exc:
            return _rpc_error(request_id, -32602, exc.code)
    elif method == "tools/call":
        try:
            result = _invoke_tool(registry, params.get("name"), params.get("arguments", {}), invoke_read, invoke_action)
        except McpRequestError as exc:
            return _rpc_error(request_id, -32602 if exc.code == "arguments_invalid" else -32601, exc.code)
    else:
        return _rpc_error(request_id, -32601, "Method not found")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
