from __future__ import annotations

import io
import builtins
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


SITE_REF = "a" * 24
GATEWAY_REF = "b" * 24
GATEWAY_MAC = "AA-BB-CC-DD-EE-FF"


class GatewayIpv6IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.tempdir.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token = "fixture-caller-token-0123456789abcdef"
        self.token_file = os.path.join(self.tempdir.name, "caller-token")
        with open(self.token_file, "w", encoding="utf-8") as handle:
            handle.write(self.token)
        self.operator_key = b"o" * 32
        self.operator_key_file = os.path.join(self.tempdir.name, "operator-approval-key")
        with open(self.operator_key_file, "wb") as handle:
            handle.write(self.operator_key)
        os.chmod(self.operator_key_file, 0o600)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        self.client._ref_key = b"g" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-test-key")
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._gateway_macs_by_site_ref[SITE_REF] = {GATEWAY_REF: GATEWAY_MAC}
        self.enabled = False
        self.transport_calls: list[tuple[str, str, bytes | None]] = []
        self.fail_patch = False

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(token, "fixture-upstream-token")
            if method == "GET":
                return {"result": {"enable": self.enabled}}
            self.assertEqual(method, "PATCH")
            self.assertEqual(path, self._upstream_path())
            self.assertIsNotNone(body)
            decoded = json.loads(body)
            self.assertEqual(set(decoded), {"enable"})
            self.assertIs(type(decoded["enable"]), bool)
            if self.fail_patch:
                raise OpenApiError("controller_unreachable")
            self.enabled = decoded["enable"]
            return {"result": None}

        self.request_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.request_patch.start()
        self.access_patch = patch.object(self.client, "_access_token", return_value="fixture-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_file,
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": self.operator_key_file,
            "OMADA_ENABLE_WRITES": "false",
            "OMADA_CHANGE_JOURNAL_DIR": self.journal_dir,
        })
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.runtime_patch = patch.object(main, "_JOURNAL_RUNTIME", None)
        self.runtime_patch.start()
        self.plan_patch = patch.object(main, "_GATEWAY_IPV6_PLANS", None)
        self.plan_patch.start()
        self.logs = io.StringIO()
        self.log_patch = patch.object(builtins, "print",
                                      lambda *args, **_kwargs: self.logs.write(" ".join(map(str, args)) + "\n"))
        self.log_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.log_patch.stop()
        self.plan_patch.stop()
        runtime = main._JOURNAL_RUNTIME
        if runtime is not None:
            runtime.close()
        self.runtime_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.request_patch.stop()
        self.tempdir.cleanup()

    @staticmethod
    def _upstream_path(controller_id: str = "ctrl") -> str:
        return (f"/openapi/v1/{controller_id}/sites/site_1/gateways/{GATEWAY_MAC}"
                "/network/ipv6")

    @staticmethod
    def _site_path(site_ref: str = SITE_REF, gateway_ref: str = GATEWAY_REF) -> str:
        return f"/v1/sites/{site_ref}/gateways/{gateway_ref}/ipv6-ip-passthrough"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers: dict[str, str] = {}
        encoded = None
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            # BaseHTTPRequestHandler emits HTML for genuinely unmapped routes (501).
            value = {}
        connection.close()
        return response.status, value

    def approval_body(self, preview: dict[str, object]) -> dict[str, object]:
        now = int(time.time())
        token = sign_approval(
            self.operator_key, operation="gateway-ipv6", plan_id=preview["plan_id"],
            plan_digest=preview["approval_request"]["digest"],
            operator_id="op_" + "3" * 24, expires_at=now + 120, now=now)
        return {"approval": token}

    def test_get_is_authenticated_inventory_scoped_and_redacted(self) -> None:
        status, body = self.request("GET", self._site_path())
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, result = self.request("GET", self._site_path(), token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["scope"], "gateway_ipv6_ip_passthrough")
        self.assertEqual(result["data"], {"enable": False})
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

        mcp_request = {"jsonrpc": "2.0", "id": 31, "method": "tools/call",
                       "params": {"name": "omada_gateway_ipv6_ip_passthrough",
                                  "arguments": {"site_ref": SITE_REF,
                                                "gateway_ref": GATEWAY_REF}}}
        status, mcp_result = self.request("POST", "/mcp", token=self.token,
                                          body=mcp_request)
        self.assertEqual(status, 200)
        self.assertFalse(mcp_result["result"]["isError"])
        self.assertEqual(mcp_result["result"]["structuredContent"]["data"],
                         {"enable": False})
        self.assertEqual(self.transport_calls,
                         [("GET", self._upstream_path(), None)] * 2)
        for bad_path, expected_error in (
            (self._site_path("c" * 24), "site_ref_unknown"),
            (self._site_path(gateway_ref="d" * 24), "gateway_ref_unknown"),
        ):
            before = len(self.transport_calls)
            status, error = self.request("GET", bad_path, token=self.token)
            self.assertEqual(status, 502)
            self.assertEqual(error.get("error"), expected_error)
            self.assertEqual(len(self.transport_calls), before)
        before = len(self.transport_calls)
        status, error = self.request(
            "GET", "/v1/sites/not-a-ref/gateways/" + GATEWAY_REF + "/ipv6-ip-passthrough",
            token=self.token)
        self.assertEqual(status, 404)
        self.assertEqual(error.get("error"), "not_found")
        self.assertEqual(len(self.transport_calls), before)
        self.assertNotIn(GATEWAY_MAC, self.logs.getvalue())
        self.assertNotIn("site_1", self.logs.getvalue())
        self.assertNotIn(SITE_REF, self.logs.getvalue())
        self.assertNotIn(GATEWAY_REF, self.logs.getvalue())

    def test_fixed_upstream_path_pins_controller_and_boolean_body(self) -> None:
        other = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        good = self._upstream_path()
        marker = OpenApiError("connection_reached")
        with patch.object(other, "_connection", side_effect=marker):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                other._request_json("GET", good, token="token")
            # Writes are allowed by the route/body allowlist only when the
            # caller also supplies the one-shot operator dispatch guard.
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                other._request_json("PATCH", good, body=b'{"enable":true}', token="token")
            other._write_dispatch_guard = lambda: None
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                other._request_json("PATCH", good, body=b'{"enable":true}', token="token")
            for method, path, body in (
                ("GET", self._upstream_path("foreign_controller"), None),
                ("GET", good + "?raw=true", None),
                ("POST", good, b'{"enable":true}'),
                ("PATCH", good, b'{"enable":1}'),
                ("PATCH", good, b'{"enable":true,"mode":1}'),
                ("PATCH", good, b'{"enable":true,"enable":false}'),
                ("PATCH", self._upstream_path("foreign_controller"), b'{"enable":true}'),
            ):
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    other._request_json(method, path, body=body, token="token")

    def test_preview_default_off_apply_verify_replay_and_capability(self) -> None:
        preview_path = self._site_path() + "-preview"
        status, unauth = self.request("POST", preview_path,
                                      body={"changes": {"enable": True}})
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, preview = self.request("POST", preview_path, token=self.token,
                                       body={"changes": {"enable": True}})
        self.assertEqual(status, 200)
        self.assertEqual(preview["scope"], "gateway_ipv6_ip_passthrough")
        self.assertEqual(preview["before"], {"enable": False})
        self.assertEqual(preview["target"], {"enable": True})
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual([call[0] for call in self.transport_calls], ["GET"])

        apply_path = f"/v1/gateway-ipv6-plans/{preview['plan_id']}/apply"
        status, disabled = self.request("POST", apply_path, token=self.token, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled["error"], "writes_disabled")
        self.assertEqual(len(self.transport_calls), 1)

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, next_preview = self.request("POST", preview_path, token=self.token,
                                            body={"changes": {"enable": True}})
        self.assertEqual(status, 200)
        apply_path = f"/v1/gateway-ipv6-plans/{next_preview['plan_id']}/apply"
        approval_body = self.approval_body(next_preview)
        status, applied = self.request("POST", apply_path, token=self.token, body=approval_body)
        self.assertEqual(status, 200)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["after"], {"enable": True})
        self.assertEqual([call[0] for call in self.transport_calls],
                         ["GET", "GET", "GET", "GET", "PATCH", "GET"])
        patch_calls = [call for call in self.transport_calls if call[0] == "PATCH"]
        self.assertEqual(len(patch_calls), 1)
        self.assertEqual(json.loads(patch_calls[0][2]), {"enable": True})

        status, replay = self.request("POST", apply_path, token=self.token, body=approval_body)
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PATCH"]), 1)

        status, capabilities = self.request("GET", "/v1/capabilities", token=self.token)
        self.assertEqual(status, 200)
        operations = {item["operation"]: item for item in capabilities["items"]}
        self.assertEqual(operations["gateway_ipv6_ip_passthrough"]["runtime_evidence"][0]["result"],
                         "success")
        preview_cap = operations["gateway_ipv6_ip_passthrough_preview"]
        self.assertEqual(preview_cap["support_state"], "unknown")
        self.assertEqual(preview_cap["runtime_evidence"], [])
        for sensitive in (SITE_REF, GATEWAY_REF, GATEWAY_MAC, next_preview["plan_id"]):
            self.assertNotIn(sensitive, self.logs.getvalue())

    def test_uncertain_patch_is_in_doubt_once_and_replay_is_blocked(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        self.fail_patch = True
        preview_path = self._site_path() + "-preview"
        status, preview = self.request("POST", preview_path, token=self.token,
                                       body={"changes": {"enable": True}})
        self.assertEqual(status, 200)
        apply_path = f"/v1/gateway-ipv6-plans/{preview['plan_id']}/apply"
        approval_body = self.approval_body(preview)
        status, uncertain = self.request("POST", apply_path, token=self.token, body=approval_body)
        self.assertEqual(status, 409)
        self.assertEqual(uncertain["error"], "change_in_doubt")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PATCH"]), 1)
        status, replay = self.request("POST", apply_path, token=self.token, body=approval_body)
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.transport_calls if call[0] == "PATCH"]), 1)

    def test_preview_rejects_extra_fields_and_unknown_routes(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        preview_path = self._site_path() + "-preview"
        for body in ({"changes": {"enable": 1}}, {"changes": {"enable": True, "other": 2}},
                     {"enable": True}, {"changes": {"enable": True}, "extra": 1}):
            with self.subTest(body=body):
                status, error = self.request("POST", preview_path, token=self.token, body=body)
                self.assertIn(status, (400, 502))
                self.assertNotEqual(error.get("status"), "ok")
        status, error = self.request("POST", "/v1/gateway-ipv6-plans/not-a-plan/apply",
                                     token=self.token, body={})
        self.assertEqual(status, 501)
        self.assertNotEqual(error.get("status"), "ok")
        self.assertFalse(any(call[0] == "PATCH" for call in self.transport_calls))


if __name__ == "__main__":
    unittest.main()
