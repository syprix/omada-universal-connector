from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operator_approval import sign_approval


TOKEN = "channel-limit-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
DEVICE_REF = "c" * 24
OTHER_DEVICE_REF = "d" * 24
SITE_ID = "site_123"
AP_MAC = "00:11:22:33:44:55"
OPERATOR_ID = "op_" + "5" * 24


class ChannelLimitIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.temp.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token_file = os.path.join(self.temp.name, "caller-token")
        Path(self.token_file).write_text(TOKEN, encoding="ascii")
        self.operator_key = b"o" * 32
        self.operator_key_file = os.path.join(self.temp.name, "operator-key")
        fd = os.open(self.operator_key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.operator_key)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        # The real journal requires a persistent reference key. Upstream calls
        # are intercepted by fake_request and never leave this process.
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-reference-key")
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.client._device_macs_by_site_ref[SITE_REF] = {DEVICE_REF: AP_MAC}
        self.site_result: object = {"channelLimit": {"enable": True}}
        self.ap_result: object = {
            "supportChannelLimit": True,
            "channelLimitType": 0,
            "defaultInstType5g": False,
            "defaultInstType6g": True,
        }
        self.fail_put = False
        self.put_then_timeout = False
        self.ignore_put = False
        self.transport_calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(token, "synthetic-upstream-token")
            if path == self._site_upstream_path():
                self.assertEqual(method, "GET")
                self.assertIsNone(body)
                return {"result": self.site_result}
            self.assertEqual(path, self._ap_upstream_path())
            if method == "GET":
                self.assertIsNone(body)
                return {"result": self.ap_result}
            self.assertEqual(method, "PUT")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertEqual(set(decoded), {"channelLimitType"})
            self.assertIs(type(decoded["channelLimitType"]), int)
            self.assertIn(decoded["channelLimitType"], (0, 1, 2))
            if self.put_then_timeout:
                self.ap_result = {**self.ap_result, **decoded}
                raise OpenApiError("controller_unreachable")
            if self.fail_put:
                raise OpenApiError("controller_unreachable")
            if not self.ignore_put:
                self.ap_result = {**self.ap_result, **decoded}
            return {"result": None}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_file,
            "OMADA_ENABLE_WRITES": "false",
            "OMADA_CHANGE_JOURNAL_DIR": self.journal_dir,
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": self.operator_key_file,
        })
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.runtime_patch = patch.object(main, "_JOURNAL_RUNTIME", None)
        self.runtime_patch.start()
        self.plans_patch = patch.object(main, "_AP_CHANNEL_LIMIT_PLANS", None)
        self.plans_patch.start()
        self.active_patch = patch.object(main, "_ACTIVE_APPROVAL", None)
        self.active_patch.start()
        self.consumed_patch = patch.dict(main._CONSUMED_APPROVALS, {}, clear=True)
        self.consumed_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        runtime = main._JOURNAL_RUNTIME
        if runtime is not None:
            runtime.close()
        self.plans_patch.stop()
        self.runtime_patch.stop()
        self.active_patch.stop()
        self.consumed_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.transport_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def _site_upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{SITE_ID}/channel-limit"

    @staticmethod
    def _ap_upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{SITE_ID}/aps/{AP_MAC}/channel-limit"

    @staticmethod
    def _site_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/wifi/channel-limit"

    @staticmethod
    def _ap_path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/channel-limit"

    @staticmethod
    def _preview_path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/channel-limit-preview"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None,
                raw_body: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers: dict[str, str] = {}
        encoded = raw_body
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None or raw_body is not None:
            if encoded is None:
                encoded = json.dumps(body, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {}
        connection.close()
        return response.status, result

    def approval_body(self, preview: dict[str, object]) -> dict[str, object]:
        request = preview["approval_request"]
        assert isinstance(request, dict)
        now = int(time.time())
        approval = sign_approval(
            self.operator_key, operation="ap-channel-limit", plan_id=preview["plan_id"],
            plan_digest=request["digest"], operator_id=OPERATOR_ID,
            expires_at=now + 120, now=now)
        return {"approval": approval}

    def preview(self, value: int = 2) -> dict[str, object]:
        status, result = self.request(
            "POST", self._preview_path(), token=TOKEN,
            body={"changes": {"channelLimitType": value}, "disruption_confirmed": True})
        self.assertEqual(status, 200, result)
        return result

    def test_auth_site_and_ap_gets_are_bound_and_projected(self) -> None:
        for path in (self._site_path(), self._ap_path()):
            status, unauth = self.request("GET", path)
            self.assertEqual(status, 401)
            self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, site = self.request("GET", self._site_path(), token=TOKEN)
        self.assertEqual(status, 200, site)
        self.assertEqual(site["data"], {"enable": True})
        status, ap = self.request("GET", self._ap_path(), token=TOKEN)
        self.assertEqual(status, 200, ap)
        self.assertEqual(ap["data"], {
            "supportChannelLimit": True, "channelLimitType": 0,
            "defaultInstType5g": False, "defaultInstType6g": True,
        })
        self.assertEqual(self.transport_calls, [
            ("GET", self._site_upstream_path(), None),
            ("GET", self._ap_upstream_path(), None),
        ])

        before = len(self.transport_calls)
        for path in (self._site_path(OTHER_SITE_REF), self._ap_path(OTHER_SITE_REF),
                     self._ap_path(SITE_REF, OTHER_DEVICE_REF)):
            status, result = self.request("GET", path, token=TOKEN)
            self.assertNotEqual(status, 200, result)
            self.assertNotIn(SITE_ID, json.dumps(result))
            self.assertNotIn(AP_MAC, json.dumps(result))
        self.assertEqual(len(self.transport_calls), before)

    def test_missing_or_unsupported_ap_fields_and_confirmation_fail_closed(self) -> None:
        complete = {
            "supportChannelLimit": True, "channelLimitType": 0,
            "defaultInstType5g": False, "defaultInstType6g": True,
        }
        cases = (
            {**complete, "supportChannelLimit": False},
            {k: v for k, v in complete.items() if k != "supportChannelLimit"},
            {k: v for k, v in complete.items() if k != "defaultInstType5g"},
            {**complete, "channelLimitType": 3},
            {**complete, "defaultInstType6g": 1},
            {**complete, "extra": "private"},
        )
        for value in cases:
            with self.subTest(value=value):
                self.ap_result = value
                status, _ = self.request("POST", self._preview_path(), token=TOKEN,
                    body={"changes": {"channelLimitType": 2}, "disruption_confirmed": True})
                self.assertNotEqual(status, 200)
                self.assertFalse(any(call[0] == "PUT" for call in self.transport_calls))
        self.ap_result = complete

        for body in (
            {"changes": {"channelLimitType": 2}},
            {"changes": {"channelLimitType": 2}, "disruption_confirmed": False},
            {"changes": {"channelLimitType": True}, "disruption_confirmed": True},
            {"changes": {"channelLimitType": 3}, "disruption_confirmed": True},
            {"changes": {"channelLimitType": 2, "extra": 0}, "disruption_confirmed": True},
            {"changes": {"channelLimitType": 2}, "disruption_confirmed": True, "extra": 0},
        ):
            status, result = self.request("POST", self._preview_path(), token=TOKEN, body=body)
            self.assertEqual(status, 400, (body, result))
            self.assertNotIn("plan_id", result)

    def test_disabled_missing_and_invalid_approval_then_signed_put_readback(self) -> None:
        status, unauth = self.request("POST", self._preview_path(), body={
            "changes": {"channelLimitType": 2}, "disruption_confirmed": True})
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")

        preview = self.preview(2)
        self.assertEqual(preview["before"], {
            "supportChannelLimit": True, "channelLimitType": 0,
            "defaultInstType5g": False, "defaultInstType6g": True,
        })
        self.assertEqual(preview["target"], {"channelLimitType": 2})
        apply_path = f"/v1/ap-channel-limit-plans/{preview['plan_id']}/apply"

        status, disabled = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled["error"], "writes_disabled")
        self.assertFalse(any(call[0] == "PUT" for call in self.transport_calls))

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, missing = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(missing["error"], "operator_approval_required")
        invalid = self.approval_body(preview)
        invalid["approval"]["signature"] = "0" * 64
        status, rejected = self.request("POST", apply_path, token=TOKEN, body=invalid)
        self.assertNotEqual(status, 200)
        self.assertFalse(any(call[0] == "PUT" for call in self.transport_calls))

        status, result = self.request("POST", apply_path, token=TOKEN,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["after"], {"channelLimitType": 2})
        put_calls = [call for call in self.transport_calls if call[0] == "PUT"]
        self.assertEqual(len(put_calls), 1)
        self.assertEqual(put_calls[0][1], self._ap_upstream_path())
        self.assertEqual(json.loads(put_calls[0][2]), {"channelLimitType": 2})
        status, replay = self.request("POST", apply_path, token=TOKEN,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PUT"]), 1)

    def test_stale_readback_failure_recovery_and_privacy(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        stale = self.preview(2)
        self.ap_result = {**self.ap_result, "defaultInstType5g": True}
        status, stale_result = self.request(
            "POST", f"/v1/ap-channel-limit-plans/{stale['plan_id']}/apply", token=TOKEN,
            body=self.approval_body(stale))
        self.assertEqual(status, 409)
        self.assertEqual(stale_result["error"], "state_changed")
        self.assertFalse(any(call[0] == "PUT" for call in self.transport_calls))

        self.ap_result = {"supportChannelLimit": True, "channelLimitType": 0,
                          "defaultInstType5g": False, "defaultInstType6g": True}
        failed = self.preview(2)
        self.ignore_put = True
        apply_path = f"/v1/ap-channel-limit-plans/{failed['plan_id']}/apply"
        status, unknown = self.request("POST", apply_path, token=TOKEN,
                                       body=self.approval_body(failed))
        self.assertEqual(status, 409)
        self.assertEqual(unknown["error"], "change_in_doubt")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PUT"]), 1)

        runtime = main._JOURNAL_RUNTIME
        self.assertIsNotNone(runtime)
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._AP_CHANNEL_LIMIT_PLANS = None
        status, recovered = self.request("GET", "/v1/change-plans/ap-channel-limit/in-doubt", token=TOKEN)
        self.assertEqual(status, 200, recovered)
        self.assertEqual(len(recovered["items"]), 1)
        self.assertEqual(recovered["items"][0]["plan_id"], failed["plan_id"])
        status, replay = self.request("POST", apply_path, token=TOKEN,
                                      body=self.approval_body(failed))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PUT"]), 1)

        runtime = main._JOURNAL_RUNTIME
        self.assertIsNotNone(runtime)
        journal_text = "".join(Path(self.journal_dir, name).read_text(encoding="utf-8")
                               for name in os.listdir(self.journal_dir))
        observed = json.dumps({"preview": failed, "result": unknown, "recovery": recovered}) + journal_text
        for secret in (SITE_ID, AP_MAC, TOKEN, self.operator_key.hex()):
            self.assertNotIn(secret, observed)

    def test_controller_allowlist_requires_exact_ap_path_and_body(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        path = self._ap_upstream_path()
        valid_body = b'{"channelLimitType":2}'
        connection_error = OpenApiError("connection_reached")
        with patch.object(client, "_connection", side_effect=connection_error):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", path, token="token")
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                client._request_json("PUT", path, body=valid_body, token="token")
            client._write_dispatch_guard = lambda: None
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("PUT", path, body=valid_body, token="token")
            rejected = (
                ("GET", path + "?raw=true", None),
                ("GET", self._ap_upstream_path("other-controller"), None),
                ("POST", path, valid_body),
                ("PUT", self._site_upstream_path(), b'{"channelLimit":{"enable":true}}'),
                ("PUT", path, b'{"channelLimitType":true}'),
                ("PUT", path, b'{"channelLimitType":3}'),
                ("PUT", path, b'{"channelLimitType":2,"extra":0}'),
                ("PUT", path, b'{"channelLimitType":2,"channelLimitType":1}'),
                ("PATCH", path, valid_body),
            )
            for method, rejected_path, body in rejected:
                with self.subTest(method=method, path=rejected_path, body=body), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, rejected_path, body=body, token="token")


if __name__ == "__main__":
    unittest.main()
