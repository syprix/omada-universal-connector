"""Staged shadow comparison of candidate registry with the existing HTTP dispatcher."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient
from app.operation_registry import REGISTRY, RegistryError


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def list_sites(self):
        self.calls.append(("sites", None))
        return {"status": "ok", "resource": "sites", "count": 0, "items": []}

    def list_devices(self, ref):
        self.calls.append(("devices", ref))
        return {"status": "ok", "resource": "devices", "count": 0, "items": []}

    def list_clients(self, ref):
        self.calls.append(("clients", ref))
        return {"status": "ok", "resource": "clients", "count": 0, "items": []}

    def list_networks(self, ref):
        self.calls.append(("networks", ref))
        return {"status": "ok", "resource": "networks", "count": 0, "items": []}

    def list_ssids(self, ref):
        self.calls.append(("ssids", ref))
        return {"status": "ok", "resource": "ssids", "count": 0, "items": []}

    def read_controller_health(self):
        self.calls.append(("controller_health", None))
        return {"status": "ok", "resource": "controller_health", "data": {}}

    def read_controller_firmware_pool_channel_counts(self):
        self.calls.append(("controller_firmware_pool_channel_counts", None))
        return {"status": "ok", "resource": "controller_firmware_pool_channel_counts",
                "channel_counts": {"stable": 0, "release_candidate": 2, "beta": 3},
                "partial": False}

    def read_controller_firmware_critical_model_count(self):
        self.calls.append(("controller_firmware_critical_model_count", None))
        return {"status": "ok", "resource": "controller_firmware_critical_model_count",
                "critical_model_count": 0, "count_present": True,
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "coverage_complete": True, "partial": False}

    def read_site_overview(self, ref):
        self.calls.append(("site_overview", ref))
        return {"status": "ok", "resource": "site_overview", "site_ref": ref, "data": {}}

    def read_site_health_timeline(self, ref):
        self.calls.append(("site_health_timeline", ref))
        return {"status": "ok", "resource": "site_health_timeline", "site_ref": ref, "items": []}

    def read_site_client_health_timeline(self, ref):
        self.calls.append(("site_client_health_timeline", ref))
        return {"status": "ok", "resource": "site_client_health_timeline", "site_ref": ref,
                "data": {"scores": []}}

    def read_site_wifi_summary(self, ref):
        self.calls.append(("site_wifi_summary", ref))
        return {"status": "ok", "resource": "site_wifi_summary", "site_ref": ref,
                "data": {"clients": 0}, "partial": True}

    def read_experience_index(self, ref):
        self.calls.append(("experience_index", ref))
        return {"status": "ok", "resource": "experience_index", "site_ref": ref,
                "data": {"last_scan": []}}

    def read_rf_planning_result(self, ref):
        self.calls.append(("rf_planning_result", ref))
        return {"status": "ok", "resource": "rf_planning_result", "site_ref": ref,
                "data": {"status": 1}}

    def read_rf_planning_dashboard(self, ref):
        self.calls.append(("rf_planning_dashboard", ref))
        return {"status": "ok", "resource": "rf_planning_dashboard", "site_ref": ref,
                "data": {"bands": {}}}

    def read_rf_planning_dashboard_current(self, ref):
        self.calls.append(("rf_planning_dashboard_current", ref))
        return {"status": "ok", "resource": "rf_planning_dashboard_current", "site_ref": ref,
                "data": {"bands": {}}, "partial": False}

    def read_rf_planning_dashboard_history(self, ref):
        self.calls.append(("rf_planning_dashboard_history", ref))
        return {"status": "ok", "resource": "rf_planning_dashboard_history", "site_ref": ref,
                "data": {"bands": {}}, "partial": False}

    def read_rf_excluded_aps(self, ref):
        self.calls.append(("rf_excluded_aps", ref))
        return {"status": "ok", "resource": "rf_excluded_aps", "site_ref": ref,
                "count": 0, "items": [], "partial": False}

    def read_rf_deploy_history(self, ref):
        self.calls.append(("rf_deploy_history", ref))
        return {"status": "ok", "resource": "rf_deploy_history", "site_ref": ref,
                "data": {"first_deployment": True}, "partial": False}

    def read_ap_radio_part(self, site_ref, device_ref, part):
        self.calls.append((part, site_ref + ":" + device_ref))
        return {"status": "ok", "resource": part, "device_ref": device_ref,
                "data": {"channelLoadStatus": 1}}

    def read_ap_wifi_neighbors(self, site_ref, device_ref):
        self.calls.append(("ap_wifi_neighbors", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "ap_wifi_neighbors", "device_ref": device_ref,
                "count": 0, "items": []}

    def read_ap_speed_test_results(self, site_ref, device_ref):
        self.calls.append(("ap_speed_test_results", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "ap_speed_test_results", "device_ref": device_ref,
                "data": {"main_testing": False, "results": []}}

    def read_rf_planning_detail(self, ref):
        self.calls.append(("rf_planning_detail", ref))
        return {"status": "ok", "resource": "rf_planning_detail", "site_ref": ref,
                "data": {"aps": [], "ap_count": 0}}

    def read_rf_planning_history(self, ref):
        self.calls.append(("rf_planning_history", ref))
        return {"status": "ok", "resource": "rf_planning_history", "site_ref": ref,
                "data": {"items": [], "count": 0}, "truncated": False}

    def read_rf_planning_history_detail(self, ref, history_ref):
        self.calls.append(("rf_planning_history_detail", ref + ":" + history_ref))
        return {"status": "ok", "resource": "rf_planning_history_detail", "site_ref": ref,
                "history_ref": history_ref, "data": {"aps": [], "ap_count": 0}}

    def read_rf_planning_recent_history(self, ref):
        self.calls.append(("rf_planning_recent_history", ref))
        return {"status": "ok", "resource": "rf_planning_recent_history", "site_ref": ref,
                "data": {"items": [], "count": 0}, "truncated": False}

    def list_gateway_firewall_rules(self, ref):
        self.calls.append(("gateway_firewall_rules", ref))
        return {"status": "ok", "resource": "gateway_firewall_rules", "count": 0, "items": []}


class RegistryShadowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.token = "shadow-test-token-with-enough-length-0123456789"
        self.token_path = os.path.join(self.tempdir.name, "token")
        with open(self.token_path, "w", encoding="ascii") as f:
            f.write(self.token)
        self.fake = FakeClient()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_path})
        self.env.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.fake)
        self.client_patch.start()

    def tearDown(self):
        self.client_patch.stop()
        self.env.stop()
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, *, token: str | None = None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Authorization": "Bearer " + token} if token else {}
        conn.request(method, path, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        status = response.status
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {}
        conn.close()
        return status, body

    def test_registered_gets_match_http_dispatch_without_upstream_calls(self):
        ref = "0123456789abcdef01234567"
        expected = {
            "/v1/sites": ("sites", None),
            f"/v1/sites/{ref}/devices": ("devices", ref),
            f"/v1/sites/{ref}/clients": ("clients", ref),
            f"/v1/sites/{ref}/networks": ("networks", ref),
            f"/v1/sites/{ref}/ssids": ("ssids", ref),
            "/v1/controller/health": ("controller_health", None),
            "/v1/controller/firmware-critical-model-count/summary":
                ("controller_firmware_critical_model_count", None),
            "/v1/controller/firmware-pool-channel-counts/summary":
                ("controller_firmware_pool_channel_counts", None),
            f"/v1/sites/{ref}/health/summary": ("site_overview", ref),
            f"/v1/sites/{ref}/health/timeline": ("site_health_timeline", ref),
            f"/v1/sites/{ref}/health/client/timeline": ("site_client_health_timeline", ref),
            f"/v1/sites/{ref}/wifi/summary": ("site_wifi_summary", ref),
            f"/v1/sites/{ref}/aps/{'b' * 24}/scan-status":
                ("scan_status", ref + ":" + "b" * 24),
            f"/v1/sites/{ref}/aps/{'b' * 24}/wifi-neighbors":
                ("ap_wifi_neighbors", ref + ":" + "b" * 24),
            f"/v1/sites/{ref}/aps/{'b' * 24}/speed-test-results":
                ("ap_speed_test_results", ref + ":" + "b" * 24),
            f"/v1/sites/{ref}/wifi/optimization/history": ("experience_index", ref),
            f"/v1/sites/{ref}/wifi/optimization/status": ("rf_planning_result", ref),
            f"/v1/sites/{ref}/wifi/optimization/dashboard": ("rf_planning_dashboard", ref),
            f"/v1/sites/{ref}/wifi/optimization/dashboard/current": ("rf_planning_dashboard_current", ref),
            f"/v1/sites/{ref}/wifi/optimization/dashboard/history": ("rf_planning_dashboard_history", ref),
            f"/v1/sites/{ref}/wifi/optimization/excluded-aps": ("rf_excluded_aps", ref),
            f"/v1/sites/{ref}/wifi/optimization/deployment-history": ("rf_deploy_history", ref),
            f"/v1/sites/{ref}/wifi/optimization/detail": ("rf_planning_detail", ref),
            f"/v1/sites/{ref}/wifi/optimization/history/records": ("rf_planning_history", ref),
            f"/v1/sites/{ref}/wifi/optimization/history/records/{'b' * 24}":
                ("rf_planning_history_detail", ref + ":" + "b" * 24),
            f"/v1/sites/{ref}/wifi/optimization/history/recent": ("rf_planning_recent_history", ref),
        }
        for path, call in expected.items():
            with self.subTest(path=path):
                candidate, bindings = REGISTRY.match("GET", path)
                expected_operation = ("ap_scan_status" if call[0] == "scan_status" else
                                      "ap_wifi_interference" if call[0] == "ap_wifi_neighbors" else
                                      call[0])
                self.assertEqual(candidate.operation_id, expected_operation)
                if call[0] == "rf_planning_history_detail":
                    self.assertEqual(dict(bindings), {
                        "site_ref": ref, "history_ref": "b" * 24,
                    })
                elif call[0] in {"scan_status", "ap_wifi_neighbors", "ap_speed_test_results"}:
                    self.assertEqual(dict(bindings), {
                        "site_ref": ref, "device_ref": "b" * 24,
                    })
                else:
                    self.assertEqual(dict(bindings).get("site_ref"), call[1])
                status, body = self.request("GET", path, token=self.token)
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], call[0])
                self.assertEqual(self.fake.calls[-1], call)
        # The fake is the only client supplied; no real upstream transport is constructed.
        self.assertEqual(len(self.fake.calls), 26)

    def test_invalid_refs_queries_and_methods_are_rejected_by_both_layers(self):
        paths = (
            "/v1/sites/0123456789ABCDEF01234567/devices",
            "/v1/sites/0123456789abcdef0123456/devices",
            "/v1/sites/0123456789abcdef01234567/devices?path=/arbitrary",
            "/v1/sites/0123456789ABCDEF01234567/health/summary",
            "/v1/sites/0123456789abcdef01234567/health/timeline?start=1&end=2",
        )
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(RegistryError):
                    REGISTRY.match("GET", path)
                status, _ = self.request("GET", path, token=self.token)
                self.assertEqual(status, 404)
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", "/v1/sites")
        status, _ = self.request("POST", "/v1/sites", token=self.token)
        self.assertEqual(status, 501)
        self.assertEqual(self.fake.calls, [])

    def test_valid_dispatch_does_not_bypass_bearer_authentication(self):
        ref = "0123456789abcdef01234567"
        path = f"/v1/sites/{ref}/devices"
        # Registry is only a matcher; it grants no HTTP authorization.
        self.assertEqual(REGISTRY.match("GET", path)[0].operation_id, "devices")
        status, body = self.request("GET", path)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        status, body = self.request("GET", path, token="wrong-token")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        self.assertEqual(self.fake.calls, [])

    def test_registered_acl_route_keeps_http_dispatch_and_capability_names(self):
        ref = "0123456789abcdef01234567"
        legacy_path = f"/v1/sites/{ref}/firewall/gateway-acls"
        self.assertEqual(REGISTRY.match("GET", legacy_path)[0].operation_id,
                         "gateway_firewall_rules")
        status, body = self.request("GET", legacy_path, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "gateway_firewall_rules")
        self.assertEqual(self.fake.calls, [("gateway_firewall_rules", ref)])

        capability_routes = dict(OmadaOpenApiClient.CAPABILITY_OPERATIONS)
        for item in REGISTRY.entries:
            self.assertEqual(capability_routes[item.operation_id], f"GET {item.public_template}")


if __name__ == "__main__":
    unittest.main()
