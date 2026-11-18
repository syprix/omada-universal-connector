from __future__ import annotations

import builtins
import io
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
SWITCH_REF = "b" * 24
SWITCH_MAC = "AA-BB-CC-DD-EE-FF"
PORT = 7


class PoeIntegrationTests(unittest.TestCase):
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
        self.client._ref_key = b"p" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-test-key")
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._switch_macs_by_site_ref[SITE_REF] = {SWITCH_REF: SWITCH_MAC}
        self.rows = [{"switchMac": SWITCH_MAC, "port": PORT, "poe": 0,
                      "supportPoe": True, "profileOverrideEnable": True}]
        self.upstream: list[tuple[str, str, bytes | None]] = []
        self.fail_put = False

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.upstream.append((method, path, body))
            self.assertEqual(token, "fixture-upstream-token")
            if method == "GET":
                page_size = self.client.config.page_size
                page = int(path.partition("?page=")[2].split("&", 1)[0])
                start = (page - 1) * page_size
                data = self.rows[start:start + page_size]
                return {"result": {"data": data, "totalRows": len(self.rows),
                                    "currentPage": page,
                                    "currentSize": len(data)}}
            self.assertEqual(method, "PUT")
            expected_path = ("/openapi/v1/ctrl/sites/site_1/switches/AA-BB-CC-DD-EE-FF"
                             f"/ports/{PORT}/poe-mode")
            self.assertEqual(path, expected_path)
            self.assertIsNotNone(body)
            parsed = json.loads(body)
            self.assertEqual(set(parsed), {"poeMode"})
            self.assertIs(type(parsed["poeMode"]), int)
            self.assertIn(parsed["poeMode"], (0, 1))
            if self.fail_put:
                raise OpenApiError("controller_unreachable")
            self.rows[0]["poe"] = parsed["poeMode"]
            return {"result": None}

        self.request_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.request_patch.start()
        self.access_patch = patch.object(self.client, "_access_token",
                                          return_value="fixture-upstream-token")
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
        self.plan_patch = patch.object(main, "_POE_PLANS", None)
        self.plan_patch.start()
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None
        self.logs = io.StringIO()
        self.log_patch = patch.object(builtins, "print",
                                      lambda *args, **_kwargs: self.logs.write(
                                          " ".join(map(str, args)) + "\n"))
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
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None
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
    def _path(site_ref: str = SITE_REF, switch_ref: str = SWITCH_REF,
              port: int = PORT, suffix: str = "poe") -> str:
        return f"/v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/{suffix}"

    def test_ambiguous_switch_mac_blocks_poe_read_and_write_before_io(self) -> None:
        self.client._switch_macs_by_site_ref[SITE_REF]["c" * 24] = SWITCH_MAC.lower()
        self.upstream.clear()
        with self.assertRaisesRegex(OpenApiError, "switch_ref_ambiguous"):
            self.client.read_switch_port_poe_state(SITE_REF, SWITCH_REF, PORT)
        with self.assertRaisesRegex(OpenApiError, "switch_ref_ambiguous"):
            self.client.put_switch_port_poe_mode(
                SITE_REF, SWITCH_REF, PORT, {"poeMode": 0})
        self.assertEqual(self.upstream, [])

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
        return {"approval": sign_approval(
            self.operator_key, operation="poe", plan_id=preview["plan_id"],
            plan_digest=request["digest"], operator_id="op_" + "2" * 24,
            expires_at=int(time.time()) + 120)}

    def test_get_auth_inventory_scope_and_redacted_projection(self) -> None:
        status, body = self.request("GET", self._path())
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        self.assertEqual(self.upstream, [])

        status, result = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], {"poe": 0, "supportPoe": True,
                                          "profileOverrideEnable": True})
        self.assertEqual([call[0] for call in self.upstream], ["GET"])
        for ref_path in (self._path("c" * 24), self._path(switch_ref="d" * 24)):
            before = len(self.upstream)
            status, error = self.request("GET", ref_path, token=self.token)
            self.assertEqual(status, 502)
            self.assertIn(error["error"], ("site_ref_unknown", "switch_ref_unknown"))
            self.assertEqual(len(self.upstream), before)
        for ref_path in (self._path("c" * 24, suffix="poe-preview"),
                         self._path(switch_ref="d" * 24, suffix="poe-preview")):
            before = len(self.upstream)
            status, error = self.request("POST", ref_path, token=self.token,
                                         body={"changes": {"poeMode": 1}})
            self.assertEqual(status, 400)
            self.assertIn(error["error"], ("site_ref_unknown", "switch_ref_unknown"))
            self.assertEqual(len(self.upstream), before)
        for sensitive in ("site_1", SWITCH_MAC, SITE_REF, SWITCH_REF):
            self.assertNotIn(sensitive, self.logs.getvalue())

    def test_missing_duplicate_or_invalid_port_rows_fail_closed(self) -> None:
        self.rows = []
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "switch_port_unknown")
        self.rows = [dict(self.rows[0]) if self.rows else {
            "switchMac": SWITCH_MAC, "port": PORT, "poe": 0,
            "supportPoe": True, "profileOverrideEnable": True}]
        self.rows.append(dict(self.rows[0]))
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "switch_port_ambiguous")
        self.rows = [{"switchMac": SWITCH_MAC, "port": PORT, "poe": -1,
                      "supportPoe": True, "profileOverrideEnable": True}]
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "poe_mode_invalid")
        self.rows = [{"switchMac": SWITCH_MAC, "port": PORT, "poe": 0,
                      "supportPoe": True}]
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        self.rows = [{"switchMac": SWITCH_MAC, "port": PORT, "poe": 0,
                      "supportPoe": False, "profileOverrideEnable": True}]
        status, error = self.request("GET", self._path(), token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "poe_unsupported")
        self.rows = [{"switchMac": SWITCH_MAC, "port": PORT, "poe": 0,
                      "supportPoe": True, "profileOverrideEnable": False}]
        status, error = self.request("POST", self._path(suffix="poe-preview"),
                                     token=self.token, body={"changes": {"poeMode": 1}})
        self.assertEqual(status, 400)
        self.assertEqual(error["error"], "profile_override_required")
        self.assertFalse(any(call[0] == "PUT" for call in self.upstream))

    def test_preview_apply_toggle_readback_replay_capability_and_scrubbing(self) -> None:
        preview_path = self._path(suffix="poe-preview")
        status, unauth = self.request("POST", preview_path,
                                      body={"changes": {"poeMode": 1}})
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.upstream, [])

        status, preview = self.request("POST", preview_path, token=self.token,
                                       body={"changes": {"poeMode": 1}})
        self.assertEqual(status, 200)
        self.assertFalse(preview["writes_enabled"])
        self.assertEqual(preview["target"], {"poeMode": 1})
        self.assertEqual(preview["port"], PORT)
        self.assertIn("interrupt_power", preview["warning"])
        apply_path = f"/v1/poe-plans/{preview['plan_id']}/apply"
        status, unauthorized_apply = self.request("POST", apply_path, body={})
        self.assertEqual(status, 401)
        self.assertEqual(unauthorized_apply["error"], "unauthorized")
        status, disabled = self.request("POST", apply_path, token=self.token, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled["error"], "writes_disabled")
        self.assertFalse(any(call[0] == "PUT" for call in self.upstream))

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, enabled_preview = self.request("POST", preview_path, token=self.token,
                                               body={"changes": {"poeMode": 1}})
        self.assertEqual(status, 200)
        self.assertTrue(enabled_preview["writes_enabled"])
        apply_path = f"/v1/poe-plans/{enabled_preview['plan_id']}/apply"
        os.environ["OMADA_ENABLE_WRITES"] = "false"
        status, disabled_again = self.request("POST", apply_path, token=self.token, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled_again["error"], "writes_disabled")
        self.assertFalse(any(call[0] == "PUT" for call in self.upstream))
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, applied = self.request("POST", apply_path, token=self.token,
                                       body=self.approval_body(enabled_preview))
        self.assertEqual(status, 200)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["after"], {"poeMode": 1})
        self.assertEqual([call[0] for call in self.upstream],
                         ["GET", "GET", "GET", "GET", "PUT", "GET"])
        patch_call = next(call for call in self.upstream if call[0] == "PUT")
        self.assertEqual(patch_call[1],
                         "/openapi/v1/ctrl/sites/site_1/switches/AA-BB-CC-DD-EE-FF"
                         f"/ports/{PORT}/poe-mode")
        self.assertEqual(json.loads(patch_call[2]), {"poeMode": 1})
        status, replay = self.request("POST", apply_path, token=self.token,
                                      body=self.approval_body(enabled_preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.upstream if call[0] == "PUT"]), 1)

        status, capability = self.request("GET", "/v1/capabilities", token=self.token)
        self.assertEqual(status, 200)
        operations = {entry["operation"]: entry for entry in capability["items"]}
        self.assertEqual(operations["switch_port_poe_mode"]["runtime_evidence"][0]["result"],
                         "success")
        preview_cap = operations["switch_port_poe_mode_preview"]
        self.assertEqual(preview_cap["support_state"], "unknown")
        self.assertEqual(preview_cap["runtime_evidence"], [])
        for sensitive in (SITE_REF, SWITCH_REF, SWITCH_MAC, "site_1",
                          enabled_preview["plan_id"]):
            self.assertNotIn(sensitive, self.logs.getvalue())

    def test_preview_body_duplicate_keys_and_port_range_are_rejected(self) -> None:
        preview_path = self._path(suffix="poe-preview")
        for raw in ('{"changes":{"poeMode":1,"poeMode":0}}',
                    '{"changes":{"poeMode":true}}',
                    '{"changes":{"poeMode":2}}',
                    '{"changes":{"poeMode":1},"extra":1}',
                    '{"change":{"poeMode":1}}'):
            status, error = self.request("POST", preview_path, token=self.token, raw_body=raw)
            self.assertEqual(status, 400)
            self.assertNotEqual(error.get("status"), "ok")
        for bad_port in ("-1", "4097", "1.0"):
            status, error = self.request(
                "POST", self._path(port=bad_port, suffix="poe-preview"),
                token=self.token, body={"changes": {"poeMode": 1}})
            self.assertIn(status, (400, 501))
            self.assertNotEqual(error.get("status"), "ok")
        self.assertEqual(self.upstream, [])

    def test_timeout_is_in_doubt_and_no_write_replay(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        self.fail_put = True
        preview_path = self._path(suffix="poe-preview")
        status, preview = self.request("POST", preview_path, token=self.token,
                                       body={"changes": {"poeMode": 1}})
        self.assertEqual(status, 200)
        apply_path = f"/v1/poe-plans/{preview['plan_id']}/apply"
        status, uncertain = self.request("POST", apply_path, token=self.token,
                                          body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(uncertain["error"], "change_in_doubt")
        self.assertEqual(len([call for call in self.upstream if call[0] == "PUT"]), 1)
        status, listed = self.request("GET", "/v1/change-plans/poe/in-doubt", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(listed["items"][0]["target_refs"], {
            "site_ref": SITE_REF, "switch_ref": SWITCH_REF, "port": PORT})
        status, inspected = self.request(
            "GET", f"/v1/change-plans/poe/{preview['plan_id']}", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(inspected["outcome"], "unknown")
        self.assertIn("current_state_does_not_prove", inspected["observation_note"])
        status, replay = self.request("POST", apply_path, token=self.token,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.upstream if call[0] == "PUT"]), 1)
        for sensitive in (SITE_REF, SWITCH_REF, SWITCH_MAC, "site_1", preview["plan_id"]):
            self.assertNotIn(sensitive, self.logs.getvalue())

    def test_in_doubt_close_requires_exact_confirmation_and_never_retries(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        self.fail_put = True
        preview_path = self._path(suffix="poe-preview")
        status, preview = self.request("POST", preview_path, token=self.token,
                                       body={"changes": {"poeMode": 1}})
        self.assertEqual(status, 200)
        apply_path = f"/v1/poe-plans/{preview['plan_id']}/apply"
        status, uncertain = self.request("POST", apply_path, token=self.token,
                                          body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(uncertain["error"], "change_in_doubt")
        calls_before_close = list(self.upstream)
        close_path = f"/v1/change-plans/poe/{preview['plan_id']}/close"
        status, rejected = self.request("POST", close_path, token=self.token,
                                        body={"confirmation": "close"})
        self.assertEqual(status, 409)
        self.assertEqual(rejected["error"], "operator_confirmation_required")
        status, closed = self.request(
            "POST", close_path, token=self.token,
            body={"confirmation": "outcome_unknown_no_retry"})
        self.assertEqual(status, 200)
        self.assertEqual(closed["state"], "closed_outcome_unknown")
        self.assertEqual(closed["target_refs"], {
            "site_ref": SITE_REF, "switch_ref": SWITCH_REF, "port": PORT})
        self.assertEqual(self.upstream, calls_before_close)
        status, replay = self.request("POST", apply_path, token=self.token,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len([call for call in self.upstream if call[0] == "PUT"]), 1)

    def test_fixed_upstream_put_allowlist_pins_controller_and_exact_body(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id-file", "secret-file",
            cert_sha256="a" * 64))
        good_path = ("/openapi/v1/ctrl/sites/site_1/switches/AA-BB-CC-DD-EE-FF"
                     f"/ports/{PORT}/poe-mode")
        self.assertFalse(hasattr(client, "_write_dispatch_guard"))
        with patch.object(client, "_connection", side_effect=AssertionError("must not connect")):
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                client._request_json("PUT", good_path, body=b'{"poeMode":1}', token="token")

        guard_calls: list[str] = []
        client._write_dispatch_guard = lambda: guard_calls.append("checked")

        class Response:
            status = 200

            @staticmethod
            def read(_limit):
                return b'{"result":null}'

            @staticmethod
            def getheader(_name, _default=""):
                return "application/json"

        class Connection:
            def request(_self, method, path, *, body, headers):
                self.assertEqual(guard_calls, ["checked"])
                self.assertEqual((method, path, body), ("PUT", good_path, b'{"poeMode":1}'))

            @staticmethod
            def getresponse():
                return Response()

            @staticmethod
            def close():
                pass

        with patch.object(client, "_connection", return_value=Connection()) as connection:
            self.assertEqual(client._request_json(
                "PUT", good_path, body=b'{"poeMode":1}', token="token"), {"result": None})
        connection.assert_called_once()
        self.assertEqual(guard_calls, ["checked"])

        with patch.object(client, "_connection", side_effect=AssertionError("must not connect")):
            for method, path, body in (
                ("PUT", good_path.replace("/ctrl/", "/foreign/"), b'{"poeMode":1}'),
                ("PUT", good_path + "?evil=true", b'{"poeMode":1}'),
                ("PATCH", good_path, b'{"poeMode":1}'),
                ("PUT", good_path, b'{"poeMode":true}'),
                ("PUT", good_path, b'{"poeMode":2}'),
                ("PUT", good_path, b'{"poeMode":1,"poeMode":0}'),
                ("PUT", good_path, b'{"poeMode":1,"other":2}'),
                ("PUT", good_path.replace(f"/ports/{PORT}/", "/ports/4097/"), b'{"poeMode":1}'),
            ):
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, body=body, token="token")


if __name__ == "__main__":
    unittest.main()
