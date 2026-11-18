from __future__ import annotations

import json
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
from app.change_journal import ChangePlanJournal, derive_controller_binding
from app.operator_approval import sign_approval


TOKEN = "journal-http-caller-token-longer-than-thirty-two-characters"
KEY = b"r" * 32
URL = "https://controller.example:8043"
CONTROLLER = "journal-controller"
SITE = "a" * 24
SSID = "b" * 24


class FakeClient:
    def __init__(self, key_file: str | None):
        self.config = SimpleNamespace(reference_key_file=key_file,
                                      base_url=URL, controller_id=CONTROLLER)
        self._ref_key = KEY
        self.state = {"ssidEnable": True}
        self.writes: list[object] = []

    def read_ssid_enable_state(self, _site: str, _ssid: str):
        return dict(self.state)

    def patch_ssid_enable(self, _site: str, _ssid: str, body: dict[str, bool]):
        self.writes.append(dict(body))
        self.state = dict(body)


class JournalRuntimeHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.token_file = self.root / "caller-token"
        self.token_file.write_text(TOKEN, encoding="ascii")
        self.key_file = self.root / "reference-key"
        self.key_file.write_bytes(KEY)
        self.operator_key = b"o" * 32
        self.operator_key_file = self.root / "operator-approval-key"
        self.operator_key_file.write_bytes(self.operator_key)
        os.chmod(self.operator_key_file, 0o600)
        self.client = FakeClient(str(self.key_file))
        self.env = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": str(self.token_file),
            "OMADA_ENABLE_WRITES": "true",
            "OMADA_CHANGE_JOURNAL_DIR": "",
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": str(self.operator_key_file),
        })
        self.env.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self._reset_globals()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _reset_globals(self):
        for name in ("_RADIO_PLANS", "_DNS_CACHE_PLANS", "_SSID_PLANS",
                     "_GATEWAY_IPV6_PLANS", "_POE_PLANS"):
            setattr(main, name, None)
        main._JOURNAL_RUNTIME = None
        main._CONSUMED_APPROVALS.clear()
        main._ACTIVE_APPROVAL = None

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        if main._JOURNAL_RUNTIME is not None:
            main._JOURNAL_RUNTIME.close()
        self._reset_globals()
        self.client_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def request(self, method: str, path: str, body=None, *, auth=True):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {}
        payload = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body if body is not None else {}).encode()
        if auth:
            headers["Authorization"] = "Bearer " + TOKEN
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        return response.status, data

    def configured_journal(self, path: Path | None = None):
        folder = path or (self.root / "journal")
        folder.mkdir(mode=0o700, exist_ok=True)
        os.chmod(folder, 0o700)
        os.environ["OMADA_CHANGE_JOURNAL_DIR"] = str(folder)
        return folder

    def approval_body(self, preview: dict[str, object]) -> dict[str, object]:
        request = preview["approval_request"]
        return {"approval": sign_approval(
            self.operator_key, operation="ssid", plan_id=preview["plan_id"],
            plan_digest=request["digest"], operator_id="op_" + "3" * 24,
            expires_at=int(time.time()) + 120)}

    def test_no_journal_is_readonly_but_preview_remains_available(self):
        status, state = self.request("GET", "/state")
        self.assertEqual(status, 200)
        self.assertTrue(state["read_only"])
        self.assertEqual(state["journal_status"], "unconfigured")
        status, preview = self.request("POST", f"/v1/sites/{SITE}/ssids/{SSID}/enable-preview",
                                       {"changes": {"ssidEnable": False}})
        self.assertEqual(status, 200)
        status, result = self.request("POST", f"/v1/ssid-plans/{preview['plan_id']}/apply", {})
        self.assertEqual(result["error"], "writes_disabled")
        self.assertEqual(self.client.writes, [])

    def test_missing_or_ephemeral_reference_key_fails_closed_and_lists_503(self):
        self.configured_journal()
        self.client.config.reference_key_file = None
        status, state = self.request("GET", "/state")
        self.assertEqual(status, 200)
        self.assertTrue(state["read_only"])
        self.assertEqual(state["journal_error"], "reference_key_not_persistent")
        status, result = self.request("GET", "/v1/change-plans/ssid/in-doubt")
        self.assertEqual(status, 503)
        self.assertEqual(result["error"], "reference_key_not_persistent")

    def test_invalid_loaded_reference_key_fails_closed(self):
        self.configured_journal()
        self.client._ref_key = b"too-short"
        status, state = self.request("GET", "/state")
        self.assertEqual(status, 200)
        self.assertTrue(state["read_only"])
        self.assertEqual(state["journal_error"], "reference_key_invalid")
        self.assertNotIn(self.client._ref_key.hex(), json.dumps(state))

    def test_missing_volume_is_readonly_and_does_not_claim_empty_in_doubt(self):
        missing = self.root / "missing-volume"
        os.environ["OMADA_CHANGE_JOURNAL_DIR"] = str(missing)
        status, state = self.request("GET", "/state")
        self.assertEqual(status, 200)
        self.assertTrue(state["read_only"])
        self.assertEqual(state["journal_status"], "unavailable")
        self.assertNotIn(str(missing), json.dumps(state))
        status, result = self.request("GET", "/v1/change-plans/ssid/in-doubt")
        self.assertEqual(status, 503)
        self.assertNotIn(str(missing), json.dumps(result))

    def test_ready_journal_allows_mock_apply_and_effective_state(self):
        self.configured_journal()
        status, state = self.request("GET", "/state")
        self.assertEqual(status, 200)
        self.assertFalse(state["read_only"])
        self.assertEqual(state["journal_status"], "ready")
        status, preview = self.request("POST", f"/v1/sites/{SITE}/ssids/{SSID}/enable-preview",
                                       {"changes": {"ssidEnable": False}})
        self.assertEqual(status, 200)
        status, applied = self.request("POST", f"/v1/ssid-plans/{preview['plan_id']}/apply",
                                       self.approval_body(preview))
        self.assertEqual(status, 200)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(self.client.writes, [{"ssidEnable": False}])

    def test_recovered_intent_is_visible_and_never_replayed(self):
        folder = self.configured_journal()
        journal = ChangePlanJournal(
            str(folder), controller_binding=derive_controller_binding(KEY, URL, CONTROLLER))
        plan_id = "d" * 48
        journal.record_dispatch_intent(
            operation="ssid", plan_id=plan_id,
            target_refs={"site_ref": SITE, "ssid_ref": SSID},
            before={"ssidEnable": True}, target={"ssidEnable": False})
        journal.close()
        status, result = self.request("GET", "/v1/change-plans/ssid/in-doubt")
        self.assertEqual(status, 200)
        self.assertEqual(result["items"][0]["plan_id"], plan_id)
        status, result = self.request("POST", f"/v1/ssid-plans/{plan_id}/apply", {})
        self.assertEqual(status, 409)
        self.assertEqual(self.client.writes, [])

    def test_binding_mismatch_fails_closed_without_secret_or_path_leak(self):
        folder = self.configured_journal()
        journal = ChangePlanJournal(
            str(folder), controller_binding=derive_controller_binding(b"x" * 32, URL, CONTROLLER))
        journal.record_dispatch_intent(
            operation="ssid", plan_id="e" * 48,
            target_refs={"site_ref": SITE, "ssid_ref": SSID},
            before={"ssidEnable": True}, target={"ssidEnable": False})
        journal.close()
        status, result = self.request("GET", "/v1/change-plans/ssid/in-doubt")
        self.assertEqual(status, 503)
        self.assertEqual(result["error"], "journal_binding_mismatch")
        self.assertNotIn(str(folder), json.dumps(result))
        self.assertNotIn(KEY.hex(), json.dumps(result))

    def test_in_doubt_endpoint_requires_auth_even_when_journal_ready(self):
        self.configured_journal()
        status, result = self.request("GET", "/v1/change-plans/ssid/in-doubt", auth=False)
        self.assertEqual(status, 401)
        self.assertEqual(result["error"], "unauthorized")

    def test_journal_write_failure_disables_writes_and_reports_unavailable(self):
        self.configured_journal()
        self.assertEqual(self.request("GET", "/state")[1]["journal_status"], "ready")
        journal = main._JOURNAL_RUNTIME.journal
        with patch("app.change_journal.os.fsync", side_effect=OSError("fixture failure")):
            with self.assertRaises(Exception):
                journal.record_dispatch_intent(
                    operation="ssid", plan_id="f" * 48,
                    target_refs={"site_ref": SITE, "ssid_ref": SSID},
                    before={"ssidEnable": True}, target={"ssidEnable": False})
        status, state = self.request("GET", "/state")
        self.assertEqual(status, 200)
        self.assertTrue(state["read_only"])
        self.assertEqual(state["journal_status"], "unavailable")
        self.assertEqual(state["journal_error"], "journal_unavailable")
        self.assertEqual(self.request("GET", "/v1/change-plans/ssid/in-doubt")[0], 503)
        self.assertEqual(self.client.writes, [])


if __name__ == "__main__":
    unittest.main()
