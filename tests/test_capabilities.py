from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest.mock import patch

from app import main
from app.change_journal import ChangePlanJournal
from app.journal_runtime import JournalRuntime
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operator_approval import sign_approval


class CapabilityStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def operation(self, name: str) -> dict[str, object]:
        return next(item for item in self.client.capabilities()["items"]
                    if item["operation"] == name)

    def test_initial_state_is_unknown_without_historical_success(self) -> None:
        caps = self.client.capabilities()
        self.assertEqual(caps["catalog_scope"], "instrumented_openapi_operations")
        self.assertIs(caps["catalog_complete"], False)
        self.assertTrue(caps["items"])
        for item in caps["items"]:
            self.assertEqual(item["support_state"], "unknown")
            self.assertEqual(item["implementation_state"], "implemented")
            self.assertEqual(item["runtime_evidence_count"], 0)
            self.assertEqual(item["controller_response_evidence_count"], 0)
            self.assertEqual(item["observed_support_states"], {})
            self.assertEqual(item["runtime_evidence"], [])

    def test_static_fallback_catalog_has_same_partial_scope(self) -> None:
        catalog = OmadaOpenApiClient.capability_catalog()
        self.assertEqual(catalog["catalog_scope"], "instrumented_openapi_operations")
        self.assertIs(catalog["catalog_complete"], False)
        self.assertTrue(catalog["items"])
        self.assertTrue(all(item["support_state"] == "unknown"
                            for item in catalog["items"]))

    def test_recovery_and_forwarding_capabilities_are_listed_once(self) -> None:
        names = ("site_intelli_recover_summary", "site_port_forwarding_summary")
        for catalog in (self.client.capabilities(), OmadaOpenApiClient.capability_catalog()):
            listed = [item["operation"] for item in catalog["items"]]
            for name in names:
                with self.subTest(catalog=catalog is not None, operation=name):
                    self.assertEqual(listed.count(name), 1)

    def test_change_preview_operations_are_implemented_but_not_live_verified(self) -> None:
        expected = {
            "ap_radio_change_preview": "POST /v1/sites/{site_ref}/aps/{device_ref}/radio-preview",
            "dns_cache_change_preview": "POST /v1/sites/{site_ref}/dns/cache-preview",
            "ssid_enable_change_preview": "POST /v1/sites/{site_ref}/ssids/{ssid_ref}/enable-preview",
        }
        items = {item["operation"]: item for item in self.client.capabilities()["items"]}
        for operation, route in expected.items():
            with self.subTest(operation=operation):
                item = items[operation]
                self.assertEqual(item["route"], route)
                self.assertEqual(item["implementation_state"], "implemented")
                self.assertEqual(item["support_state"], "unknown")
                self.assertEqual(item["runtime_evidence"], [])

    def test_success_and_failure_are_runtime_evidence(self) -> None:
        self.client._record_capability("devices", "a" * 24, None, None,
                                       response_shape_state="response_shape_supported",
                                       controller_response_observed=True)
        evidence = self.operation("devices")["runtime_evidence"][0]
        summary = self.operation("devices")
        self.assertEqual(evidence["result"], "success")
        self.assertTrue(evidence["recorded_at"].endswith("+00:00"))
        self.assertEqual(evidence["permission_state"], "allowed")
        self.assertEqual(evidence["hardware_support_state"], "unknown")
        self.assertEqual(evidence["firmware_support_state"], "unknown")
        self.assertEqual(summary["support_state"], "unknown")
        self.assertEqual(summary["runtime_evidence_count"], 1)
        self.assertEqual(summary["controller_response_evidence_count"], 1)
        self.assertEqual(summary["observed_support_states"],
                         {"live_verified_supported": 1})
        self.assertEqual(summary["observed_permission_states"], {"allowed": 1})
        self.client._record_capability("ap_radios", "a" * 24 + ":" + "b" * 24,
                                       OpenApiError("openapi_rejected", -39386), None,
                                       controller_response_observed=True)
        rejected = self.operation("ap_radios")["runtime_evidence"][0]
        self.assertEqual(rejected["failure_class"], "unknown_rejection")
        self.assertEqual(rejected["support_state"], "unknown")
        self.assertEqual(rejected["permission_state"], "unknown")
        self.assertEqual(rejected["hardware_support_state"], "unknown")
        self.assertEqual(rejected["firmware_support_state"], "unknown")
        self.assertEqual(rejected["upstream_error_code"], -39386)
        self.assertEqual(self.operation("ap_radios")["support_state"], "unknown")

    def test_permission_classification_and_target_isolation(self) -> None:
        self.client._record_capability("devices", "a" * 24,
                                       OpenApiError("openapi_permission_denied"), None,
                                       controller_response_observed=True)
        self.client._record_capability("devices", "b" * 24, None, None,
                                       response_shape_state="response_shape_supported",
                                       controller_response_observed=True)
        evidence = self.operation("devices")["runtime_evidence"]
        self.assertEqual({row["target_ref"] for row in evidence}, {"a" * 24, "b" * 24})
        denied = next(row for row in evidence if row["target_ref"] == "a" * 24)
        self.assertEqual(denied["failure_class"], "permission_denied")
        self.assertEqual(denied["support_state"], "unavailable_permission")
        self.assertEqual(denied["permission_state"], "denied")
        self.assertEqual(denied["hardware_support_state"], "unknown")
        self.assertEqual(denied["firmware_support_state"], "unknown")
        supported = next(row for row in evidence if row["target_ref"] == "b" * 24)
        self.assertEqual(supported["support_state"], "live_verified_supported")
        self.assertEqual(supported["permission_state"], "allowed")
        summary = self.operation("devices")
        self.assertEqual(summary["runtime_evidence_count"], 2)
        self.assertEqual(summary["observed_support_states"], {
            "live_verified_supported": 1, "unavailable_permission": 1})
        self.assertEqual(summary["observed_permission_states"], {
            "allowed": 1, "denied": 1})


class CapabilityRouteTests(unittest.TestCase):
    def test_route_requires_bearer_auth_and_does_not_probe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token = "caller-token-0123456789abcdef0123456789"
            token_path = os.path.join(directory, "token")
            with open(token_path, "w", encoding="utf-8") as handle:
                handle.write(token)
            class Fake:
                calls = 0
                def capabilities(self):
                    self.calls += 1
                    return {"status": "ok", "items": []}
            fake = Fake()
            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_path}), \
                    patch.object(main, "_openapi_client", return_value=fake):
                from http.client import HTTPConnection
                from http.server import ThreadingHTTPServer
                import threading
                server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    def get(auth=None):
                        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                        headers = {"Authorization": auth} if auth else {}
                        conn.request("GET", "/v1/capabilities", headers=headers)
                        response = conn.getresponse()
                        body = response.read()
                        status = response.status
                        conn.close()
                        return status, body
                    self.assertEqual(get()[0], 401)
                    self.assertEqual(fake.calls, 0)
                    status, body = get("Bearer " + token)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, b'{"items":[],"status":"ok"}')
                    self.assertEqual(fake.calls, 1)
                finally:
                    server.shutdown()
                    thread.join(timeout=2)
                    server.server_close()

    def test_radio_preview_and_disabled_apply_routes(self) -> None:
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        import json
        import threading
        with tempfile.TemporaryDirectory() as directory:
            token = "caller-token-0123456789abcdef0123456789"
            token_path = os.path.join(directory, "token")
            with open(token_path, "w", encoding="utf-8") as handle:
                handle.write(token)
            class Fake:
                writes = 0
                value = 1
                _ref_key = b"r" * 32
                def read_ap_radio_part(self, site, device, part):
                    return {"data": {"radioSetting2g": {"txPowerLevel": self.value}}}
                def patch_ap_radio_power(self, site, device, changes):
                    self.writes += 1
                    self.value = changes["radioSetting2g"]["txPowerLevel"]
            fake = Fake()
            approval_key = b"o" * 32
            approval_path = os.path.join(directory, "operator-approval-key")
            with open(approval_path, "wb") as handle:
                handle.write(approval_key)
            os.chmod(approval_path, 0o600)
            journal = ChangePlanJournal(directory, controller_binding="c" * 64)
            runtime = JournalRuntime("ready", journal=journal)
            original_plans = main._RADIO_PLANS
            main._RADIO_PLANS = None
            try:
                with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_path,
                                              "OMADA_OPERATOR_APPROVAL_KEY_FILE": approval_path,
                                              "OMADA_ENABLE_WRITES": "false"}), \
                        patch.object(main, "_openapi_client", return_value=fake), \
                        patch.object(main, "_journal_runtime", return_value=runtime):
                    server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        def post(path, payload, auth=True, content_type="application/json"):
                            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                            headers = {"Content-Type": content_type}
                            if auth:
                                headers["Authorization"] = "Bearer " + token
                            conn.request("POST", path, json.dumps(payload), headers)
                            response = conn.getresponse()
                            body = json.loads(response.read())
                            status = response.status
                            conn.close()
                            return status, body
                        route = "/v1/sites/" + "a" * 24 + "/aps/" + "b" * 24 + "/radio-preview"
                        self.assertEqual(post(route, {"changes": {"radioSetting2g": {"txPowerLevel": 0}}}, auth=False)[0], 401)
                        status, preview = post(route, {"changes": {"radioSetting2g": {"txPowerLevel": 0}}})
                        self.assertEqual(status, 200)
                        self.assertEqual(preview["previous"]["radioSetting2g"]["txPowerLevel"], 1)
                        self.assertEqual(fake.writes, 0)
                        self.assertEqual(post(route, {"changes": {}, "extra": 1})[0], 400)
                        plan_route = "/v1/radio-plans/" + preview["plan_id"] + "/apply"
                        status, body = post(plan_route, {})
                        self.assertEqual(status, 409)
                        self.assertEqual(body["error"], "writes_disabled")
                        self.assertEqual(fake.writes, 0)
                        os.environ["OMADA_ENABLE_WRITES"] = "true"
                        main._RADIO_PLANS = None
                        status, enabled_preview = post(route, {"changes": {"radioSetting2g": {"txPowerLevel": 2}}})
                        self.assertEqual(status, 200)
                        apply_route = "/v1/radio-plans/" + enabled_preview["plan_id"] + "/apply"
                        now = int(time.time())
                        approval = sign_approval(
                            approval_key, operation="radio", plan_id=enabled_preview["plan_id"],
                            plan_digest=enabled_preview["approval_request"]["digest"],
                            operator_id="op_" + "1" * 24, expires_at=now + 120, now=now)
                        status, applied = post(apply_route, {"approval": approval})
                        self.assertEqual(status, 200)
                        self.assertEqual(applied["status"], "verified")
                        self.assertEqual(fake.writes, 1)
                    finally:
                        server.shutdown()
                        thread.join(timeout=2)
                        server.server_close()
            finally:
                main._RADIO_PLANS = original_plans
                journal.close()


if __name__ == "__main__":
    unittest.main()
