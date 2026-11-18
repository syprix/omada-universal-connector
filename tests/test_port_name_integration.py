from __future__ import annotations

import builtins
import hashlib
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
from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.operator_approval import sign_approval


TOKEN = "port-name-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
SWITCH_REF = "b" * 24
OTHER_SWITCH_REF = "c" * 24
SITE_ID = "private-site-id"
SWITCH_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_MAC = "11-22-33-44-55-66"
OLD_NAME = "ancien_private_port_name"
NEW_NAME = "new_private_port_name"
OPERATOR_ID = "op_" + "5" * 24


class PortNameIntegrationTests(unittest.TestCase):
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
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-reference-key")
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.client._switch_macs_by_site_ref[SITE_REF] = {
            SWITCH_REF: SWITCH_MAC, OTHER_SWITCH_REF: OTHER_MAC,
        }
        self.port_name = OLD_NAME
        self.duplicate_row = False
        self.fail_put = False
        self.put_calls: list[tuple[str, dict[str, str]]] = []
        self.transport_calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(token, "synthetic-upstream-token")
            if method == "GET":
                self.assertEqual(path.split("?", 1)[0],
                                 f"/openapi/v1/ctrl/sites/{SITE_ID}/switches/ports/overview")
                row = {"switchMac": SWITCH_MAC, "port": 7, "portName": self.port_name,
                       "name": "private_switch_name", "ip": "192.0.2.10"}
                rows = [row, dict(row)] if self.duplicate_row else [row]
                query = path.split("?", 1)[1]
                page = int(query.split("page=", 1)[1].split("&", 1)[0])
                return {"result": {"data": rows if page == 1 else [],
                                    "totalRows": len(rows), "currentPage": page,
                                    "currentSize": len(rows) if page == 1 else 0}}
            self.assertEqual(method, "PUT")
            self.assertEqual(path, f"/openapi/v1/ctrl/sites/{SITE_ID}/switches/{SWITCH_MAC}/ports/7/name")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertEqual(set(decoded), {"name"})
            self.assertIs(type(decoded["name"]), str)
            self.put_calls.append((path, decoded))
            if self.fail_put:
                raise OSError("private upstream error")
            self.port_name = decoded["name"]
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
        self.plans_patch = patch.object(main, "_PORT_NAME_PLANS", None)
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
        return f"/openapi/v1/ctrl/sites/{SITE_ID}/switches/ports/overview"

    @staticmethod
    def _read_path(switch_ref: str = SWITCH_REF) -> str:
        return f"/v1/sites/{SITE_REF}/switches/{switch_ref}/ports/7/name"

    @staticmethod
    def _preview_path(switch_ref: str = SWITCH_REF) -> str:
        return f"/v1/sites/{SITE_REF}/switches/{switch_ref}/ports/7/name-preview"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
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
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        status = response.status
        connection.close()
        return status, parsed

    def preview(self) -> dict[str, object]:
        status, result = self.request("POST", self._preview_path(), token=TOKEN,
                                      body={"changes": {"name": NEW_NAME}})
        self.assertEqual(status, 200, result)
        return result

    def approval_body(self, preview: dict[str, object], *, key: bytes | None = None):
        request = preview["approval_request"]
        assert isinstance(request, dict)
        now = int(time.time())
        signed = sign_approval(
            key or self.operator_key, operation="switch-port-name",
            plan_id=preview["plan_id"], plan_digest=request["digest"],
            operator_id=OPERATOR_ID, expires_at=now + 120, now=now)
        return {"approval": signed}

    def test_authenticated_preview_and_unique_ref_port_binding(self) -> None:
        status, unauth = self.request("POST", self._preview_path(),
                                      body={"changes": {"name": NEW_NAME}})
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        self.client._switch_macs_by_site_ref[SITE_REF][OTHER_SWITCH_REF] = SWITCH_MAC
        status, ambiguous = self.request("POST", self._preview_path(OTHER_SWITCH_REF),
                                         token=TOKEN, body={"changes": {"name": NEW_NAME}})
        self.assertNotEqual(status, 200)
        self.assertEqual(ambiguous["error"], "readback_unavailable")
        self.assertEqual(self.transport_calls, [])
        self.client._switch_macs_by_site_ref[SITE_REF][OTHER_SWITCH_REF] = OTHER_MAC

        self.duplicate_row = True
        status, duplicate = self.request("POST", self._preview_path(), token=TOKEN,
                                         body={"changes": {"name": NEW_NAME}})
        self.assertEqual(status, 400)
        self.assertEqual(duplicate["error"], "readback_unavailable")
        self.assertEqual(self.put_calls, [])

        self.duplicate_row = False
        preview = self.preview()
        self.assertEqual(preview["before"], {"name": OLD_NAME})
        self.assertEqual(preview["target"], {"name": NEW_NAME})
        self.assertEqual(preview["rollback"], {"name": OLD_NAME})
        approval = preview["approval_request"]
        self.assertEqual(approval["operation"], "switch-port-name")
        self.assertEqual(approval["before"], {"name": OLD_NAME})
        self.assertEqual(approval["target"], {"name": NEW_NAME})

    def test_default_write_off_missing_and_wrong_approval_and_stale_state(self) -> None:
        preview = self.preview()
        apply_path = f"/v1/switch-port-name-plans/{preview['plan_id']}/apply"
        status, disabled = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled["error"], "writes_disabled")
        self.assertEqual(self.put_calls, [])

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, missing = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(missing["error"], "operator_approval_required")
        forged = self.approval_body(preview, key=b"x" * 32)
        status, wrong = self.request("POST", apply_path, token=TOKEN, body=forged)
        self.assertEqual(status, 409)
        self.assertIn(wrong["error"], {"operator_approval_invalid", "operator_approval_mismatch"})
        self.assertEqual(self.put_calls, [])

        self.port_name = "external changed port"
        status, stale = self.request("POST", apply_path, token=TOKEN,
                                     body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(stale["error"], "state_changed")
        self.assertEqual(self.put_calls, [])

    def test_approved_apply_is_single_put_readback_and_secret_free_outside_preview(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        preview = self.preview()
        apply_path = f"/v1/switch-port-name-plans/{preview['plan_id']}/apply"
        status, applied = self.request("POST", apply_path, token=TOKEN,
                                       body=self.approval_body(preview))
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(self.port_name, NEW_NAME)
        self.assertEqual(len(self.put_calls), 1)
        self.assertEqual(json.loads(self.transport_calls[-2][2]), {"name": NEW_NAME})
        self.assertNotIn(OLD_NAME, json.dumps(applied))
        self.assertNotIn(NEW_NAME, json.dumps(applied))
        self.assertNotIn(OLD_NAME, self.logs.getvalue())
        self.assertNotIn(NEW_NAME, self.logs.getvalue())

        with open(os.path.join(self.journal_dir, "change-plans.jsonl"), encoding="utf-8") as handle:
            journal_text = handle.read()
        self.assertIn('"name_redacted":true', journal_text)
        for private in (OLD_NAME, NEW_NAME, hashlib.sha256(OLD_NAME.encode()).hexdigest(),
                        hashlib.sha256(NEW_NAME.encode()).hexdigest()):
            self.assertNotIn(private, journal_text)

        status, replay = self.request("POST", apply_path, token=TOKEN,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len(self.put_calls), 1)

    def test_dispatch_failure_recovers_as_redacted_in_doubt_without_replay(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        preview = self.preview()
        apply_path = f"/v1/switch-port-name-plans/{preview['plan_id']}/apply"
        self.fail_put = True
        status, failed = self.request("POST", apply_path, token=TOKEN,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(failed["error"], "change_in_doubt")
        self.assertEqual(len(self.put_calls), 1)

        runtime = main._JOURNAL_RUNTIME
        assert runtime is not None
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._PORT_NAME_PLANS = None

        status, doubts = self.request("GET", "/v1/change-plans/switch-port-name/in-doubt",
                                      token=TOKEN)
        self.assertEqual(status, 200, doubts)
        matches = [row for row in doubts["items"] if row["plan_id"] == preview["plan_id"]]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["state"], "in_doubt")
        self.assertEqual(len(self.put_calls), 1)

        status, inspected = self.request(
            "GET", f"/v1/change-plans/switch-port-name/{preview['plan_id']}", token=TOKEN)
        self.assertEqual(status, 200, inspected)
        self.assertEqual(inspected["state"], "in_doubt")
        self.assertTrue(inspected["before"]["name_redacted"])
        self.assertTrue(inspected["target"]["name_redacted"])
        self.assertTrue(inspected["current_observation"]["name_redacted"])
        self.assertEqual(inspected["observation_note"],
                         "current_state_does_not_prove_original_write_outcome")
        rendered = json.dumps(doubts) + json.dumps(inspected) + self.logs.getvalue()
        self.assertNotIn(OLD_NAME, rendered)
        self.assertNotIn(NEW_NAME, rendered)
        self.assertEqual(len(self.put_calls), 1)

        with open(os.path.join(self.journal_dir, "change-plans.jsonl"), encoding="utf-8") as handle:
            journal_text = handle.read()
        self.assertIn('"name_redacted":true', journal_text)
        for private in (OLD_NAME, NEW_NAME, hashlib.sha256(OLD_NAME.encode()).hexdigest(),
                        hashlib.sha256(NEW_NAME.encode()).hexdigest()):
            self.assertNotIn(private, journal_text)


if __name__ == "__main__":
    unittest.main()
