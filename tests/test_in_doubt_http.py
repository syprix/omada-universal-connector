from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import StringIO
from unittest.mock import patch

from app import main
from app.change_journal import ChangePlanJournal
from app.journal_runtime import JournalRuntime
from app.changes import ChangeError, RadioChangePlans
from app.dns_cache_changes import DnsCacheChangeError, DnsCacheChangePlans
from app.gateway_ipv6_changes import GatewayIpv6ChangeError, GatewayIpv6IpPassthroughPlans
from app.ssid_changes import SsidChangeError, SsidChangePlans


TOKEN = "in-doubt-caller-token-with-at-least-32-characters"
SITE = "a" * 24
DEVICE = "b" * 24
SSID = "c" * 24
GATEWAY = "d" * 24
PLAN_IDS = {
    "radio": "1" * 48,
    "dns-cache": "2" * 48,
    "ssid": "3" * 48,
    "gateway-ipv6": "4" * 48,
}


class InDoubtHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.tempdir.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.operator_key_file = os.path.join(self.tempdir.name, "operator-approval-key")
        with open(self.operator_key_file, "wb") as stream:
            stream.write(b"o" * 32)
        os.chmod(self.operator_key_file, 0o600)
        self.reads: list[tuple[str, tuple[object, ...]]] = []
        self.writes: list[tuple[str, tuple[object, ...]]] = []

        def reader(kind: str):
            def read(*args):
                self.reads.append((kind, args))
                raise OSError("fixture read failure")
            return read

        def writer(kind: str):
            def write(*args):
                self.writes.append((kind, args))
            return write

        self.managers = {
            "radio": RadioChangePlans(reader("radio"), writer("radio"), writes_enabled=True),
            "dns-cache": DnsCacheChangePlans(reader("dns-cache"), writer("dns-cache"), writes_enabled=True),
            "ssid": SsidChangePlans(reader("ssid"), writer("ssid"), writes_enabled=True),
            "gateway-ipv6": GatewayIpv6IpPassthroughPlans(
                reader("gateway-ipv6"), writer("gateway-ipv6"), writes_enabled=True),
        }
        self.error_types = {
            "radio": ChangeError,
            "dns-cache": DnsCacheChangeError,
            "ssid": SsidChangeError,
            "gateway-ipv6": GatewayIpv6ChangeError,
        }
        self.managers["radio"].plans[PLAN_IDS["radio"]] = {
            "target": (SITE, DEVICE), "changes": {"radioSetting2g": {"txPowerLevel": 0}},
            "previous": {"radioSetting2g": {"txPowerLevel": 1}}, "state": "in_doubt"}
        self.managers["dns-cache"].plans[PLAN_IDS["dns-cache"]] = {
            "site_ref": SITE, "before": {"enable": True, "ttl": 600},
            "target": {"enable": False, "ttl": 600}, "state": "in_doubt"}
        self.managers["ssid"].plans[PLAN_IDS["ssid"]] = {
            "target_refs": (SITE, SSID), "before": {"ssidEnable": True},
            "target": {"ssidEnable": False}, "state": "in_doubt"}
        self.managers["gateway-ipv6"].plans[PLAN_IDS["gateway-ipv6"]] = {
            "site_ref": SITE, "gateway_ref": GATEWAY, "before": {"enable": False},
            "target": {"enable": True}, "state": "in_doubt"}

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_file,
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": self.operator_key_file,
            "OMADA_ENABLE_WRITES": "true",
            "OMADA_CHANGE_JOURNAL_DIR": "",
        })
        self.env_patch.start()
        class FixtureClient:
            _ref_key = b"r" * 32
        self.client_patch = patch.object(main, "_openapi_client", return_value=FixtureClient())
        self.client_patch.start()
        self.journal = ChangePlanJournal(self.tempdir.name, controller_binding="f" * 64)
        self.runtime_patch = patch.object(main, "_JOURNAL_RUNTIME", JournalRuntime("ready", self.journal))
        self.runtime_patch.start()
        self.manager_patches = [
            patch.object(main, "_RADIO_PLANS", self.managers["radio"]),
            patch.object(main, "_DNS_CACHE_PLANS", self.managers["dns-cache"]),
            patch.object(main, "_SSID_PLANS", self.managers["ssid"]),
            patch.object(main, "_GATEWAY_IPV6_PLANS", self.managers["gateway-ipv6"]),
        ]
        for item in self.manager_patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.manager_patches):
            item.stop()
        self.runtime_patch.stop()
        self.journal.close()
        self.client_patch.stop()
        self.env_patch.stop()
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.tempdir.cleanup()

    def request(self, method: str, path: str, body: object | None = None,
                *, authorized: bool = True) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {}
        data = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            data = json.dumps(body if body is not None else {}).encode()
        if authorized:
            headers["Authorization"] = "Bearer " + TOKEN
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        return response.status, result

    def test_authenticated_lists_and_inspects_all_four_managers_read_only(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            for kind, plan_id in PLAN_IDS.items():
                status, listed = self.request("GET", f"/v1/change-plans/{kind}/in-doubt")
                self.assertEqual(status, 200)
                self.assertEqual(listed["items"][0]["plan_id"], plan_id)
                self.assertEqual(listed["items"][0]["outcome"], "unknown")

                status, inspected = self.request("GET", f"/v1/change-plans/{kind}/{plan_id}")
                self.assertEqual(status, 200)
                self.assertEqual(inspected["plan_id"], plan_id)
                self.assertEqual(inspected["status"], "ok")
                self.assertEqual(inspected["outcome"], "unknown")
                self.assertNotEqual(inspected.get("outcome"), "verified")
                self.assertEqual(inspected["current_observation"]["status"], "unavailable")

        self.assertEqual(len(self.reads), 4)
        self.assertEqual(self.writes, [])
        logged = output.getvalue()
        for opaque in (SITE, DEVICE, SSID, GATEWAY, *PLAN_IDS.values()):
            self.assertNotIn(opaque, logged)
        self.assertIn("/v1/change-plans/<kind>/<plan>", logged)

    def test_close_requires_exact_confirmation_preserves_unknown_and_blocks_replay(self) -> None:
        status, body = self.request("POST", f"/v1/change-plans/ssid/{PLAN_IDS['ssid']}/close",
                                    {"confirmation": "verified"})
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "operator_confirmation_required")
        self.assertIn(PLAN_IDS["ssid"], self.managers["ssid"].plans)

        for kind, plan_id in PLAN_IDS.items():
            status, result = self.request(
                "POST", f"/v1/change-plans/{kind}/{plan_id}/close",
                {"confirmation": "outcome_unknown_no_retry"})
            self.assertEqual(status, 200)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["state"], "closed_outcome_unknown")
            self.assertEqual(result["outcome"], "unknown")
            status, replay = self.request("POST", self.apply_path(kind, plan_id), {})
            self.assertEqual(status, 409)
            self.assertEqual(replay["error"], "operator_approval_required")

        self.assertEqual(self.writes, [])

    @staticmethod
    def apply_path(kind: str, plan_id: str) -> str:
        routes = {
            "radio": f"/v1/radio-plans/{plan_id}/apply",
            "dns-cache": f"/v1/dns-cache-plans/{plan_id}/apply",
            "ssid": f"/v1/ssid-plans/{plan_id}/apply",
            "gateway-ipv6": f"/v1/gateway-ipv6-plans/{plan_id}/apply",
        }
        return routes[kind]

    def test_auth_unknown_kinds_and_unknown_ids_are_rejected(self) -> None:
        status, body = self.request("GET", f"/v1/change-plans/radio/in-doubt", authorized=False)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        status, body = self.request(
            "POST", f"/v1/change-plans/radio/{PLAN_IDS['radio']}/close",
            {"confirmation": "outcome_unknown_no_retry"}, authorized=False)
        self.assertEqual(status, 401)
        self.assertIn(PLAN_IDS["radio"], self.managers["radio"].plans)
        status, body = self.request("GET", "/v1/change-plans/unknown/in-doubt")
        self.assertEqual(status, 404)
        status, body = self.request("GET", f"/v1/change-plans/radio/{'f' * 48}")
        self.assertEqual(status, 404)
        status, body = self.request("POST", f"/v1/change-plans/unknown/{'f' * 48}/close",
                                    {"confirmation": "outcome_unknown_no_retry"})
        self.assertEqual(status, 404)
        self.assertEqual(self.writes, [])

    def test_close_rejects_extra_confirmation_fields(self) -> None:
        status, body = self.request("POST", f"/v1/change-plans/dns-cache/{PLAN_IDS['dns-cache']}/close",
                                    {"confirmation": "outcome_unknown_no_retry", "extra": True})
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "operator_confirmation_required")
        self.assertIn(PLAN_IDS["dns-cache"], self.managers["dns-cache"].plans)
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
