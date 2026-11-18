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


TOKEN = "site-lldp-integration-caller-token-0123456789"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
SITE_ID = "site_123"
OPERATOR_ID = "op_" + "6" * 24


class SiteLldpIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.temp.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as handle:
            handle.write(TOKEN)
        self.operator_key = b"l" * 32
        self.operator_key_file = os.path.join(self.temp.name, "operator-key")
        fd = os.open(self.operator_key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.operator_key)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-reference-key")
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.enabled = False
        self.get_result: object = {"lldp": {"enable": self.enabled}}
        self.fail_patch = False
        self.patch_then_timeout = False
        self.readback_mismatch = False
        self.calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.calls.append((method, path, body))
            self.assertEqual(path, self._controller_path())
            self.assertEqual(token, "synthetic-upstream-token")
            if method == "GET":
                self.assertIsNone(body)
                return {"result": self.get_result}
            self.assertEqual(method, "PATCH")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertEqual(decoded, {"lldp": {"enable": not self.enabled}})
            if self.patch_then_timeout:
                self.enabled = decoded["lldp"]["enable"]
                self.get_result = {"lldp": {"enable": self.enabled}}
                raise OpenApiError("controller_unreachable")
            if self.fail_patch:
                raise OpenApiError("controller_unreachable")
            if not self.readback_mismatch:
                self.enabled = decoded["lldp"]["enable"]
                self.get_result = {"lldp": {"enable": self.enabled}}
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
        self.plans_patch = patch.object(main, "_SITE_LLDP_PLANS", None, create=True)
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
    def _controller_path(controller_id: str = "ctrl", site_id: str = SITE_ID) -> str:
        return f"/openapi/v1/{controller_id}/sites/{site_id}/lldp"

    @staticmethod
    def _read_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/lldp"

    @staticmethod
    def _preview_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/lldp-preview"

    def request(self, method: str, path: str, *, token: str | None = TOKEN,
                body: dict[str, object] | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers: dict[str, str] = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        encoded = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            encoded = json.dumps(body, separators=(",", ":"))
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        connection.close()
        return response.status, value

    def approval_body(self, preview: dict[str, object]) -> dict[str, object]:
        now = int(time.time())
        summary = preview["approval_request"]
        assert isinstance(summary, dict)
        return {"approval": sign_approval(
            self.operator_key, operation="site-lldp", plan_id=preview["plan_id"],
            plan_digest=summary["digest"], operator_id=OPERATOR_ID,
            expires_at=now + 120, now=now)}

    def preview(self, enable: bool = True, *, confirmed: bool = True):
        return self.request("POST", self._preview_path(), body={
            "changes": {"enable": enable}, "disruption_confirmed": confirmed})

    def test_auth_known_site_exact_get_and_schema_validation(self) -> None:
        status, unauthorized = self.request("GET", self._read_path(), token=None)
        self.assertEqual(status, 401)
        self.assertEqual(unauthorized["error"], "unauthorized")
        self.assertEqual(self.calls, [])

        status, result = self.request("GET", self._read_path())
        self.assertEqual(status, 200, result)
        self.assertEqual(result["data"], {"enable": False})
        self.assertEqual(self.calls, [("GET", self._controller_path(), None)])

        for malformed in ({}, {"lldp": {}}, {"lldp": {"enable": False, "extra": 1}},
                          {"lldp": {"enable": 0}}, {"extra": 1, "lldp": {"enable": False}}):
            self.get_result = malformed
            status, failure = self.request("GET", self._read_path())
            self.assertEqual(status, 502, malformed)
            self.assertEqual(failure["error"], "openapi_response_invalid")

    def test_unknown_site_and_wrong_methods_or_paths_never_read(self) -> None:
        status, _result = self.request("GET", self._read_path(OTHER_SITE_REF))
        self.assertNotEqual(status, 200)
        status, _result = self.request("GET", self._read_path() + "/extra")
        self.assertNotEqual(status, 200)
        status, _result = self.request("PUT", self._read_path())
        self.assertNotEqual(status, 200)
        self.assertEqual(self.calls, [])

    def test_preview_requires_exact_shape_and_explicit_disruption_confirmation(self) -> None:
        for body in (
            {"changes": {"enable": True}},
            {"changes": {"enable": True}, "disruption_confirmed": False},
            {"changes": {"enable": True}, "disruption_confirmed": 1},
            {"changes": {"enable": True}, "disruption_confirmed": True, "extra": 0},
            {"changes": {"enable": 1}, "disruption_confirmed": True},
        ):
            status, result = self.request("POST", self._preview_path(), body=body)
            self.assertNotEqual(status, 200, body)
            self.assertNotIn("plan_id", result)
        self.assertFalse(any(method == "PATCH" for method, _path, _body in self.calls))

    def test_default_off_then_signed_approved_patch_readback_and_no_replay(self) -> None:
        status, preview = self.preview()
        self.assertEqual(status, 200, preview)
        self.assertEqual(preview["before"], {"enable": False})
        self.assertEqual(preview["target"], {"enable": True})
        apply_path = f"/v1/site-lldp-plans/{preview['plan_id']}/apply"

        status, disabled = self.request("POST", apply_path, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled["error"], "writes_disabled")
        self.assertFalse(any(method == "PATCH" for method, _path, _body in self.calls))

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, no_approval = self.request("POST", apply_path, body={})
        self.assertEqual(status, 409)
        self.assertEqual(no_approval["error"], "operator_approval_required")
        self.assertFalse(any(method == "PATCH" for method, _path, _body in self.calls))

        status, applied = self.request("POST", apply_path, body=self.approval_body(preview))
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["after"], {"enable": True})
        self.assertEqual([method for method, _path, _body in self.calls],
                         ["GET", "GET", "GET", "PATCH", "GET"])
        patch_call = next(call for call in self.calls if call[0] == "PATCH")
        self.assertEqual(patch_call[1], self._controller_path())
        self.assertEqual(json.loads(patch_call[2]), {"lldp": {"enable": True}})

        status, replay = self.request("POST", apply_path, body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertFalse(any(method == "PATCH" for method, _path, _body in self.calls[5:]))

    def test_stale_plan_and_readback_mismatch_never_claim_verified_write(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, stale_preview = self.preview()
        self.assertEqual(status, 200, stale_preview)
        self.enabled = True
        self.get_result = {"lldp": {"enable": True}}
        status, stale = self.request(
            "POST", f"/v1/site-lldp-plans/{stale_preview['plan_id']}/apply",
            body=self.approval_body(stale_preview))
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"], "state_changed")
        self.assertFalse(any(method == "PATCH" for method, _path, _body in self.calls))

        self.enabled = False
        self.get_result = {"lldp": {"enable": False}}
        status, mismatch_preview = self.preview()
        self.assertEqual(status, 200, mismatch_preview)
        self.readback_mismatch = True
        status, mismatch = self.request(
            "POST", f"/v1/site-lldp-plans/{mismatch_preview['plan_id']}/apply",
            body=self.approval_body(mismatch_preview))
        self.assertEqual(status, 409)
        self.assertEqual(mismatch["error"], "change_in_doubt")
        self.assertEqual(len([call for call in self.calls if call[0] == "PATCH"]), 1)

    def test_timeout_journal_recovery_and_replay_block(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, preview = self.preview()
        self.assertEqual(status, 200, preview)
        apply_path = f"/v1/site-lldp-plans/{preview['plan_id']}/apply"
        self.patch_then_timeout = True
        status, failure = self.request("POST", apply_path, body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(failure["error"], "change_in_doubt")
        self.assertEqual(len([call for call in self.calls if call[0] == "PATCH"]), 1)

        runtime = main._JOURNAL_RUNTIME
        self.assertIsNotNone(runtime)
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._SITE_LLDP_PLANS = None
        status, items = self.request("GET", "/v1/change-plans/site-lldp/in-doubt")
        self.assertEqual(status, 200, items)
        self.assertEqual(len(items["items"]), 1)
        self.assertEqual(items["items"][0]["plan_id"], preview["plan_id"])
        self.assertEqual(items["items"][0]["state"], "in_doubt")

        status, replay = self.request("POST", apply_path, body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertFalse(any(method == "PATCH" for method, _path, _body in self.calls[4:]))

    def test_controller_allowlist_requires_guard_and_rejects_other_path_method_body(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        path = self._controller_path()
        good = b'{"lldp":{"enable":true}}'
        reached = OpenApiError("connection_reached")
        with patch.object(client, "_connection", side_effect=reached):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", path, token="token")
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                client._request_json("PATCH", path, body=good, token="token")
            client._write_dispatch_guard = lambda: None
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("PATCH", path, body=good, token="token")
            rejected = (
                ("POST", path, good),
                ("PATCH", path, b'{"lldp":{"enable":1}}'),
                ("PATCH", path, b'{"lldp":{"enable":true},"extra":1}'),
                ("PATCH", path + "?x=1", good),
                ("PATCH", self._controller_path("other-controller"), good),
            )
            for method, target, body in rejected:
                with self.subTest(method=method, target=target), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, target, body=body, token="token")


if __name__ == "__main__":
    unittest.main()
