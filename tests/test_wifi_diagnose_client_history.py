from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from app.client_history import project_client_history
from tests.test_wifi_diagnose import CALLER_TOKEN, PRIVATE_IP, PRIVATE_MARKER, PRIVATE_NAME, SITE_REF, _complete_payloads
from tests.test_wifi_diagnose_client import (
    CLIENT_REF_1, CLIENT_REF_2, CLIENTS_ROUTE, CONNECTIONS_ROUTE, SITE_ROUTES,
    _FakeTTY, _client, _connection_payload,
)
from tests.test_wifi_diagnose_client_timeline import (
    CLIENT_HEALTH_TIMELINE_ROUTE, CLIENT_HISTORY_ROUTE, CLIENT_TIMELINE_ROUTES,
    _health_timeline_payload, _timeline_payload,
)
from tools import wifi_diagnose


PRIVATE_CLIENT_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_AUTH = "private-history-auth-info"
OTHER_CLIENT_REF = "d" * 24
OTHER_SITE_REF = "e" * 24


class _HistoryHttpHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict[str, str]]] = []
    responses: dict[str, object] = {}
    fail_routes: set[str] = set()

    def _respond(self, method: str) -> None:
        type(self).requests.append((method, self.path, dict(self.headers.items())))
        if method != "GET":
            status, payload = 405, {"error": "method_not_allowed"}
        elif self.path in type(self).fail_routes:
            status, payload = 502, {"error": PRIVATE_MARKER, "message": PRIVATE_NAME}
        elif self.path not in type(self).responses:
            status, payload = 404, {"error": PRIVATE_MARKER}
        else:
            status, payload = 200, type(self).responses[self.path]
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:  # noqa: N802
        self._respond("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._respond("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._respond("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._respond("PATCH")

    def log_message(self, *_args: object) -> None:
        return


def _history_payload(*, site_ref: str = SITE_REF, client_ref: str = CLIENT_REF_2,
                     missing_field: str | None = None) -> dict[str, object]:
    row = {
        "mac": PRIVATE_CLIENT_MAC, "download": 1024, "upload": 2048,
        "duration": 900, "lastSeen": 1767355000, "port": 3, "vid": 42,
        "reasonType": 4, "guest": False, "associationTime": 12,
        "associated": 1767354000, "id": "private-row-id", "name": PRIVATE_NAME,
        "ssid": PRIVATE_MARKER, "reason": "private-reason", "deviceName": PRIVATE_NAME,
        "ip": PRIVATE_IP, "ipv6List": ["2001:db8::10"],
        "authInfo": [{"authType": 1, "info": PRIVATE_AUTH}],
    }
    if missing_field is not None:
        row.pop(missing_field, None)
    projected = project_client_history([row], PRIVATE_CLIENT_MAC)
    return {**projected, "site_ref": site_ref, "client_ref": client_ref}


class WifiDiagnoseClientHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_path = os.path.join(self.temp.name, "caller-token")
        with open(self.token_path, "w", encoding="ascii") as stream:
            stream.write(CALLER_TOKEN + "\n")
        os.chmod(self.token_path, 0o600)
        self.fail_routes: set[str] = set()
        self.history_response: object = _history_payload()
        payloads = _complete_payloads(SITE_REF)
        self.responses: dict[str, object] = {
            "/v1/sites": payloads["/v1/sites"],
            CLIENTS_ROUTE: {"status": "ok", "resource": "clients", "count": 2,
                            "items": [_client(CLIENT_REF_1, channel=1, rssi=-50, snr=30),
                                      _client(CLIENT_REF_2, channel=36, rssi=-75, snr=12,
                                              active=False)]},
            CONNECTIONS_ROUTE: _connection_payload(),
            CLIENT_HEALTH_TIMELINE_ROUTE: _health_timeline_payload(),
            CLIENT_HISTORY_ROUTE: self.history_response,
        }
        for route in SITE_ROUTES:
            self.responses[route] = payloads[route]
        for route, kind in zip(CLIENT_TIMELINE_ROUTES,
                               ("connect", "disconnect", "roaming", "blocked")):
            self.responses[route] = _timeline_payload(kind)
        _HistoryHttpHandler.requests = []
        _HistoryHttpHandler.responses = self.responses
        _HistoryHttpHandler.fail_routes = self.fail_routes
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _HistoryHttpHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temp.cleanup()

    def invoke(self, *, text: bool = False, tty_text: str = "2\nja\n"):
        stdout, stderr = io.StringIO(), io.StringIO()
        tty = _FakeTTY(tty_text)

        args = ["--site-ref", SITE_REF, "--token-file", self.token_path,
                "--base-url", self.base_url, "--client-select", "--client-timeline"]
        if text:
            args.extend(["--format", "text"])
        with patch.object(wifi_diagnose, "_open_tty", lambda: tty), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main(args)
        return code, stdout.getvalue(), stderr.getvalue(), tty.getvalue()

    def expected_paths(self) -> list[str]:
        return ["/v1/sites", CLIENTS_ROUTE, *SITE_ROUTES, CONNECTIONS_ROUTE,
                *CLIENT_TIMELINE_ROUTES, CLIENT_HEALTH_TIMELINE_ROUTE, CLIENT_HISTORY_ROUTE]

    def test_fresh_ref_allowlisted_history_and_exact_max_thirteen_gets(self) -> None:
        code, stdout, stderr, tty = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        report = json.loads(stdout)
        self.assertEqual([path for method, path, _headers in _HistoryHttpHandler.requests
                          if method == "GET"], self.expected_paths())
        self.assertEqual(len(_HistoryHttpHandler.requests), 15)
        for method, _path, headers in _HistoryHttpHandler.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")
        client = report["client"]
        history = client["history"]
        self.assertEqual(history["status"], "ok")
        self.assertFalse(history["partial"])
        self.assertEqual(history["capability_status"], "unknown")
        row = history["data"]["rows"][0]
        self.assertEqual(row, {
            "download": 1024, "upload": 2048, "duration": 900, "lastSeen": 1767355000,
            "port": 3, "vid": 42, "reasonType": 4, "guest": False,
            "associationTime": 12, "associated": 1767354000,
        })
        self.assertEqual(history["data"]["count"], 1)
        for private in (CALLER_TOKEN, CLIENT_REF_1, CLIENT_REF_2,
                        PRIVATE_CLIENT_MAC, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                        PRIVATE_AUTH, "private-reason", "private-row-id", "2001:db8::10"):
            self.assertNotIn(private, stdout + stderr + tty)

    def test_missing_or_invalid_fields_keep_history_partial_without_free_text(self) -> None:
        self.responses[CLIENT_HISTORY_ROUTE] = _history_payload(missing_field="duration")
        code, stdout, stderr, tty = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        history = json.loads(stdout)["client"]["history"]
        self.assertEqual(history["status"], "ok")
        self.assertTrue(history["partial"])
        row = history["data"]["rows"][0]
        self.assertNotIn("duration", row)
        self.assertEqual(row["download"], 1024)
        for private in (PRIVATE_CLIENT_MAC, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                        PRIVATE_AUTH, "private-reason", "private-row-id"):
            self.assertNotIn(private, stdout + stderr + tty)

        payload = _history_payload()
        payload["data"]["rows"][0]["download"] = "invalid-private-number"
        self.responses[CLIENT_HISTORY_ROUTE] = payload
        code, stdout, stderr, tty = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        history = json.loads(stdout)["client"]["history"]
        self.assertTrue(history["partial"])
        self.assertNotIn("download", history["data"]["rows"][0])
        self.assertNotIn("invalid-private-number", stdout + stderr + tty)

    def test_wrong_site_client_and_http_error_are_isolated_and_text_status_is_partial(self) -> None:
        wrong_site = _history_payload(site_ref=OTHER_SITE_REF)
        self.responses[CLIENT_HISTORY_ROUTE] = wrong_site
        code, stdout, stderr, tty = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        history = json.loads(stdout)["client"]["history"]
        self.assertEqual(history["status"], "error")
        self.assertEqual(history["capability_status"], "unknown")
        self.assertEqual(json.loads(stdout)["client"]["health_timeline"]["status"], "ok")
        self.assertNotIn(OTHER_SITE_REF, stdout + stderr + tty)

        self.responses[CLIENT_HISTORY_ROUTE] = _history_payload(client_ref=OTHER_CLIENT_REF)
        code, stdout, stderr, tty = self.invoke(text=True)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn("Gesamtzustand: teilweise", stdout)
        self.assertIn("Client-Verlauf: Fehler", stdout)
        self.assertIn("Weitere Details: erneut mit --format json ausführen.", stdout)
        self.assertNotIn(OTHER_CLIENT_REF, stdout + stderr + tty)

        self.fail_routes.add(CLIENT_HISTORY_ROUTE)
        code, stdout, stderr, tty = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(json.loads(stdout)["client"]["history"]["status"], "error")
        self.assertEqual(json.loads(stdout)["client"]["timelines"]["connect"]["status"], "ok")
        self.assertNotIn(PRIVATE_AUTH, stdout + stderr + tty)

    def test_unexpected_history_output_key_is_partial_and_redacted(self) -> None:
        payload = _history_payload()
        payload["unexpected_private_marker"] = "untrusted-private-output-value"
        _HistoryHttpHandler.responses[CLIENT_HISTORY_ROUTE] = payload
        code, stdout, stderr, tty = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        history = json.loads(stdout)["client"]["history"]
        self.assertEqual(history["status"], "ok")
        self.assertTrue(history["partial"])
        self.assertNotIn("unexpected_private_marker", json.dumps(history))
        self.assertNotIn("untrusted-private-output-value", stdout + stderr + tty)

    def test_more_than_four_thousand_rows_are_rejected_without_truncation(self) -> None:
        payload = _history_payload()
        payload["data"] = {"count": 4001, "rows": [{} for _ in range(4001)]}
        payload["partial"] = False
        payload["missing_field_count"] = 0
        payload["invalid_field_count"] = 0
        payload["unknown_field_count"] = 0
        payload["omitted_count"] = 0
        _HistoryHttpHandler.responses[CLIENT_HISTORY_ROUTE] = payload
        code, stdout, stderr, tty = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        history = json.loads(stdout)["client"]["history"]
        self.assertEqual(history["status"], "error")
        self.assertEqual(history["capability_status"], "unknown")
        self.assertNotIn("data", history)
        self.assertEqual(len(_HistoryHttpHandler.requests), 15)


if __name__ == "__main__":
    unittest.main()
