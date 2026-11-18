from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operator_approval import sign_approval


SITE = "a" * 24
SSID = "b" * 24
OTHER_SITE = "c" * 24
OTHER_SSID = "d" * 24


class FakeOpenApiClient:
    def __init__(self) -> None:
        self.config = SimpleNamespace(reference_key_file="synthetic-test-key",
                                      base_url="https://controller.example", controller_id="ctrl")
        self._ref_key = b"s" * 32
        self.enabled: object = True
        self.read_calls: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str, dict[str, bool]]] = []
        self.uncertain = False

    def read_ssid_enable_state(self, site_ref: str, ssid_ref: str) -> dict[str, bool]:
        self.read_calls.append((site_ref, ssid_ref))
        if (site_ref, ssid_ref) != (SITE, SSID):
            raise OpenApiError("ssid_ref_unknown")
        if self.enabled is None:
            return {}
        if type(self.enabled) is not bool:
            return {"ssidEnable": self.enabled}  # exercise strict callback validation
        return {"ssidEnable": self.enabled}

    def patch_ssid_enable(self, site_ref: str, ssid_ref: str, change: dict[str, bool]) -> None:
        if (site_ref, ssid_ref) != (SITE, SSID):
            raise OpenApiError("ssid_ref_unknown")
        self.writes.append((site_ref, ssid_ref, dict(change)))
        self.enabled = change["ssidEnable"]
        if self.uncertain:
            raise TimeoutError()


class SsidIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.tempdir.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
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
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_path,
            "OMADA_ENABLE_WRITES": "false",
            "OMADA_CHANGE_JOURNAL_DIR": self.journal_dir,
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": self.operator_key_path,
        })
        self.env_patch.start()
        self.runtime_patch = patch.object(main, "_JOURNAL_RUNTIME", None)
        self.runtime_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.fake)
        self.client_patch.start()
        self.plans_patch = patch.object(main, "_SSID_PLANS", None)
        self.plans_patch.start()
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None

    def tearDown(self) -> None:
        runtime = main._JOURNAL_RUNTIME
        if runtime is not None:
            runtime.close()
        self.plans_patch.stop()
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None
        self.runtime_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.tempdir.cleanup()

    def post(self, path: str, body: object, *, token: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        connection.request("POST", path, body=json.dumps(body), headers=headers)
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        return response.status, result

    def preview_path(self, site: str = SITE, ssid: str = SSID) -> str:
        return f"/v1/sites/{site}/ssids/{ssid}/enable-preview"

    def approval_body(self, preview: dict[str, object]) -> dict[str, object]:
        request = preview["approval_request"]
        return {"approval": sign_approval(
            self.operator_key, operation="ssid", plan_id=preview["plan_id"],
            plan_digest=request["digest"], operator_id="op_" + "1" * 24,
            expires_at=int(time.time()) + 120)}

    def test_authenticated_preview_is_read_only_and_apply_default_off(self) -> None:
        status, preview = self.post(self.preview_path(), {"changes": {"ssidEnable": False}}, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(preview["before"], {"ssidEnable": True})
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual(self.fake.writes, [])
        status, result = self.post(f"/v1/ssid-plans/{preview['plan_id']}/apply", {}, token=self.token)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "writes_disabled")
        self.assertEqual(self.fake.writes, [])

    def test_preview_route_requires_authentication(self) -> None:
        status, body = self.post(self.preview_path(), {"changes": {"ssidEnable": False}})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        self.assertEqual(self.fake.read_calls, [])
        self.assertEqual(self.fake.writes, [])

    def test_process_switch_is_rechecked_and_preview_reports_current_value(self) -> None:
        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "true"}):
            status, preview = self.post(self.preview_path(), {"changes": {"ssidEnable": False}}, token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(preview["writes_enabled"])
        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "false"}):
            status, result = self.post(f"/v1/ssid-plans/{preview['plan_id']}/apply",
                                       self.approval_body(preview), token=self.token)
            self.assertEqual(status, 409)
            self.assertEqual(result["error"], "writes_disabled")
            status, current_preview = self.post(self.preview_path(),
                                                {"changes": {"ssidEnable": False}}, token=self.token)
        self.assertEqual(status, 200)
        self.assertFalse(current_preview["writes_enabled"])
        self.assertEqual(self.fake.writes, [])

    def test_fixture_apply_verifies_status_and_blocks_replay(self) -> None:
        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "true"}):
            status, preview = self.post(self.preview_path(), {"changes": {"ssidEnable": False}}, token=self.token)
            self.assertEqual(status, 200)
            status, result = self.post(f"/v1/ssid-plans/{preview['plan_id']}/apply",
                                       self.approval_body(preview), token=self.token)
            self.assertEqual(status, 200)
            self.assertEqual(result["after"], {"ssidEnable": False})
            status, replay = self.post(f"/v1/ssid-plans/{preview['plan_id']}/apply",
                                       self.approval_body(preview), token=self.token)
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(self.fake.writes, [(SITE, SSID, {"ssidEnable": False})])

    def test_missing_status_foreign_refs_and_invalid_request_are_blocked(self) -> None:
        self.fake.enabled = None
        status, body = self.post(self.preview_path(), {"changes": {"ssidEnable": False}}, token=self.token)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "status_invalid")
        self.assertEqual(self.fake.writes, [])

        self.fake.enabled = True
        for path in (self.preview_path(OTHER_SITE), self.preview_path(SITE, OTHER_SSID)):
            status, body = self.post(path, {"changes": {"ssidEnable": False}}, token=self.token)
            self.assertEqual(status, 400)
            self.assertEqual(body["error"], "readback_unavailable")
        for changes in ({"ssidEnable": 0}, {"ssidEnable": False, "extra": True}, {"enable": False}):
            status, body = self.post(self.preview_path(), {"changes": changes}, token=self.token)
            self.assertEqual(status, 400)
            self.assertEqual(body["error"], "change_invalid")
        status, body = self.post(self.preview_path(), {"changes": {"ssidEnable": False}, "extra": 1}, token=self.token)
        self.assertEqual(status, 400)
        self.assertEqual(self.fake.writes, [])

    def test_uncertain_patch_is_consumed_and_never_replayed(self) -> None:
        with patch.dict(os.environ, {"OMADA_ENABLE_WRITES": "true"}):
            status, preview = self.post(self.preview_path(), {"changes": {"ssidEnable": False}}, token=self.token)
            self.assertEqual(status, 200)
            self.fake.uncertain = True
            status, result = self.post(f"/v1/ssid-plans/{preview['plan_id']}/apply",
                                       self.approval_body(preview), token=self.token)
            self.assertEqual(status, 409)
            self.assertEqual(result["error"], "change_in_doubt")
            status, replay = self.post(f"/v1/ssid-plans/{preview['plan_id']}/apply",
                                       self.approval_body(preview), token=self.token)
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len(self.fake.writes), 1)

    def test_openapi_projection_and_patch_are_exact_and_inventory_bound(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site_known"
        client._ssid_ids_by_site_ref[SITE] = {SSID: "ssid_known"}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "ssidEnable": True, "name": "private", "pskSetting": {"password": "secret"}}}) as get:
            state = client.read_ssid_enable_state(SITE, SSID)
        self.assertEqual(state, {"ssidEnable": True})
        get.assert_called_once_with("GET", "/openapi/v1/ctrl/sites/site_known/wireless-network/ssids/ssid_known", token="token")

        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={}) as request:
            client.patch_ssid_enable(SITE, SSID, {"ssidEnable": False})
        request.assert_called_once_with(
            "PATCH", "/openapi/v1/ctrl/sites/site_known/wireless-network/ssids/ssid_known/enable",
            body=b'{"ssidEnable":false}', token="token")

        with patch.object(client, "_connection", side_effect=AssertionError("network must not start")):
            for method, path, body in (
                ("PUT", "/openapi/v1/ctrl/sites/site_known/wireless-network/ssids/ssid_known/enable", b'{"ssidEnable":false}'),
                ("PATCH", "/openapi/v1/other/sites/site_known/wireless-network/ssids/ssid_known/enable", b'{"ssidEnable":false}'),
                ("PATCH", "/openapi/v1/ctrl/sites/site_known/wireless-network/ssids/ssid_known/enable", b'{"ssidEnable":0}'),
                ("PATCH", "/openapi/v1/ctrl/sites/site_known/wireless-network/ssids/ssid_known/enable", b'{"ssidEnable":false,"extra":1}'),
                ("PATCH", "/openapi/v1/ctrl/sites/site_known/wireless-network/ssids/ssid_known/enable", b'{"ssidEnable":false,"ssidEnable":true}'),
            ):
                with self.subTest(method=method, path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, body=body, token="token")

        client._site_ids_by_ref.pop(SITE)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            client.patch_ssid_enable(SITE, SSID, {"ssidEnable": False})
        client._site_ids_by_ref[SITE] = "site_known"
        client._ssid_ids_by_site_ref[SITE] = {}
        with self.assertRaisesRegex(OpenApiError, "ssid_ref_unknown"):
            client.patch_ssid_enable(SITE, SSID, {"ssidEnable": False})

    def test_detail_get_without_bool_status_is_rejected(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site_known"
        client._ssid_ids_by_site_ref[SITE] = {SSID: "ssid_known"}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {"name": "private"}}), \
                self.assertRaisesRegex(OpenApiError, "ssid_enable_state_unavailable"):
            client.read_ssid_enable_state(SITE, SSID)


if __name__ == "__main__":
    unittest.main()
