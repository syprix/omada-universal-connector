from __future__ import annotations

import json
import hashlib
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import main
from app.operator_approval import sign_approval


TOKEN = "operator-approval-caller-token-0123456789abcdef"
REFERENCE_KEY = b"r" * 32
APPROVAL_KEY = b"o" * 32
OTHER_KEY = b"x" * 32
URL = "https://controller.example:8043"
CONTROLLER = "approval-controller"
OPERATOR = "op_" + "1" * 24
SITE = "a" * 24
SWITCH = "b" * 24
PORT = 7


class FakeClient:
    def __init__(self, reference_key_file: str):
        self.config = SimpleNamespace(reference_key_file=reference_key_file,
                                      base_url=URL, controller_id=CONTROLLER)
        self._ref_key = REFERENCE_KEY
        self.status = {"status": 1}
        self.write_attempts: list[dict[str, int]] = []
        self.events: list[str] = []
        self.fail_next_read = False
        self.fail_write = False

    def read_switch_port_status(self, _site: str, _switch: str, _port: int):
        if self.fail_next_read:
            self.fail_next_read = False
            self.events.append("preflight_read_error")
            raise OSError("local fixture read failure")
        self.events.append("read")
        return {"status": "ok", "resource": "switch_port_status",
                "data": dict(self.status)}

    def put_switch_port_status(self, _site: str, _switch: str, _port: int,
                               body: dict[str, int]):
        self.events.append("write")
        self.write_attempts.append(dict(body))
        if self.fail_write:
            raise TimeoutError("simulated local timeout")
        self.status = dict(body)


class ApprovalHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.token_file = self.root / "caller-token"
        self.token_file.write_text(TOKEN, encoding="ascii")
        os.chmod(self.token_file, 0o600)
        self.reference_key_file = self.root / "reference-key"
        self.reference_key_file.write_bytes(REFERENCE_KEY)
        os.chmod(self.reference_key_file, 0o600)
        self.operator_key_file = self.root / "operator-key"
        self.operator_key_file.write_bytes(APPROVAL_KEY)
        os.chmod(self.operator_key_file, 0o600)
        self.journal_dir = self.root / "journal"
        self.journal_dir.mkdir(mode=0o700)
        os.chmod(self.journal_dir, 0o700)
        self.client = FakeClient(str(self.reference_key_file))
        self.env = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": str(self.token_file),
            "OMADA_REFERENCE_KEY_FILE": str(self.reference_key_file),
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": str(self.operator_key_file),
            "OMADA_CHANGE_JOURNAL_DIR": str(self.journal_dir),
            "OMADA_ENABLE_WRITES": "true",
        })
        self.env.start()
        self._reset_globals()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @staticmethod
    def _reset_globals():
        if main._JOURNAL_RUNTIME is not None:
            main._JOURNAL_RUNTIME.close()
        for name in ("_RADIO_PLANS", "_DNS_CACHE_PLANS", "_SSID_PLANS",
                     "_GATEWAY_IPV6_PLANS", "_POE_PLANS", "_PORT_STATUS_PLANS"):
            setattr(main, name, None)
        main._JOURNAL_RUNTIME = None
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self._reset_globals()
        self.client_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    @staticmethod
    def preview_path():
        return f"/v1/sites/{SITE}/switches/{SWITCH}/ports/{PORT}/status-preview"

    def request(self, method: str, path: str, body=None, *, authorized=True):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {}
        payload = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body if body is not None else {}).encode()
        if authorized:
            headers["Authorization"] = "Bearer " + TOKEN
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        result = json.loads(response.read())
        conn.close()
        return response.status, result

    def preview(self):
        return self.request("POST", self.preview_path(), {
            "changes": {"status": 0}, "disruption_confirmed": True})

    @staticmethod
    def apply_path(plan_id: str):
        return f"/v1/switch-port-status-plans/{plan_id}/apply"

    @staticmethod
    def doubt_path(plan_id: str):
        return f"/v1/change-plans/switch-port-status/{plan_id}"

    def approval(self, preview: dict[str, object], *, key=APPROVAL_KEY,
                 plan_id: str | None = None, digest: str | None = None,
                 expires_at: int | None = None, now: int | None = None):
        request = preview["approval_request"]
        current = int(time.time()) if now is None else now
        return sign_approval(
            key, operation="switch-port-status",
            plan_id=plan_id or str(request["plan_id"]),
            plan_digest=digest or str(request["digest"]), operator_id=OPERATOR,
            expires_at=expires_at if expires_at is not None else current + 120,
            now=current)

    def test_preview_returns_server_bound_approval_snapshot_and_auth_is_required(self):
        status, unauthorized = self.request("POST", self.preview_path(), {
            "changes": {"status": 0}, "disruption_confirmed": True}, authorized=False)
        self.assertEqual(status, 401)
        self.assertEqual(unauthorized["error"], "unauthorized")
        status, preview = self.preview()
        self.assertEqual(status, 200)
        summary = preview["approval_request"]
        self.assertEqual(summary["operation"], "switch-port-status")
        self.assertEqual(summary["plan_id"], preview["plan_id"])
        self.assertEqual(summary["target_refs"], {
            "site_ref": SITE, "switch_ref": SWITCH, "port": PORT})
        self.assertEqual(summary["before"], {"status": 1})
        self.assertEqual(summary["target"], {"status": 0})
        self.assertEqual(len(summary["before_hash"]), 64)
        self.assertEqual(len(summary["digest"]), 64)
        self.assertNotIn(str(self.journal_dir), json.dumps(preview))

    def test_operator_key_must_be_separate_from_reference_key(self):
        self.operator_key_file.write_bytes(REFERENCE_KEY)
        status, state = self.request("GET", "/state")
        self.assertEqual(status, 200)
        self.assertTrue(state["read_only"])
        self.assertEqual(state["approval_status"], "unavailable")
        status, preview = self.preview()
        self.assertEqual(status, 200)
        self.assertFalse(preview["writes_enabled"])
        status, result = self.request("POST", self.apply_path(preview["plan_id"]), {})
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "writes_disabled")
        self.assertEqual(self.client.write_attempts, [])

    def test_apply_without_approval_rejected_and_with_wrong_plan_digest_or_key_rejected(self):
        status, preview = self.preview()
        plan_id = preview["plan_id"]
        status, missing = self.request("POST", self.apply_path(plan_id), {})
        self.assertEqual(status, 409)
        self.assertEqual(missing["error"], "operator_approval_required")

        bad_tokens = [
            self.approval(preview, plan_id="f" * 48),
            self.approval(preview, digest="0" * 64),
            self.approval(preview, key=OTHER_KEY),
        ]
        for token in bad_tokens:
            with self.subTest(token=token):
                status, result = self.request("POST", self.apply_path(plan_id), {"approval": token})
                self.assertEqual(status, 409)
                self.assertIn(result["error"], {
                    "operator_approval_mismatch", "operator_approval_invalid"})
        self.assertEqual(self.client.write_attempts, [])

    def test_expired_approval_and_changed_stored_plan_are_rejected(self):
        status, preview = self.preview()
        plan_id = preview["plan_id"]
        now = int(time.time())
        expired = self.approval(preview, expires_at=now - 1, now=now - 3)
        status, result = self.request("POST", self.apply_path(plan_id), {"approval": expired})
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "operator_approval_expired")

        token = self.approval(preview)
        main._PORT_STATUS_PLANS.plans[plan_id]["target"] = {"status": 1}
        status, result = self.request("POST", self.apply_path(plan_id), {"approval": token})
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "operator_approval_mismatch")
        self.assertEqual(self.client.write_attempts, [])

    def test_nonce_cannot_be_reused_after_approval_even_when_preflight_read_fails(self):
        status, preview = self.preview()
        token = self.approval(preview)
        plan_id = preview["plan_id"]
        self.client.fail_next_read = True
        status, failed = self.request("POST", self.apply_path(plan_id), {"approval": token})
        self.assertEqual(status, 400)
        self.assertEqual(failed["error"], "readback_unavailable")
        status, replay = self.request("POST", self.apply_path(plan_id), {"approval": token})
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "operator_approval_reused")
        self.assertEqual(self.client.write_attempts, [])

    def test_valid_approval_dispatches_once_only_after_apply_preflight_read(self):
        status, preview = self.preview()
        token = self.approval(preview)
        events = self.client.events
        original_guard = main._guarded_dispatch

        def guarded(kind, callback, *args):
            events.append("guarded_dispatch")
            return original_guard(kind, callback, *args)

        self.client.events.clear()
        with patch.object(main, "_guarded_dispatch", side_effect=guarded):
            status, result = self.request(
                "POST", self.apply_path(preview["plan_id"]), {"approval": token})
        self.assertEqual(status, 200)
        self.assertEqual(result["before"], {"status": 1})
        self.assertEqual(result["after"], {"status": 0})
        self.assertEqual(self.client.write_attempts, [{"status": 0}])
        self.assertEqual(events, ["read", "read", "guarded_dispatch", "write", "read"])
        status, replay = self.request(
            "POST", self.apply_path(preview["plan_id"]), {"approval": token})
        self.assertEqual(status, 409)
        self.assertEqual(self.client.write_attempts, [{"status": 0}])

    def test_dispatch_rechecks_approval_expiry_immediately_before_write(self):
        writes = []
        with patch.object(main, "_ACTIVE_APPROVAL", {"kind": "switch-port-status", "expires_at": 100}), \
                patch.object(main.time, "time", return_value=100):
            with self.assertRaisesRegex(Exception, "operator_approval_expired"):
                main._guarded_dispatch("switch-port-status", lambda: writes.append(True))
        self.assertEqual(writes, [])

    def test_approval_expiring_during_connection_is_not_sent(self):
        from unittest.mock import MagicMock
        from app.openapi import OmadaOpenApiClient, OpenApiConfig
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site_id"
        client._switch_macs_by_site_ref[SITE] = {SWITCH: "00:11:22:33:44:55"}
        connection = MagicMock()
        with patch.object(client, "_access_token", return_value="fake"), \
                patch.object(client, "_connection", return_value=connection), \
                patch.object(main, "_operator_key", return_value=APPROVAL_KEY), \
                patch.object(main, "_ACTIVE_APPROVAL", {"kind": "switch-port-status", "expires_at": 100,
                                                        "key_digest": hashlib.sha256(APPROVAL_KEY).digest(), "client": client}), \
                patch.object(main.time, "time", side_effect=[99, 100]):
            with self.assertRaisesRegex(Exception, "operator_approval_expired"):
                main._guarded_dispatch("switch-port-status", client.put_switch_port_status,
                                       SITE, SWITCH, PORT, {"status": 0})
        connection.request.assert_not_called()
        connection.close.assert_called_once()

    def test_dispatch_guard_rejects_other_thread_and_second_use(self):
        outcomes = []
        class FakeClient:
            def write(self):
                def wrong_thread():
                    try:
                        self._write_dispatch_guard()
                    except Exception:
                        outcomes.append("other_thread_rejected")
                thread = threading.Thread(target=wrong_thread)
                thread.start()
                thread.join(timeout=2)
                self._write_dispatch_guard()
                outcomes.append("own_thread_allowed")
                try:
                    self._write_dispatch_guard()
                except Exception:
                    outcomes.append("reuse_rejected")
        client = FakeClient()
        with patch.object(main, "_operator_key", return_value=APPROVAL_KEY), \
                patch.object(main, "_ACTIVE_APPROVAL", {"kind": "poe", "expires_at": 100,
                                                        "key_digest": hashlib.sha256(APPROVAL_KEY).digest(), "client": client}), \
                patch.object(main.time, "time", return_value=99):
            main._guarded_dispatch("poe", client.write)
        self.assertEqual(outcomes, ["other_thread_rejected", "own_thread_allowed", "reuse_rejected"])
        self.assertIsNone(client._write_dispatch_guard)

    def test_rotated_operator_key_revokes_approval_before_send(self):
        sent = []
        class FakeClient:
            def write(self):
                self._write_dispatch_guard()
                sent.append(True)
        client = FakeClient()
        active = {"kind": "poe", "expires_at": 100,
                  "key_digest": hashlib.sha256(APPROVAL_KEY).digest(), "client": client}
        with patch.object(main, "_ACTIVE_APPROVAL", active), \
                patch.object(main.time, "time", return_value=99), \
                patch.object(main, "_operator_key", side_effect=[APPROVAL_KEY, OTHER_KEY]):
            with self.assertRaisesRegex(Exception, "operator_approval_revoked"):
                main._guarded_dispatch("poe", client.write)
        self.assertEqual(sent, [])

    def test_timeout_intent_recovers_and_old_approval_cannot_replay(self):
        status, preview = self.preview()
        token = self.approval(preview)
        plan_id = preview["plan_id"]
        self.client.fail_write = True
        status, result = self.request("POST", self.apply_path(plan_id), {"approval": token})
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "change_in_doubt")
        self.assertEqual(self.client.write_attempts, [{"status": 0}])

        # Release the file lock and reconstruct the service's process-local managers.
        self._reset_globals()
        status, listed = self.request("GET", "/v1/change-plans/switch-port-status/in-doubt")
        self.assertEqual(status, 200)
        self.assertEqual([item["plan_id"] for item in listed["items"]], [plan_id])
        status, inspected = self.request("GET", self.doubt_path(plan_id))
        self.assertEqual(status, 200)
        self.assertEqual(inspected["outcome"], "unknown")
        status, replay = self.request("POST", self.apply_path(plan_id), {"approval": token})
        self.assertEqual(status, 409)
        self.assertIn(replay["error"], {"plan_unavailable", "operator_approval_mismatch"})
        self.assertEqual(self.client.write_attempts, [{"status": 0}])


if __name__ == "__main__":
    unittest.main()
