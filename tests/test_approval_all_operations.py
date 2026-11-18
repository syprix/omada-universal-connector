from __future__ import annotations

import importlib
import os
import time
import unittest
from unittest.mock import patch

from app.operator_approval import sign_approval


CASES = (
    ("tests.test_dns_cache_integration", "DnsCacheIntegrationTests", "dns-cache"),
    ("tests.test_dns_cache_integration", "DnsCacheIntegrationTests", "radio"),
    ("tests.test_ssid_integration", "SsidIntegrationTests", "ssid"),
    ("tests.test_gateway_ipv6_integration", "GatewayIpv6IntegrationTests", "gateway-ipv6"),
    ("tests.test_poe_integration", "PoeIntegrationTests", "poe"),
    ("tests.test_port_status_http", "SwitchPortStatusHttpTests", "switch-port-status"),
)


class AllOperationApprovalHttpTests(unittest.TestCase):
    """Exercise each real HTTP plan manager with local fixture callbacks only."""

    def _run_operation(self, module_name: str, class_name: str, operation: str) -> None:
        module = importlib.import_module(module_name)
        fixture_class = getattr(module, class_name)
        fixture = fixture_class(methodName="runTest")
        fixture.setUp()
        try:
            with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "true"}):
                if operation == "dns-cache":
                    preview_path = f"/v1/sites/{module.SITE}/dns/cache-preview"
                    status, preview = fixture.post(preview_path, {"changes": {"ttl": 900}},
                                                   token=fixture.token)
                    apply_path = f"/v1/dns-cache-plans/{preview['plan_id']}/apply"
                    send = lambda body: fixture.post(apply_path, body, token=fixture.token)
                    writes = lambda: fixture.fake.writes
                elif operation == "radio":
                    site, device = module.SITE, "b" * 24
                    preview_path = f"/v1/sites/{site}/aps/{device}/radio-preview"
                    status, preview = fixture.post(
                        preview_path, {"changes": {"radioSetting2g": {"txPowerLevel": 1}}},
                        token=fixture.token)
                    apply_path = f"/v1/radio-plans/{preview['plan_id']}/apply"
                    send = lambda body: fixture.post(apply_path, body, token=fixture.token)
                    writes = lambda: fixture.fake.radio_writes
                elif operation == "ssid":
                    preview_path = fixture.preview_path()
                    status, preview = fixture.post(preview_path, {"changes": {"ssidEnable": False}},
                                                   token=fixture.token)
                    apply_path = f"/v1/ssid-plans/{preview['plan_id']}/apply"
                    send = lambda body: fixture.post(apply_path, body, token=fixture.token)
                    writes = lambda: fixture.fake.writes
                elif operation == "gateway-ipv6":
                    preview_path = fixture._site_path() + "-preview"
                    status, preview = fixture.request(
                        "POST", preview_path, token=fixture.token, body={"changes": {"enable": True}})
                    apply_path = f"/v1/gateway-ipv6-plans/{preview['plan_id']}/apply"
                    send = lambda body: fixture.request("POST", apply_path, token=fixture.token, body=body)
                    writes = lambda: [call for call in fixture.transport_calls if call[0] == "PATCH"]
                elif operation == "poe":
                    preview_path = fixture._path(suffix="poe-preview")
                    status, preview = fixture.request(
                        "POST", preview_path, token=fixture.token, body={"changes": {"poeMode": 1}})
                    apply_path = f"/v1/poe-plans/{preview['plan_id']}/apply"
                    send = lambda body: fixture.request("POST", apply_path, token=fixture.token, body=body)
                    writes = lambda: [call for call in fixture.upstream if call[0] == "PUT"]
                else:
                    fixture.enable_journal()
                    preview_path = fixture.preview_path()
                    status, preview = fixture.request("POST", preview_path, {
                        "changes": {"status": 0}, "disruption_confirmed": True})
                    apply_path = f"/v1/switch-port-status-plans/{preview['plan_id']}/apply"
                    send = lambda body: fixture.request("POST", apply_path, body)
                    writes = lambda: fixture.client.write_attempts

                self.assertEqual(status, 200, (operation, preview))
                self.assertEqual(writes(), [], operation)
                missing_status, missing = send({})
                self.assertEqual(missing_status, 409, (operation, missing))
                self.assertEqual(missing["error"], "operator_approval_required")
                self.assertEqual(writes(), [], operation)

                now = int(time.time())
                approval = sign_approval(
                    fixture.operator_key, operation=operation,
                    plan_id=preview["plan_id"],
                    plan_digest=preview["approval_request"]["digest"],
                    operator_id="op_" + "9" * 24, expires_at=now + 120, now=now)
                status, result = send({"approval": approval})
                self.assertEqual(status, 200, (operation, result))
                self.assertEqual(len(writes()), 1, operation)
        finally:
            fixture.tearDown()

    def test_all_six_http_apply_branches_require_bound_approval(self) -> None:
        for module_name, class_name, operation in CASES:
            with self.subTest(operation=operation):
                self._run_operation(module_name, class_name, operation)


if __name__ == "__main__":
    unittest.main()
