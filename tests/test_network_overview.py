from __future__ import annotations

import unittest

from app import mcp
from app.network_diagnose import NetworkDiagnoseError, run_site
from app.operation_registry import REGISTRY


SITE = "a" * 24
DEVICE = "b" * 24


def _responses() -> dict[str, dict[str, object]]:
    root = f"/v1/sites/{SITE}"
    return {
        root + "/devices": {
            "status": "ok", "resource": "devices", "site_ref": SITE, "count": 1,
            "items": [{"device_ref": DEVICE, "device_type": "AP", "name": "private label"}],
        },
        root + "/health/summary": {
            "status": "ok", "resource": "site_overview", "site_ref": SITE,
            "data": {"health_score": 91}, "partial": False,
        },
        root + "/networks": {
            "status": "ok", "resource": "networks", "site_ref": SITE, "count": 1,
            "items": [{"network_ref": "c" * 24, "name": "private SSID", "vlan": 42}],
        },
        root + "/topology/network-summary": {
            "status": "ok", "resource": "site_topology_network_summary", "site_ref": SITE,
            "data": {"unknown_field_count": 0, "split_network_count": 1,
                     "default_network_count": 1, "configuring_network_count": 0,
                     "unknown_network_field_count": 0, "ssid_count": 1,
                     "ssid_vlan_enabled_count": 1, "ssid_configuring_count": 0,
                     "ssid_client_count_sum": 2, "ssid_vlan_id_count": 1,
                     "unknown_ssid_field_count": 0, "partial": False},
        },
        root + "/topology/vlan-summary": {
            "status": "ok", "resource": "site_topology_vlan_summary", "site_ref": SITE,
            "data": {"network_count": 1, "distinct_vlan_count": 1,
                     "default_network_count": 0, "configuring_network_count": 0,
                     "missing_vlan_id_count": 0, "unknown_network_field_count": 0,
                     "unknown_field_count": 0, "partial": False},
        },
        root + "/dhcp/leases": {
            "status": "ok", "resource": "dhcp_leases", "site_ref": SITE,
            "count": 2, "summary": {"total": 2, "devices": 1, "clients": 1,
                                         "dynamic": 2, "static": 0},
            "items": [{"ip": "192.0.2.1", "mac": "secret"}],
        },
        root + "/dns/cache": {"status": "ok", "resource": "dns_cache_settings",
                                "site_ref": SITE, "data": {"enabled": True, "ttl_seconds": 600}},
        root + "/dns/proxy": {"status": "ok", "resource": "dns_proxy_settings",
                                "site_ref": SITE, "data": {"enabled": True, "mode": "doh"}},
        root + "/dns/records": {
            "status": "ok", "resource": "lan_dns_records", "site_ref": SITE,
            "count": 1, "items": [{"record_ref": "d" * 48, "record_type": "ip",
                                     "enabled": True, "domain": "private.example"}],
        },
        root + "/events": {"status": "ok", "resource": "site_events", "site_ref": SITE,
                            "count": 1, "window_start_ms": 100, "window_end_ms": 200,
                            "items": [{"event_ref": "e" * 48, "time_ms": 150, "module": "device"}]},
        root + "/alerts": {"status": "ok", "resource": "site_alerts", "site_ref": SITE,
                            "count": 1, "window_start_ms": 100, "window_end_ms": 200,
                            "items": [{"alert_ref": "f" * 48, "time_ms": 160, "module": "system",
                                       "severity": "warning", "message": "private"}]},
        root + "/topology": {
            "status": "ok", "resource": "site_topology", "site_ref": SITE,
            "nodes": [{"device_ref": DEVICE, "device_type": "ap", "disconnected": False}],
            "edges": [], "partial": False, "omitted_node_count": 0,
            "omitted_edge_count": 0, "last_update_ms": 1800000000000,
        },
    }


class NetworkOverviewTests(unittest.TestCase):
    def test_event_summary_keeps_total_separate_from_bounded_sample(self) -> None:
        responses = _responses()
        event_path = f"/v1/sites/{SITE}/events"
        responses[event_path].update({
            "total_count": 250,
            "partial": True,
            "module_counts": {"system": 10, "device": 230, "client": 10},
        })
        report = run_site(SITE, lambda path: responses[path])
        events = report["results"]["events"]
        self.assertEqual(report["status"], "partial")
        self.assertEqual(events["count"], 250)
        self.assertEqual(events["sampled_count"], 1)
        self.assertEqual(events["module_counts"],
                         {"system": 10, "device": 230, "client": 10, "other": 0})
        self.assertTrue(events["partial"])

    def test_event_summary_must_match_reported_total(self) -> None:
        responses = _responses()
        event_path = f"/v1/sites/{SITE}/events"
        responses[event_path].update({
            "total_count": 250,
            "partial": True,
            "module_counts": {"system": 10, "device": 229, "client": 10},
        })
        report = run_site(SITE, lambda path: responses[path])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["results"]["events"],
                         {"status": "error", "error": "response_invalid"})

    def test_site_bundle_orders_inventory_before_topology_and_redacts_rows(self) -> None:
        responses, calls = _responses(), []
        report = run_site(SITE, lambda path: calls.append(path) or responses[path])
        root = f"/v1/sites/{SITE}"
        self.assertEqual(calls, [root + "/devices", root + "/health/summary",
                                 root + "/networks", root + "/dhcp/leases",
                                 root + "/topology/network-summary",
                                 root + "/topology/vlan-summary",
                                 root + "/dns/cache", root + "/dns/proxy",
                                 root + "/dns/records", root + "/events", root + "/alerts",
                                 root + "/topology"])
        self.assertEqual(report["status"], "ok")
        result = report["results"]
        self.assertEqual(result["devices"]["device_type_counts"],
                         {"ap": 1, "gateway": 0, "switch": 0, "other": 0})
        self.assertEqual(result["networks"], {"status": "ok", "count": 1})
        self.assertEqual(result["topology_network_summary"]["data"]["ssid_count"], 1)
        self.assertNotIn("42", repr(result["topology_network_summary"]))
        self.assertEqual(result["vlan_summary"]["data"]["distinct_vlan_count"], 1)
        self.assertNotIn("42", repr(result["vlan_summary"]))
        self.assertEqual(result["dhcp"]["binding_counts"]["clients"], 1)
        self.assertEqual(result["dns_records"]["record_counts"],
                         {"ip": 1, "cname": 0, "forward": 0, "enabled": 1})
        self.assertEqual(result["alerts"]["severity_counts"]["warning"], 1)
        self.assertNotIn("private label", repr(report))
        self.assertNotIn("private SSID", repr(report))
        self.assertNotIn("secret", repr(report))
        self.assertNotIn("private.example", repr(report))
        self.assertNotIn("private", repr(report))
        self.assertNotIn("c" * 24, repr(report))

    def test_partial_failures_are_isolated_and_topology_needs_inventory(self) -> None:
        responses = _responses()
        responses[f"/v1/sites/{SITE}/devices"] = {
            "status": "error", "resource": "devices", "error": "connector_http_error"}
        calls: list[str] = []
        report = run_site(SITE, lambda path: calls.append(path) or responses[path])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["results"]["devices"]["status"], "error")
        self.assertEqual(report["results"]["topology"]["error"], "device_inventory_required")
        self.assertNotIn(f"/v1/sites/{SITE}/topology", calls)

    def test_malformed_vlan_summary_isolated_from_other_sections(self) -> None:
        responses = _responses()
        responses[f"/v1/sites/{SITE}/topology/vlan-summary"]["data"]["distinct_vlan_count"] = True
        report = run_site(SITE, lambda path: responses[path])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["results"]["vlan_summary"],
                         {"status": "error", "error": "response_invalid"})
        self.assertEqual(report["results"]["networks"]["count"], 1)
        self.assertEqual(report["results"]["topology"]["status"], "ok")

    def test_malformed_network_summary_isolated_from_other_sections(self) -> None:
        responses = _responses()
        responses[f"/v1/sites/{SITE}/topology/network-summary"]["data"]["ssid_count"] = True
        report = run_site(SITE, lambda path: responses[path])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["results"]["topology_network_summary"],
                         {"status": "error", "error": "response_invalid"})
        self.assertEqual(report["results"]["vlan_summary"]["status"], "ok")

    def test_rejects_unbound_or_invalid_topology_refs(self) -> None:
        responses = _responses()
        responses[f"/v1/sites/{SITE}/topology"]["nodes"] = [
            {"device_ref": "d" * 24, "device_type": "ap"}]
        result = run_site(SITE, lambda path: responses[path])
        self.assertEqual(result["results"]["topology"],
                         {"status": "error", "error": "response_invalid"})
        with self.assertRaisesRegex(NetworkDiagnoseError, "site_ref_invalid"):
            run_site("../", lambda _path: {})

    def test_mcp_advertises_and_dispatches_fixed_site_tool(self) -> None:
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "omada_network_overview",
                              "arguments": {"site_ref": SITE}}}
        calls: list[tuple[str, dict[str, str]]] = []
        response = mcp.handle_mcp_request(
            request, None, REGISTRY,
            lambda name, args: calls.append((name, args)) or {"status": "ok"})
        self.assertEqual(response["result"]["structuredContent"], {"status": "ok"})
        self.assertEqual(calls, [("network_overview", {"site_ref": SITE})])
        bad = {**request, "params": {"name": "omada_network_overview",
                                      "arguments": {"site_ref": SITE, "path": "/anything"}}}
        rejected = mcp.handle_mcp_request(bad, None, REGISTRY, lambda *_: {})
        self.assertEqual(rejected["error"]["message"], "arguments_invalid")


if __name__ == "__main__":
    unittest.main()
