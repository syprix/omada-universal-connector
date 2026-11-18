from __future__ import annotations

import builtins
import copy
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


TOKEN = "gateway-tag-qos-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
SITE_ID = "private-tag-qos-site-id"
OPERATOR_ID = "op_" + "6" * 24
INITIAL = {"tagConfigList": [
    {"classType": 0, "enable": False, "dscp": "8"},
    {"classType": 1, "enable": True, "dscp": "10"},
    {"classType": 2, "enable": False, "dscp": "20"},
    {"classType": 3, "enable": True, "dscp": "46"},
]}


class GatewayTagQosIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.temp.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        os.chmod(self.token_file, 0o600)
        self.operator_key = b"o" * 32
        self.operator_key_file = os.path.join(self.temp.name, "operator-key")
        fd = os.open(self.operator_key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(self.operator_key)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-reference-key")
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.state = copy.deepcopy(INITIAL)
        self.transport_calls: list[tuple[str, str, bytes | None]] = []
        self.put_calls: list[tuple[str, dict[str, object]]] = []
        self.put_mode = "normal"

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(token, "synthetic-upstream-token")
            self.assertEqual(path, self._upstream_path())
            if method == "GET":
                self.assertIsNone(body)
                return {"result": copy.deepcopy(self.state)}
            self.assertEqual(method, "PUT")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertEqual(set(decoded), {"tagConfigList"})
            self.assertIsInstance(decoded["tagConfigList"], list)
            self.put_calls.append((path, copy.deepcopy(decoded)))
            if self.put_mode == "timeout":
                raise OSError("private upstream detail")
            self.state = copy.deepcopy(decoded)
            if self.put_mode == "mismatch":
                self.state["tagConfigList"][0]["dscp"] = "16"
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
        self.plans_patch = patch.object(main, "_GATEWAY_TAG_QOS_PLANS", None)
        self.plans_patch.start()
        self.active_patch = patch.object(main, "_ACTIVE_APPROVAL", None)
        self.active_patch.start()
        self.consumed_patch = patch.dict(main._CONSUMED_APPROVALS, {}, clear=True)
        self.consumed_patch.start()
        self.logs = io.StringIO()
        self.print_patch = patch.object(
            builtins, "print", lambda *args, **_kwargs: self.logs.write(
                " ".join(map(str, args)) + "\n"))
        self.print_patch.start()
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
        self.print_patch.stop()
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
    def _upstream_path() -> str:
        return f"/openapi/v1/ctrl/sites/{SITE_ID}/qos/gateway/tag-outbound-traffic"

    @staticmethod
    def _read_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/qos/gateway/tag-outbound-traffic"

    @staticmethod
    def _preview_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/qos/gateway/tag-outbound-traffic-preview"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: object | None = None, raw_body: bytes | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers: dict[str, str] = {}
        encoded = raw_body
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":")).encode("ascii")
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        status = response.status
        connection.close()
        return status, parsed

    def preview(self, changes: dict[str, object] | None = None) -> dict[str, object]:
        status, result = self.request(
            "POST", self._preview_path(), token=TOKEN,
            body={"changes": {"classType": 2, "enable": True} if changes is None else changes,
                  "disruption_confirmed": True})
        self.assertEqual(status, 200, result)
        return result

    def approval(self, preview: dict[str, object], *, key: bytes | None = None,
                 nonce: str | None = None) -> dict[str, object]:
        summary = preview["approval_request"]
        assert isinstance(summary, dict)
        now = int(time.time())
        context = patch("app.operator_approval.secrets.token_hex", return_value=nonce) if nonce else _NullContext()
        with context:
            return sign_approval(
                key or self.operator_key, operation="gateway-tag-qos",
                plan_id=preview["plan_id"], plan_digest=summary["digest"],
                operator_id=OPERATOR_ID, expires_at=now + 120, now=now)

    def apply(self, preview: dict[str, object], approval: dict[str, object]):
        return self.request("POST", f"/v1/gateway-tag-qos-plans/{preview['plan_id']}/apply",
                            token=TOKEN, body={"approval": approval})

    def test_auth_complete_preview_warning_and_hmac_binds_all_ordered_state(self) -> None:
        status, unauth = self.request("GET", self._read_path())
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, read = self.request("GET", self._read_path(), token=TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(read["data"], INITIAL)
        preview = self.preview()
        expected = copy.deepcopy(INITIAL)
        expected["tagConfigList"][2]["enable"] = True
        self.assertEqual(preview["before"], INITIAL)
        self.assertEqual(preview["target"], expected)
        self.assertEqual(preview["rollback"], INITIAL)
        self.assertEqual(preview["warning"],
                         "This site-wide QoS configuration may affect traffic prioritization across the site; the controller-specific effect and outcome are not guaranteed.")
        summary = preview["approval_request"]
        self.assertEqual(summary["before"], INITIAL)
        self.assertEqual(summary["target"], expected)
        self.assertEqual(summary["target_refs"], {"site_ref": SITE_REF})

        plan = main._GATEWAY_TAG_QOS_PLANS.plans[preview["plan_id"]]
        old_before, old_target = copy.deepcopy(plan["before"]), copy.deepcopy(plan["target"])
        plan["before"]["tagConfigList"].reverse()
        plan["target"]["tagConfigList"].reverse()
        signed = self.approval(preview)
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, rejected = self.apply(preview, signed)
        self.assertEqual(status, 409)
        self.assertIn(rejected["error"], {"operator_approval_mismatch", "operator_approval_invalid"})
        self.assertEqual(self.put_calls, [])
        plan["before"], plan["target"] = old_before, old_target

    def test_missing_extra_duplicate_classes_and_dscp_fail_closed(self) -> None:
        malformed = [
            {"tagConfigList": INITIAL["tagConfigList"][:3]},
            {"tagConfigList": [*INITIAL["tagConfigList"], INITIAL["tagConfigList"][0]]},
            {"tagConfigList": [{**row, "extra": True} for row in INITIAL["tagConfigList"]]},
            {"tagConfigList": [{**row, "classType": 0} if index == 1 else row
                               for index, row in enumerate(INITIAL["tagConfigList"])]},
            {"tagConfigList": [{**row, "dscp": "08"} if index == 0 else row
                               for index, row in enumerate(INITIAL["tagConfigList"])]},
            {"tagConfigList": [{**row, "dscp": ""} if index == 0 else row
                               for index, row in enumerate(INITIAL["tagConfigList"])]},
        ]
        for state in malformed:
            self.state = copy.deepcopy(state)
            with self.subTest(state=state):
                status, result = self.request("GET", self._read_path(), token=TOKEN)
                self.assertEqual(status, 502)
                self.assertEqual(result["error"], "openapi_response_invalid")
                status, preview = self.request(
                    "POST", self._preview_path(), token=TOKEN,
                    body={"changes": {"classType": 2, "enable": True},
                          "disruption_confirmed": True})
                self.assertNotEqual(status, 200)
                self.assertNotIn("plan_id", preview)
                self.assertEqual(self.put_calls, [])
        self.state = copy.deepcopy(INITIAL)

    def test_same_valid_dscp_across_classes_is_preserved_without_normalization(self) -> None:
        self.state["tagConfigList"][1]["dscp"] = "8"
        preview = self.preview()
        self.assertEqual(preview["before"]["tagConfigList"][0]["dscp"], "8")
        self.assertEqual(preview["before"]["tagConfigList"][1]["dscp"], "8")
        self.assertEqual(preview["target"]["tagConfigList"][0]["dscp"], "8")
        self.assertEqual(preview["target"]["tagConfigList"][1]["dscp"], "8")
        self.assertEqual(preview["target"]["tagConfigList"][1]["enable"], True)

    def test_default_off_wrong_approval_stale_and_single_successful_put(self) -> None:
        preview = self.preview()
        apply_path = f"/v1/gateway-tag-qos-plans/{preview['plan_id']}/apply"
        status, disabled = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled["error"], "writes_disabled")
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, missing = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(missing["error"], "operator_approval_required")
        status, wrong = self.apply(preview, self.approval(preview, key=b"x" * 32))
        self.assertEqual(status, 409)
        self.assertIn(wrong["error"], {"operator_approval_invalid", "operator_approval_mismatch"})
        self.assertEqual(self.put_calls, [])

        preview = self.preview()
        self.state["tagConfigList"][0]["dscp"] = "16"
        status, stale = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"], "state_changed")
        self.assertEqual(self.put_calls, [])
        self.state = copy.deepcopy(INITIAL)

        preview = self.preview()
        status, applied = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 200, applied)
        target = copy.deepcopy(INITIAL)
        target["tagConfigList"][2]["enable"] = True
        self.assertEqual(self.state, target)
        self.assertEqual(self.put_calls, [(self._upstream_path(), target)])
        self.assertEqual(applied["before"], INITIAL)
        self.assertEqual(applied["after"], target)
        self.assertEqual([row[0] for row in self.transport_calls[-3:]], ["GET", "PUT", "GET"])
        self.assertEqual(json.loads(self.transport_calls[-2][2]), target)
        self.assertEqual(len(self.put_calls), 1)

    def test_post_intent_foreign_change_and_readback_mismatch_are_in_doubt_no_replay(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        preview = self.preview()
        plans = main._GATEWAY_TAG_QOS_PLANS
        original = plans.journal.record_dispatch_intent

        def mutate_after_durable_intent(**event):
            original(**event)
            self.state["tagConfigList"][0]["dscp"] = "16"

        plans.journal.record_dispatch_intent = mutate_after_durable_intent
        status, rejected = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 409)
        self.assertEqual(rejected["error"], "change_in_doubt")
        self.assertEqual(self.put_calls, [])
        plans.journal.record_dispatch_intent = original

        # Start with a fresh plan and force a full-state readback mismatch.
        self.state = copy.deepcopy(INITIAL)
        preview = self.preview()
        self.put_mode = "mismatch"
        status, mismatch = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 409)
        self.assertEqual(mismatch["error"], "change_in_doubt")
        self.assertEqual(len(self.put_calls), 1)
        runtime = main._JOURNAL_RUNTIME
        assert runtime is not None
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._GATEWAY_TAG_QOS_PLANS = None
        status, doubts = self.request("GET", "/v1/change-plans/gateway-tag-qos/in-doubt", token=TOKEN)
        self.assertEqual(status, 200, doubts)
        self.assertIn(preview["plan_id"], [item["plan_id"] for item in doubts["items"]])
        status, replay = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len(self.put_calls), 1)

    def test_controller_transport_guard_rejects_all_other_put_shapes_and_runs_pre_request(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        path = self._upstream_path()
        valid_body = json.dumps(INITIAL, separators=(",", ":")).encode("ascii")
        events: list[str] = []

        class Response:
            status = 200

            @staticmethod
            def read(_limit: int) -> bytes:
                return b'{"errorCode":0,"result":null}'

            @staticmethod
            def getheader(_name: str, default: str = "") -> str:
                return "application/json" if not default else default

        class Connection:
            def __init__(self) -> None:
                self.calls = []

            def request(self, method, request_path, *, body=None, headers=None):
                events.append("request")
                self.calls.append((method, request_path, body))

            def getresponse(self):
                return Response()

            @staticmethod
            def close():
                pass

        connection = Connection()

        def connect():
            events.append("connect")
            return connection

        with patch.object(client, "_connection", side_effect=connect):
            client._write_dispatch_guard = lambda: events.append("guard")
            for method, candidate_path, candidate_body in (
                    ("PATCH", path, valid_body),
                    ("PUT", path.replace("/ctrl/", "/other/"), valid_body),
                    ("PUT", path, valid_body[:-1] + b',"extra":1}'),
                    ("PUT", path, b'{"tagConfigList":[],"tagConfigList":[]}'),
                    ("PUT", path, b'{"tagConfigList":[{"classType":0,"classType":0}]}')):
                with self.subTest(method=method, candidate_path=candidate_path), self.assertRaises(OpenApiError) as raised:
                    client._request_json(method, candidate_path, body=candidate_body, token="fake")
                self.assertEqual(raised.exception.code, "openapi_path_rejected")
            self.assertEqual(events, [])
            client._request_json("PUT", path, body=valid_body, token="fake")
            self.assertEqual(events, ["connect", "guard", "request"])
            self.assertEqual(connection.calls, [("PUT", path, valid_body)])
            events.clear()
            connection.calls.clear()
            client._write_dispatch_guard = lambda: (_ for _ in ()).throw(RuntimeError("expired"))
            with self.assertRaisesRegex(RuntimeError, "expired"):
                client._request_json("PUT", path, body=valid_body, token="fake")
            self.assertEqual(events, ["connect"])
            self.assertEqual(connection.calls, [])

    def test_logs_and_responses_omit_controller_identity_and_tokens(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        preview = self.preview()
        status, applied = self.apply(preview, self.approval(preview))
        self.assertEqual(status, 200)
        output = self.logs.getvalue() + json.dumps(applied)
        for private in (SITE_ID, "controller.example", "synthetic-upstream-token", "unused-secret"):
            self.assertNotIn(private, output)


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, *_args):
        return False


if __name__ == "__main__":
    unittest.main()
