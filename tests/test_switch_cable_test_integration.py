from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import unittest
from dataclasses import replace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.operator_approval import sign_approval
from app.openapi import OmadaOpenApiClient, OpenApiConfig


SITE_REF, SWITCH_REF = "a" * 24, "b" * 24
MAC, PORT = "00:11:22:33:44:55", 7
TOKEN = "cable-test-caller-token-0123456789abcdef"


class SwitchCableTestIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.temp.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.key = b"k" * 32
        self.key_file = os.path.join(self.temp.name, "operator-key")
        with open(self.key_file, "wb") as stream:
            stream.write(self.key)
        os.chmod(self.key_file, 0o600)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-ref-key")
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._switch_macs_by_site_ref[SITE_REF] = {SWITCH_REF: MAC}
        self.logs = []
        self.results = {"status": 0, "data": []}
        self.upstream = []

        def request(method, path, body=None, token=None):
            self.upstream.append((method, path, body))
            self.assertEqual(token, "fixture-upstream-token")
            if path.endswith("/ports") and method == "GET":
                return {"errorCode": 0, "result": [{"port": PORT, "type": 1,
                    "editEnable": True, "isUpperPort": False, "isDisabled": False,
                    "isStackPort": False, "reasons": [], "isCopper": True}]}
            if path.endswith("/logs") and method == "GET":
                return {"errorCode": 0, "result": self.logs}
            if path.endswith("/full-results") and method == "GET":
                return {"errorCode": 0, "result": self.results}
            if path.endswith("/start") and method == "POST":
                self.assertEqual(json.loads(body), {"portList": [{"port": PORT}]})
                return {"errorCode": 0}
            if path.endswith("/cancel") and method == "POST":
                self.assertIsNone(body)
                return {"errorCode": 0}
            self.fail("unexpected upstream route")

        self.request_patch = patch.object(self.client, "_request_json", side_effect=request)
        self.request_patch.start()
        self.access_patch = patch.object(self.client, "_access_token", return_value="fixture-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_file,
            "OMADA_ENABLE_WRITES": "true",
            "OMADA_CHANGE_JOURNAL_DIR": self.journal_dir,
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": self.key_file,
        })
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.runtime_patch = patch.object(main, "_JOURNAL_RUNTIME", None)
        self.runtime_patch.start()
        self.plan_patch = patch.object(main, "_SWITCH_CABLE_TEST_PLANS", None)
        self.plan_patch.start()
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None
        self.output = io.StringIO()
        self.print_patch = patch.object(builtins, "print", lambda *a, **k: self.output.write(" ".join(map(str, a)) + "\n"))
        self.print_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.print_patch.stop()
        runtime = main._JOURNAL_RUNTIME
        if runtime is not None:
            runtime.close()
        self.plan_patch.stop()
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None
        self.runtime_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.request_patch.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, token=TOKEN):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Authorization": "Bearer " + token}
        encoded = None
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=encoded, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        return response.status, data

    def preview(self):
        return self.request("POST", f"/v1/sites/{SITE_REF}/switches/{SWITCH_REF}/cable-test-preview",
                            {"port": PORT, "disruption_confirmed": True})

    def approve(self, operation, summary):
        return sign_approval(self.key, operation=operation, plan_id=summary["plan_id"],
            plan_digest=summary["digest"], operator_id="op_" + "d" * 24,
            expires_at=int(__import__("time").time()) + 60)

    def test_preview_and_apply_need_exact_operator_approval_then_poll_redacted_result(self):
        status, preview = self.preview()
        self.assertEqual(status, 200)
        self.assertEqual(preview["target"], {"port": PORT, "max_runtime_seconds": 60})
        self.assertEqual(preview["approval_request"]["target_refs"],
                         {"site_ref": SITE_REF, "switch_ref": SWITCH_REF})
        plan_id = preview["plan_id"]
        summary = preview["approval_request"]
        status, rejected = self.request("POST", f"/v1/switch-cable-test-plans/{plan_id}/apply", {})
        self.assertEqual(status, 409)
        self.assertEqual(rejected["error"], "operator_approval_required")
        self.assertFalse(any(method == "POST" for method, _, _ in self.upstream))
        approval = self.approve("switch-cable-test", summary)
        status, applied = self.request("POST", f"/v1/switch-cable-test-plans/{plan_id}/apply",
                                       {"approval": approval})
        self.assertEqual(status, 200)
        self.assertEqual(applied["status"], "started")
        post_count = sum(method == "POST" for method, _, _ in self.upstream)
        status, repeated = self.request("POST", f"/v1/switch-cable-test-plans/{plan_id}/apply",
                                        {"approval": approval})
        self.assertEqual(status, 409)
        self.assertEqual(repeated["error"], "plan_unavailable")
        self.assertEqual(sum(method == "POST" for method, _, _ in self.upstream), post_count)

        self.logs.append({"type": 1, "timeStamp": 999, "testPortList": [{"port": PORT}],
                          "completePortList": [{"port": PORT}], "cancelPortList": [],
                          "timeoutPortList": []})
        self.results = {"status": 0, "data": [{"port": PORT, "timeStamp": 999,
            "state": [1, 2], "length": [14, 15], "privateMac": MAC}]}
        status, observed = self.request("GET", f"/v1/switch-cable-test-plans/{plan_id}/status")
        self.assertEqual(status, 200)
        self.assertEqual(observed["status"], "completed")
        self.assertEqual(observed["result"], {"state_codes": [1, 2], "length_values": [14, 15]})
        self.assertNotIn(MAC, json.dumps(observed))

    def test_cancel_is_a_separately_approved_post_and_not_an_unreviewed_get(self):
        _, preview = self.preview()
        plan_id = preview["plan_id"]
        approval = self.approve("switch-cable-test", preview["approval_request"])
        status, _ = self.request("POST", f"/v1/switch-cable-test-plans/{plan_id}/apply",
                                 {"approval": approval})
        self.assertEqual(status, 200)
        status, cancel_preview = self.request("POST",
            f"/v1/switch-cable-test-plans/{plan_id}/cancel-preview", {"disruption_confirmed": True})
        self.assertEqual(status, 200)
        cancel_approval = self.approve("switch-cable-test-cancel", cancel_preview["approval_request"])
        cancel_id = cancel_preview["plan_id"]
        status, cancelled = self.request("POST",
            f"/v1/switch-cable-test-cancel-plans/{cancel_id}/apply", {"approval": cancel_approval})
        self.assertEqual(status, 200, cancelled)
        self.assertEqual(cancelled["outcome"], "unknown_until_status_read")
        self.assertEqual(self.upstream[-1][0], "POST")

    def test_mcp_http_flow_uses_the_same_signed_start_and_redacted_status(self):
        def call(action_args, request_id):
            return self.request("POST", "/mcp", {
                "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                "params": {"name": "omada_switch_cable_test", "arguments": action_args},
            })

        status, response = call({"action": "preview", "site_ref": SITE_REF,
            "switch_ref": SWITCH_REF, "port": PORT, "disruption_confirmed": True}, 1)
        self.assertEqual(status, 200)
        planned = response["result"]["structuredContent"]
        approval = self.approve("switch-cable-test", planned["approval_request"])
        status, response = call({"action": "apply", "plan_id": planned["plan_id"],
                                 "approval": approval}, 2)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["status"], "started")
        self.logs.append({"type": 1, "timeStamp": 1001,
                          "testPortList": [{"port": PORT}], "completePortList": [{"port": PORT}],
                          "cancelPortList": [], "timeoutPortList": []})
        self.results = {"status": 0, "data": [{"port": PORT, "timeStamp": 1001,
            "state": [1], "length": [12], "privateMac": MAC}]}
        status, response = call({"action": "status", "plan_id": planned["plan_id"]}, 3)
        self.assertEqual(status, 200)
        report = response["result"]["structuredContent"]
        self.assertEqual(report["status"], "completed")
        self.assertNotIn(MAC, json.dumps(report))
        self.assertEqual(sum(method == "POST" for method, _, _ in self.upstream), 1)


if __name__ == "__main__":
    unittest.main()
