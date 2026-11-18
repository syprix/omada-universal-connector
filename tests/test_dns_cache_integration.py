from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.change_journal import ChangePlanJournal
from app.journal_runtime import JournalRuntime
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operator_approval import sign_approval


SITE = "a" * 24
OTHER_SITE = "b" * 24


class FakeOpenApiClient:
    def __init__(self) -> None:
        self._ref_key = b"r" * 32
        self.state: dict[str, object] = {"enable": True, "ttl": 600}
        self.read_sites: list[str] = []
        self.writes: list[tuple[str, dict[str, object]]] = []
        self.extra_read_field = False
        self.radio_state: dict[str, object] = {"radioSetting2g": {"txPowerLevel": 2}}
        self.radio_writes: list[dict[str, object]] = []

    def read_dns_cache_change_state(self, site_ref: str) -> dict[str, object]:
        self.read_sites.append(site_ref)
        if site_ref != SITE:
            raise OpenApiError("site_ref_unknown")
        state = dict(self.state)
        if self.extra_read_field:
            state["unexpected"] = "must be blocked"
        return state

    def put_dns_cache_settings(self, site_ref: str, state: dict[str, object]) -> None:
        if site_ref != SITE:
            raise OpenApiError("site_ref_unknown")
        self.writes.append((site_ref, dict(state)))
        self.state = dict(state)

    def read_ap_radio_part(self, site_ref: str, _device_ref: str, part: str) -> dict[str, object]:
        if site_ref != SITE or part != "radio_config":
            raise OpenApiError("site_ref_unknown")
        return {"data": {key: dict(value) for key, value in self.radio_state.items()}}

    def patch_ap_radio_power(self, site_ref: str, _device_ref: str,
                             changes: dict[str, object]) -> None:
        if site_ref != SITE:
            raise OpenApiError("site_ref_unknown")
        self.radio_writes.append(json.loads(json.dumps(changes)))
        self.radio_state.update(changes)


class DnsCacheIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.token = "caller-secret-do-not-log-0123456789abcdef"
        self.token_path = os.path.join(self.tempdir.name, "caller-token")
        with open(self.token_path, "w", encoding="utf-8") as handle:
            handle.write(self.token + "\n")
        self.operator_key = b"o" * 32
        self.operator_key_path = os.path.join(self.tempdir.name, "operator-approval-key")
        with open(self.operator_key_path, "wb") as handle:
            handle.write(self.operator_key)
        os.chmod(self.operator_key_path, 0o600)
        self.fake = FakeOpenApiClient()
        self.journal_dir = os.path.join(self.tempdir.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.runtime = JournalRuntime("ready", journal=ChangePlanJournal(
            self.journal_dir, controller_binding="d" * 64))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_path,
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": self.operator_key_path,
            "OMADA_ENABLE_WRITES": "false",
        })
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.fake)
        self.client_patch.start()
        self.journal_patch = patch.object(main, "_journal_runtime", return_value=self.runtime)
        self.journal_patch.start()
        self.plans_patch = patch.object(main, "_DNS_CACHE_PLANS", None)
        self.plans_patch.start()
        self.radio_plans_patch = patch.object(main, "_RADIO_PLANS", None)
        self.radio_plans_patch.start()

    def tearDown(self) -> None:
        self.radio_plans_patch.stop()
        self.plans_patch.stop()
        self.client_patch.stop()
        self.journal_patch.stop()
        self.env_patch.stop()
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.runtime.close()
        self.tempdir.cleanup()

    def post(self, path: str, body: object, *, token: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        connection.request("POST", path, body=json.dumps(body), headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def approval_body(self, preview: dict[str, object], operation: str) -> dict[str, object]:
        now = int(time.time())
        token = sign_approval(
            self.operator_key, operation=operation, plan_id=preview["plan_id"],
            plan_digest=preview["approval_request"]["digest"],
            operator_id="op_" + "2" * 24, expires_at=now + 120, now=now)
        return {"approval": token}

    def test_authenticated_preview_reads_inventory_bound_site_without_write(self) -> None:
        status, body = self.post(f"/v1/sites/{SITE}/dns/cache-preview",
                                 {"changes": {"ttl": 900}}, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["before"], {"enable": True, "ttl": 600})
        self.assertEqual(body["target"], {"enable": True, "ttl": 900})
        self.assertEqual(self.fake.read_sites, [SITE])
        self.assertEqual(self.fake.writes, [])

    def test_apply_is_disabled_by_default(self) -> None:
        status, preview = self.post(f"/v1/sites/{SITE}/dns/cache-preview",
                                    {"changes": {"enable": False}}, token=self.token)
        self.assertEqual(status, 200)
        status, body = self.post(f"/v1/dns-cache-plans/{preview['plan_id']}/apply", {}, token=self.token)
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "writes_disabled")
        self.assertEqual(self.fake.writes, [])

    def test_cached_dns_plan_rechecks_current_process_switch_before_apply(self) -> None:
        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "true"}):
            status, preview = self.post(f"/v1/sites/{SITE}/dns/cache-preview",
                                        {"changes": {"ttl": 900}}, token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(preview["writes_enabled"])

        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "false"}):
            status, body = self.post(f"/v1/dns-cache-plans/{preview['plan_id']}/apply", {}, token=self.token)
            self.assertEqual(status, 409)
            self.assertEqual(body["error"], "writes_disabled")
            status, next_preview = self.post(f"/v1/sites/{SITE}/dns/cache-preview",
                                             {"changes": {"ttl": 900}}, token=self.token)
        self.assertEqual(status, 200)
        self.assertFalse(next_preview["writes_enabled"])
        self.assertEqual(self.fake.writes, [])

    def test_cached_radio_plan_rechecks_current_process_switch_before_apply(self) -> None:
        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "true"}):
            status, preview = self.post(f"/v1/sites/{SITE}/aps/{'b' * 24}/radio-preview",
                                        {"changes": {"radioSetting2g": {"txPowerLevel": 1}}},
                                        token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(preview["writes_enabled"])

        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "false"}):
            status, body = self.post(f"/v1/radio-plans/{preview['plan_id']}/apply", {}, token=self.token)
            self.assertEqual(status, 409)
            self.assertEqual(body["error"], "writes_disabled")
            status, next_preview = self.post(f"/v1/sites/{SITE}/aps/{'b' * 24}/radio-preview",
                                             {"changes": {"radioSetting2g": {"txPowerLevel": 1}}},
                                             token=self.token)
        self.assertEqual(status, 200)
        self.assertFalse(next_preview["writes_enabled"])
        self.assertEqual(self.fake.radio_writes, [])

    def test_enabled_fixture_apply_writes_full_state_and_verifies_readback(self) -> None:
        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "true"}):
            status, preview = self.post(f"/v1/sites/{SITE}/dns/cache-preview",
                                        {"changes": {"ttl": 900}}, token=self.token)
            self.assertEqual(status, 200)
            approval_body = self.approval_body(preview, "dns-cache")
            status, result = self.post(f"/v1/dns-cache-plans/{preview['plan_id']}/apply",
                                       approval_body, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.fake.writes, [(SITE, {"enable": True, "ttl": 900})])
        self.assertEqual(self.fake.state, {"enable": True, "ttl": 900})
        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "true"}):
            status, replay = self.post(f"/v1/dns-cache-plans/{preview['plan_id']}/apply",
                                       approval_body, token=self.token)
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len(self.fake.writes), 1)

    def test_unknown_upstream_fields_and_uninventoried_site_are_refused(self) -> None:
        self.fake.extra_read_field = True
        status, body = self.post(f"/v1/sites/{SITE}/dns/cache-preview",
                                 {"changes": {"ttl": 900}}, token=self.token)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "state_invalid")
        self.assertEqual(self.fake.writes, [])

        self.fake.extra_read_field = False
        status, body = self.post(f"/v1/sites/{OTHER_SITE}/dns/cache-preview",
                                 {"changes": {"ttl": 900}}, token=self.token)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "readback_unavailable")
        self.assertEqual(self.fake.writes, [])

    def test_routes_require_auth_and_reject_unexpected_body_keys(self) -> None:
        status, body = self.post(f"/v1/sites/{SITE}/dns/cache-preview",
                                 {"changes": {"ttl": 900}})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        status, body = self.post(f"/v1/sites/{SITE}/dns/cache-preview",
                                 {"changes": {"ttl": 900}, "extra": True}, token=self.token)
        self.assertEqual(status, 400)
        self.assertEqual(self.fake.read_sites, [])

    def test_upstream_allowlist_and_exact_fixed_body(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site_known"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={}) as request:
            client.put_dns_cache_settings(SITE, {"enable": False, "ttl": 900})
        request.assert_called_once_with(
            "PUT", "/openapi/v1/ctrl/sites/site_known/setting/service/dns-cache",
            body=b'{"enable":false,"ttl":900}', token="token")

        with patch.object(client, "_connection", side_effect=AssertionError("network must not start")):
            for method, path, body in (
                ("PATCH", "/openapi/v1/ctrl/sites/site_known/setting/service/dns-cache", b'{"enable":false,"ttl":900}'),
                ("PUT", "/openapi/v1/ctrl/sites/site_known/setting/service/dns-proxy", b'{"enable":false,"ttl":900}'),
                ("PUT", "/openapi/v1/ctrl/sites/site_known/setting/service/dns-cache", b'{"enable":false}'),
                ("PUT", "/openapi/v1/ctrl/sites/site_known/setting/service/dns-cache", b'{"enable":false,"ttl":900,"extra":1}'),
                ("PUT", "/openapi/v1/ctrl/sites/site_known/setting/service/dns-cache", b'{"enable":false,"ttl":900,"ttl":800}'),
                ("PUT", "/openapi/v1/other-controller/sites/site_known/setting/service/dns-cache", b'{"enable":false,"ttl":900}'),
            ):
                with self.subTest(method=method, path=path, body=body), \
                        self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, body=body, token="token")

        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            client.put_dns_cache_settings(OTHER_SITE, {"enable": False, "ttl": 900})


if __name__ == "__main__":
    unittest.main()
