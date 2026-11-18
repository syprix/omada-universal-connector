from __future__ import annotations

import unittest

from app.network_diagnose import NetworkDiagnoseError, run
from app.switch_diagnose import SwitchDiagnoseError, _bound_json, run as run_switch


SITE_REF, GATEWAY_REF = "a" * 24, "d" * 24
ROOT = f"/v1/sites/{SITE_REF}/gateways/{GATEWAY_REF}"
SITE_SETTINGS_ROUTE = f"/v1/sites/{SITE_REF}/settings/existence"
SITE_CAPABILITIES_ROUTE = f"/v1/sites/{SITE_REF}/capabilities"


def _responses() -> dict[str, dict[str, object]]:
    return {
        "/v1/sites": {"status": "ok", "resource": "sites", "count": 1,
                       "items": [{"site_ref": SITE_REF}]},
        f"/v1/sites/{SITE_REF}/devices": {
            "status": "ok", "resource": "devices", "site_ref": SITE_REF,
            "count": 1, "items": [{"device_ref": GATEWAY_REF, "device_type": "gateway"}],
        },
        ROOT + "/wan-status": {
            "status": "ok", "resource": "gateway_wan_status", "device_ref": GATEWAY_REF,
            "count": 1, "items": [{"port": 1, "link_status": 1, "latency_ms": 12}],
        },
        ROOT + "/wan-health": {
            "status": "ok", "resource": "gateway_wan_health", "device_ref": GATEWAY_REF,
            "wan_details": [{"port": 1, "protocol_code": 1}], "count": 1,
            "partial": False,
        },
        ROOT + "/health": {
            "status": "ok", "resource": "gateway_health", "site_ref": SITE_REF,
            "gateway_ref": GATEWAY_REF, "window_start_ms": 100, "window_end_ms": 200,
            "data": {"score": 80},
        },
        ROOT + "/health/timeline": {
            "status": "ok", "resource": "gateway_health_timeline", "site_ref": SITE_REF,
            "gateway_ref": GATEWAY_REF, "data": {"scores": [{"time_ms": 200, "score": 80}]},
            "partial": False,
        },
        ROOT + "/lan-status": {
            "status": "ok", "resource": "gateway_lan_status", "device_ref": GATEWAY_REF,
            "count": 1, "source_count": 1, "items": [{"vlan": 20, "rx": 1000,
            "tx": 2000, "clientNum": 3}], "partial": False,
        },
        ROOT + "/ports": {
            "status": "ok", "resource": "gateway_ports", "device_ref": GATEWAY_REF,
            "count": 1, "source_count": 1, "items": [{"port": 1, "type": 2,
            "physicalType": 1, "mode": 0}], "partial": False,
        },
        ROOT + "/speed-test-results": {
            "status": "ok", "resource": "gateway_speed_test_results",
            "device_ref": GATEWAY_REF, "data": {"status_code": 0, "count": 1,
            "source_count": 1, "items": [{"portId": 1, "down": 900000}],
            "partial": False, "omitted_count": 0, "unknown_field_count": 0,
            "redacted_field_count": 2},
        },
        ROOT + "/internet-info": {
            "status": "ok", "resource": "gateway_internet_info", "device_ref": GATEWAY_REF,
            "data": {"support": {"lte": True}, "settings": {"internet_enabled": True},
                     "online_detection_code_counts": {"wan": [{"code": 1, "count": 1}]},
                     "partial": False, "unknown_field_count": 0, "redacted_field_count": 1},
        },
        SITE_SETTINGS_ROUTE: {
            "status": "ok", "resource": "site_setting_existence", "site_ref": SITE_REF,
            "data": {"settings": {"dns_proxy": True, "qos": False},
                     "present_count": 2, "missing_count": 0, "invalid_count": 0,
                     "unknown_field_count": 0},
        },
        SITE_CAPABILITIES_ROUTE: {
            "status": "ok", "resource": "site_capabilities", "site_ref": SITE_REF,
            "data": {"capabilities": {"firewall": True, "qos": False},
                     "present_count": 2, "missing_count": 0, "invalid_count": 0,
                     "unknown_field_count": 0},
        },
    }


class NetworkDiagnoseTests(unittest.TestCase):
    def test_binds_gateway_to_fresh_site_inventory_then_reads_fixed_routes(self) -> None:
        responses, calls = _responses(), []
        result = run(SITE_REF, GATEWAY_REF, lambda path: calls.append(path) or responses[path])
        self.assertEqual(calls, list(responses))
        self.assertEqual(calls[:2], ["/v1/sites", f"/v1/sites/{SITE_REF}/devices"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(set(result["results"]), {
            "wan_status", "wan_details", "health", "health_timeline", "lan_status", "ports",
            "speed_test_results", "internet_info", "site_setting_existence",
            "site_capabilities"})
        self.assertEqual(result["results"]["wan_status"]["items"][0]["latency_ms"], 12)
        self.assertEqual(result["results"]["health"]["window_start_ms"], 100)
        self.assertNotIn("device_ref", repr(result))
        self.assertEqual(result["results"]["site_setting_existence"]["data"]["settings"],
                         {"dns_proxy": True, "qos": False})

    def test_unknown_or_non_gateway_inventory_reference_stops_before_diagnostics(self) -> None:
        responses = _responses()
        responses[f"/v1/sites/{SITE_REF}/devices"]["items"] = [
            {"device_ref": "e" * 24, "device_type": "gateway"}]
        responses[f"/v1/sites/{SITE_REF}/devices"]["count"] = 1
        calls: list[str] = []
        with self.assertRaisesRegex(NetworkDiagnoseError, "gateway_ref_unknown"):
            run(SITE_REF, GATEWAY_REF, lambda path: calls.append(path) or responses[path])
        self.assertEqual(calls, ["/v1/sites", f"/v1/sites/{SITE_REF}/devices"])

    def test_partial_error_and_wrong_reference_are_reported_without_replay(self) -> None:
        responses = _responses()
        calls = []

        def request(path: str) -> object:
            calls.append(path)
            if path.endswith("/wan-health"):
                return {**responses[path], "device_ref": "e" * 24}
            return responses[path]

        result = run(SITE_REF, GATEWAY_REF, request)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["results"]["wan_details"]["error"], "response_invalid")
        self.assertEqual(len(calls), 12)

    def test_direct_wan_detail_list_is_summarized_and_partial_is_preserved(self) -> None:
        responses = _responses()
        responses[ROOT + "/wan-health"].update({
            "wan_details": [{"port": 1, "latency": 12, "omitted_field_count": 2}],
            "count": 1,
            "partial": True,
        })
        result = run(SITE_REF, GATEWAY_REF, lambda path: responses[path])
        section = result["results"]["wan_details"]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(section["status"], "ok")
        self.assertEqual(section["count"], 1)
        self.assertTrue(section["partial"])

    def test_direct_wan_detail_count_mismatch_is_rejected(self) -> None:
        responses = _responses()
        responses[ROOT + "/wan-health"]["count"] = 2
        result = run(SITE_REF, GATEWAY_REF, lambda path: responses[path])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["results"]["wan_details"],
                         {"status": "error", "error": "response_invalid",
                          "capability_status": "unknown"})

    def test_sanitized_upstream_codes_survive_as_an_isolated_section_error(self) -> None:
        responses = _responses()

        def request(path: str) -> object:
            if path == ROOT + "/internet-info":
                raise NetworkDiagnoseError("openapi_rejected", upstream_http_status=200,
                                           upstream_error_code=-1)
            return responses[path]

        result = run(SITE_REF, GATEWAY_REF, request)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["results"]["internet_info"], {
            "status": "error", "error": "openapi_rejected",
            "capability_status": "unknown", "upstream_http_status": 200,
            "upstream_error_code": -1,
        })

    def test_rejects_invalid_references_and_unbounded_rows(self) -> None:
        with self.assertRaisesRegex(NetworkDiagnoseError, "site_ref_invalid"):
            run("../", GATEWAY_REF, lambda _path: {})
        with self.assertRaisesRegex(NetworkDiagnoseError, "gateway_ref_invalid"):
            run(SITE_REF, "x", lambda _path: {})
        responses = _responses()
        responses[ROOT + "/wan-status"]["items"] = [{}] * 65
        result = run(SITE_REF, GATEWAY_REF, lambda path: responses[path])
        self.assertEqual(result["results"]["wan_status"]["error"], "response_invalid")

    def test_switch_bundle_checks_fresh_inventory_and_reads_all_fixed_routes(self) -> None:
        switch_ref = "e" * 24
        root = f"/v1/sites/{SITE_REF}/switches/{switch_ref}"
        responses = {
            "/v1/sites": {"status": "ok", "resource": "sites", "items":[{"site_ref": SITE_REF}]},
            f"/v1/sites/{SITE_REF}/devices": {
                "status": "ok", "resource": "devices", "items":[
                    {"device_ref": switch_ref, "device_type": "switch", "model": "SW-1"}]},
            root + "/health": {"status": "ok", "resource": "switch_health", "switch_ref": switch_ref,
                                "data": {"dimensions": {}}, "partial": False},
            root + "/health/timeline": {"status": "ok", "resource": "switch_health_timeline",
                                          "switch_ref": switch_ref, "data": {"scores": []}, "partial": False},
            root + "/sdm-usage": {"status": "ok", "resource": "switch_sdm_usage",
                                   "switch_ref": switch_ref, "data": {"category": 0, "num": 24}, "partial": False},
            root + "/cable-test/logs": {"status": "ok", "resource": "switch_cable_test_logs",
                                         "switch_ref": switch_ref, "count": 0,
                                         "data": {"logs": []}, "partial": False},
            root + "/cable-test/full-results": {"status": "ok", "resource": "switch_cable_test_full_results",
                                                 "switch_ref": switch_ref,
                                                 "data": {"status_code": 0, "ports": []}, "partial": False},
            root + "/cable-test/increment-results": {"status": "ok", "resource": "switch_cable_test_increment_results",
                                                      "switch_ref": switch_ref,
                                                      "data": {"status_code": 0, "ports": []}, "partial": False},
            root + "/cable-test/ports": {"status": "ok", "resource": "switch_cable_test_ports",
                                           "switch_ref": switch_ref,
                                           "data": {"ports": []}, "partial": False},
            root + "/dhcp/users": {"status": "ok", "resource": "switch_dhcp_users",
                                     "switch_ref": switch_ref,
                                     "data": {"summary": {"total": 0}}, "partial": False},
            root + "/ospf-neighbors": {"status": "ok", "resource": "switch_ospf_neighbors",
                                         "switch_ref": switch_ref,
                                         "summary": {"by_state": {}, "unknown_state_rows": 0},
                                         "count": 0, "partial": False},
            root + "/port-networks": {"status": "ok", "resource": "switch_port_networks",
                                        "switch_ref": switch_ref, "count": 0,
                                        "summary": {"vlans": [], "unknown_vlan_rows": 0},
                                        "partial": False},
            root + "/exist-networks": {"status": "ok", "resource": "switch_exist_networks",
                                        "switch_ref": switch_ref, "count": 0,
                                        "summary": {"by_vlan": {}, "by_vlan_type": {}},
                                        "partial": False},
            root + "/networks": {"status": "ok", "resource": "switch_networks",
                                   "switch_ref": switch_ref, "count": 0,
                                   "summary": {"by_vlan": {}, "by_status_code": {},
                                                "by_dhcp_mode_code": {}, "unknown_rows": 0},
                                   "partial": False},
            root + "/interfaces": {"status": "ok", "resource": "switch_interfaces",
                                     "switch_ref": switch_ref, "count": 0,
                                     "summary": {"by_type_code": {}, "unknown_rows": 0},
                                     "partial": False},
            root + "/routing-table": {"status": "ok", "resource": "switch_routing_table",
                                       "switch_ref": switch_ref, "count": 0,
                                       "summary": {"by_type": {}, "by_distance": {},
                                                    "by_metric": {}, "unknown_rows": 0},
                                       "partial": False},
            root + "/static-routes": {"status": "ok", "resource": "switch_static_routes",
                                       "switch_ref": switch_ref, "count": 0,
                                       "summary": {"by_status": {}, "by_ip_version": {},
                                                    "by_distance": {}, "by_resource_code": {},
                                                    "by_destination_count": {},
                                                    "support_ipv6_static_routing": None},
                                       "partial": False},
            root + "/vrfs": {"status": "ok", "resource": "switch_vrfs",
                                      "switch_ref": switch_ref,
                                      "count": 0, "summary": {"by_ipv4_enabled": {}, "by_ipv6_enabled": {},
                                      "default_count": 0, "by_resource_code": {}, "unknown_rows": 0}, "partial": False},
            root + "/vlan-interfaces": {"status": "ok", "resource": "switch_vlan_interfaces",
                                      "switch_ref": switch_ref, "count": 0,
                                      "summary": {"unique_vlan_count": 0, "unknown_rows": 0}, "partial": False},
            root + "/statistics": {"status": "ok", "resource": "switch_statistics",
                                      "switch_ref": switch_ref, "data": {"port_count": 0,
                                      "by_link_status_code": {}, "unknown_port_rows": 0}, "partial": False},
            root + "/ports": {"status": "ok", "resource": "switch_ports", "device_ref": switch_ref,
                               "count": 1, "items": [{"port": 1, "link_status": 1}]},
            root + "/ports/counters": {"status": "ok", "resource": "switch_port_counters",
                                        "switch_ref": switch_ref, "data": {"ports": []}},
            root + "/ports/poe-info": {"status": "ok", "resource": "switch_port_poe_info",
                                        "switch_ref": switch_ref, "data": {"ports": []}},
            root + "/vlans": {"status": "ok", "resource": "switch_vlans", "switch_ref": switch_ref,
                               "count": 1, "items": [{"vlan_ref": "f" * 24, "ports": [1]}],
                               "membership_summary": {"isolated_networks": 0,
                                   "memberships": {"native": {"ports": 1, "lags": 0},
                                       "tagged": {"ports": 0, "lags": 0},
                                       "untagged": {"ports": 0, "lags": 0}},
                                   "unknown_network_rows": 0,
                                   "incomplete_membership_rows": 0}},
            root + "/lldp-neighbors": {"status": "ok", "resource": "switch_lldp_neighbors",
                                        "switch_ref": switch_ref, "data": {"neighbor_count": 1}},
        }
        calls = []
        report = run_switch(SITE_REF, switch_ref, lambda path: calls.append(path) or responses[path])
        self.assertEqual(calls, list(responses))
        self.assertEqual(report["status"], "ok")
        self.assertEqual(set(report["results"]), {"health", "health_timeline", "sdm_usage", "cable_test_logs", "cable_test_full_results", "cable_test_increment_results", "cable_test_ports", "dhcp_users", "ospf_neighbors", "port_networks", "exist_networks", "networks", "interfaces", "routing_table", "static_routes", "vrfs", "vlan_interfaces", "statistics", "ports", "port_counters", "poe", "vlans", "lldp"})
        self.assertEqual(report["results"]["ports"]["items"][0]["port"], 1)
        self.assertEqual(report["results"]["vlans"]["membership_summary"]["memberships"]["native"]["ports"], 1)
        self.assertNotIn("SW-1", repr(report))

    def test_switch_bundle_rejects_unlisted_or_non_switch_refs_before_detail_reads(self) -> None:
        switch_ref = "e" * 24
        calls = []
        responses = {
            "/v1/sites": {"status": "ok", "resource": "sites", "items":[{"site_ref": SITE_REF}]},
            f"/v1/sites/{SITE_REF}/devices": {
                "status": "ok", "resource": "devices", "items":[
                    {"device_ref": switch_ref, "device_type": "access point"}]},
        }
        with self.assertRaises(SwitchDiagnoseError) as caught:
            run_switch(SITE_REF, switch_ref,
                       lambda path: calls.append(path) or responses[path])
        self.assertEqual(caught.exception.code, "switch_ref_unknown")
        self.assertEqual(calls, ["/v1/sites", f"/v1/sites/{SITE_REF}/devices"])

    def test_switch_output_bounds_nested_arrays_and_counts_omitted_entries(self) -> None:
        bounded, omitted = _bound_json({"ports": [{"port": port} for port in range(70)]})
        self.assertEqual(len(bounded["ports"]), 64)
        self.assertEqual(bounded["ports"][-1], {"port": 63})
        self.assertEqual(omitted, 6)


if __name__ == "__main__":
    unittest.main()
