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
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operator_approval import sign_approval


TOKEN = "ap-afc-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
DEVICE_REF = "c" * 24
OTHER_DEVICE_REF = "d" * 24
SITE_ID = "site_123"
AP_MAC = "00:11:22:33:44:55"
OPERATOR_ID = "op_" + "5" * 24


class ApAfcIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.temp.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as handle:
            handle.write(TOKEN)
        self.operator_key = b"o" * 32
        self.operator_key_file = os.path.join(self.temp.name, "operator-key")
        fd = os.open(self.operator_key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.operator_key)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        # Synthetic persistent reference key for the real journal. Controller
        # traffic is fully intercepted and stays in this test process.
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-reference-key")
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.client._device_macs_by_site_ref[SITE_REF] = {DEVICE_REF: AP_MAC}
        self.support_afc = True
        self.enable = False
        self.get_result: object = {"supportAfc": self.support_afc, "enable": self.enable}
        self.put_then_timeout = False
        self.fail_put = False
        self.transport_calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(path, self._upstream_path())
            self.assertEqual(token, "synthetic-upstream-token")
            if method == "GET":
                self.assertIsNone(body)
                return {"result": self.get_result}
            self.assertEqual(method, "PUT")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertEqual(set(decoded), {"enable"})
            self.assertIs(type(decoded["enable"]), bool)
            if self.put_then_timeout:
                self.enable = decoded["enable"]
                self.get_result = {"supportAfc": self.support_afc, "enable": self.enable}
                raise OpenApiError("controller_unreachable")
            if self.fail_put:
                raise OpenApiError("controller_unreachable")
            self.enable = decoded["enable"]
            self.get_result = {"supportAfc": self.support_afc, "enable": self.enable}
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
        self.plans_patch = patch.object(main, "_AP_AFC_PLANS", None, create=True)
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
    def _upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{SITE_ID}/aps/{AP_MAC}/afc-config"

    @staticmethod
    def _site_path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/afc"

    @staticmethod
    def _preview_path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/afc-preview"

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
        now = int(time.time())
        request = preview["approval_request"]
        assert isinstance(request, dict)
        approval = sign_approval(
            self.operator_key, operation="ap-afc", plan_id=preview["plan_id"],
            plan_digest=request["digest"], operator_id=OPERATOR_ID,
            expires_at=now + 120, now=now)
        return {"approval": approval}

    def preview(self, enable: bool = True) -> dict[str, object]:
        status, value = self.request(
            "POST", self._preview_path(), token=TOKEN,
            body={"changes": {"enable": enable}, "disruption_confirmed": True})
        self.assertEqual(status, 200, value)
        return value

    def test_auth_ap_site_binding_and_exact_get_projection(self) -> None:
        status, unauth = self.request("GET", self._site_path())
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, result = self.request("GET", self._site_path(), token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {"supportAfc": True, "enable": False})
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

        before = len(self.transport_calls)
        status, unknown_site = self.request("GET", self._site_path(OTHER_SITE_REF), token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(len(self.transport_calls), before)
        self.assertNotIn(SITE_ID, json.dumps(unknown_site))

        status, unknown_ap = self.request(
            "GET", self._site_path(SITE_REF, OTHER_DEVICE_REF), token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(len(self.transport_calls), before)
        self.assertNotIn(AP_MAC, json.dumps(unknown_ap))

    def test_unsupported_or_malformed_get_state_blocks_preview(self) -> None:
        bad_values: tuple[object, ...] = (
            {"supportAfc": False, "enable": False},
            {"enable": False},
            {"supportAfc": True},
            {"supportAfc": None, "enable": False},
            {"supportAfc": True, "enable": 0},
            {"supportAfc": True, "enable": False, "extra": 1},
            None,
        )
        for value in bad_values:
            with self.subTest(value=value):
                self.get_result = value
                status, get_error = self.request("GET", self._site_path(), token=TOKEN)
                if value == {"supportAfc": False, "enable": False}:
                    # A well-formed report that the AP lacks AFC is readable;
                    # the change preview itself must refuse it.
                    self.assertEqual(status, 200)
                    self.assertEqual(get_error["data"], value)
                else:
                    self.assertEqual(status, 502)
                    self.assertEqual(get_error["error"], "openapi_response_invalid")

                writes_before = len([call for call in self.transport_calls if call[0] == "PUT"])
                status, preview_error = self.request(
                    "POST", self._preview_path(), token=TOKEN,
                    body={"changes": {"enable": True}, "disruption_confirmed": True})
                self.assertNotEqual(status, 200)
                self.assertNotIn("plan_id", preview_error)
                self.assertEqual(len([call for call in self.transport_calls if call[0] == "PUT"]), writes_before)
        self.get_result = {"supportAfc": True, "enable": False}

        for body in (
            {"changes": {"enable": True}},
            {"changes": {"enable": True}, "disruption_confirmed": False},
            {"changes": {"enable": 1}, "disruption_confirmed": True},
            {"changes": {"enable": True, "extra": False}, "disruption_confirmed": True},
            {"changes": {"enable": True}, "disruption_confirmed": True, "extra": False},
        ):
            status, error = self.request("POST", self._preview_path(), token=TOKEN, body=body)
            self.assertEqual(status, 400, body)
            self.assertEqual(error.get("status"), "error")

    def test_disabled_and_missing_approval_then_put_and_readback(self) -> None:
        status, unauth = self.request(
            "POST", self._preview_path(),
            body={"changes": {"enable": True}, "disruption_confirmed": True})
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")

        preview = self.preview(True)
        self.assertEqual(preview["before"], {"supportAfc": True, "enable": False})
        self.assertEqual(preview["target"], {"enable": True})
        apply_path = f"/v1/ap-afc-plans/{preview['plan_id']}/apply"

        status, disabled = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled["error"], "writes_disabled")
        self.assertFalse(any(call[0] == "PUT" for call in self.transport_calls))

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, no_approval = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(no_approval["error"], "operator_approval_required")
        self.assertFalse(any(call[0] == "PUT" for call in self.transport_calls))

        status, applied = self.request("POST", apply_path, token=TOKEN,
                                       body=self.approval_body(preview))
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["before"], {"supportAfc": True, "enable": False})
        self.assertEqual(applied["after"], {"enable": True})
        self.assertEqual([call[0] for call in self.transport_calls],
                         ["GET", "GET", "GET", "PUT", "GET"])
        put_call = next(call for call in self.transport_calls if call[0] == "PUT")
        self.assertEqual(put_call[1], self._upstream_path())
        self.assertEqual(json.loads(put_call[2]), {"enable": True})

    def test_stale_timeout_journal_recovery_and_no_replay(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        stale_preview = self.preview(True)
        self.enable = True
        self.get_result = {"supportAfc": True, "enable": True}
        stale_path = f"/v1/ap-afc-plans/{stale_preview['plan_id']}/apply"
        status, stale = self.request("POST", stale_path, token=TOKEN,
                                     body=self.approval_body(stale_preview))
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"], "state_changed")
        self.assertFalse(any(call[0] == "PUT" for call in self.transport_calls))

        self.enable = False
        self.get_result = {"supportAfc": True, "enable": False}
        failed_preview = self.preview(True)
        failed_path = f"/v1/ap-afc-plans/{failed_preview['plan_id']}/apply"
        self.put_then_timeout = True
        status, failed = self.request("POST", failed_path, token=TOKEN,
                                      body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(failed["error"], "change_in_doubt")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PUT"]), 1)

        status, replay = self.request("POST", failed_path, token=TOKEN,
                                      body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")

        runtime = main._JOURNAL_RUNTIME
        self.assertIsNotNone(runtime)
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._AP_AFC_PLANS = None
        status, items = self.request("GET", "/v1/change-plans/ap-afc/in-doubt", token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(len(items["items"]), 1)
        self.assertEqual(items["items"][0]["plan_id"], failed_preview["plan_id"])
        self.assertEqual(items["items"][0]["state"], "in_doubt")

        status, recovered_replay = self.request(
            "POST", failed_path, token=TOKEN, body=self.approval_body(failed_preview))
        self.assertEqual(status, 409)
        self.assertEqual(recovered_replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PUT"]), 1)

    def test_controller_allowlist_is_limited_to_exact_path_method_and_body(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        path = self._upstream_path()
        valid_body = b'{"enable":true}'
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
                ("GET", self._upstream_path("other-controller"), None),
                ("POST", path, valid_body),
                ("PUT", path, b'{"enable":1}'),
                ("PUT", path, b'{"enable":true,"extra":0}'),
                ("PUT", path, b'{"enable":true,"enable":false}'),
                ("PUT", path, b'true'),
                ("PATCH", path, valid_body),
            )
            for method, rejected_path, body in rejected:
                with self.subTest(method=method, path=rejected_path, body=body), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, rejected_path, body=body, token="token")


if __name__ == "__main__":
    unittest.main()
