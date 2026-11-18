from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from tests.test_wifi_diagnose import CALLER_TOKEN, PRIVATE_IP, PRIVATE_MARKER, PRIVATE_NAME, SITE_REF, _complete_payloads
from tests.test_wifi_diagnose_client import (
    CLIENT_REF_1, CLIENT_REF_2, CLIENTS_ROUTE, CONNECTIONS_ROUTE, SITE_ROUTES,
    _FakeTTY, _client,
)
from tools import wifi_diagnose


PRIVATE_SITE_ID = "long-duration-private-site"
PRIVATE_CLIENT_MAC = "AA:BB:CC:DD:EE:FF"
OTHER_CLIENT_MAC = "11:22:33:44:55:66"
UPSTREAM_TOKEN = "synthetic-upstream-token"
TWO_DAYS_MS = 172_800_000
MAX_INT64 = 2**63 - 1


class _CliHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict[str, str]]] = []
    responses: dict[str, object] = {}

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(("GET", self.path, dict(self.headers.items())))
        payload = type(self).responses.get(self.path, {"error": PRIVATE_MARKER})
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200 if self.path in type(self).responses else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self) -> None:  # noqa: N802
        type(self).requests.append(("POST", self.path, dict(self.headers.items())))
        self.send_error(405)

    do_PUT = do_POST
    do_PATCH = do_POST

    def log_message(self, *_args: object) -> None:
        return


class ClientLongDurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(CALLER_TOKEN)
        os.chmod(self.token_file, 0o600)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64, page_size=10, max_pages=2))
        self.client._site_ids_by_ref = {SITE_REF: PRIVATE_SITE_ID}
        self.client._client_macs_by_site_ref = {SITE_REF: {CLIENT_REF_2: PRIVATE_CLIENT_MAC}}
        self.upstream_calls: list[tuple[str, str]] = []
        self.upstream_result: dict[str, object] = {}

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.upstream_calls.append((method, path))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, UPSTREAM_TOKEN)
            parsed = urlsplit(path)
            self.assertEqual(parsed.path,
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/clients/{PRIVATE_CLIENT_MAC}/client-connection")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end"})
            self.assertEqual(int(query["end"][0]) - int(query["start"][0]), 86_400_000)
            return {"result": self.upstream_result}

        self.request_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.request_patch.start()
        self.access_patch = patch.object(self.client, "_access_token", return_value=UPSTREAM_TOKEN)
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_file})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.logs = io.StringIO()
        self.print_patch = patch.object(builtins, "print", lambda *args, **_kwargs:
                                        self.logs.write(" ".join(map(str, args)) + "\n"))
        self.print_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.print_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.request_patch.stop()
        self.temp.cleanup()

    def api_read(self) -> dict[str, object]:
        return self.client.read_client_connection_history(SITE_REF, CLIENT_REF_2)

    def set_api_duration(self, duration: object) -> None:
        now_ms = int(time.time() * 1000)
        self.upstream_result = {"connections": [{"start": now_ms - 1000, "duration": duration}],
                                "roamings": []}

    def test_api_preserves_48_hour_int64_duration_and_fixed_24_hour_query(self) -> None:
        self.set_api_duration(TWO_DAYS_MS)
        payload = self.api_read()
        self.assertEqual(payload["resource"], "client_connection_history")
        item = payload["items"][0]
        self.assertEqual(item["duration_ms"], TWO_DAYS_MS)
        self.assertNotIn("end_ms", item)
        self.assertNotIn("state", item)
        self.assertEqual(len(self.upstream_calls), 1)
        self.assertEqual(self.upstream_calls[0][0], "GET")
        for private in (PRIVATE_SITE_ID, PRIVATE_CLIENT_MAC, OTHER_CLIENT_MAC):
            self.assertNotIn(private, json.dumps(payload) + self.logs.getvalue())

    def test_api_rejects_bool_negative_and_out_of_int64_duration(self) -> None:
        for duration in (True, -1, MAX_INT64 + 1):
            with self.subTest(duration=duration):
                self.upstream_calls.clear()
                self.set_api_duration(duration)
                with self.assertRaises(OpenApiError) as caught:
                    self.api_read()
                self.assertEqual(caught.exception.code, "openapi_response_invalid")
                self.assertEqual(len(self.upstream_calls), 1)
                self.assertNotIn(PRIVATE_CLIENT_MAC, self.logs.getvalue())

    def test_cli_keeps_48_hour_raw_duration_marks_partial_and_invents_no_end_or_state(self) -> None:
        payloads = _complete_payloads(SITE_REF)
        now_ms = int(time.time() * 1000)
        payloads[CONNECTIONS_ROUTE] = {
            "status": "ok", "resource": "client_connection_history",
            "site_ref": SITE_REF, "client_ref": CLIENT_REF_2,
            "window_start_ms": now_ms - 86_400_000, "window_end_ms": now_ms,
            "count": 1,
            "items": [{"kind": "connection", "start_ms": now_ms - 1000,
                       "duration_ms": TWO_DAYS_MS}],
        }
        _CliHandler.requests = []
        _CliHandler.responses = {
            "/v1/sites": {"status": "ok", "resource": "sites", "count": 1,
                           "items": [{"site_ref": SITE_REF}]},
            CLIENTS_ROUTE: {"status": "ok", "resource": "clients", "count": 2,
                            "items": [_client(CLIENT_REF_1, channel=1, rssi=-50, snr=30),
                                      _client(CLIENT_REF_2, channel=36, rssi=-75, snr=12)]},
            **{route: value for route, value in payloads.items()},
            CONNECTIONS_ROUTE: payloads[CONNECTIONS_ROUTE],
        }
        cli_server = ThreadingHTTPServer(("127.0.0.1", 0), _CliHandler)
        cli_thread = threading.Thread(target=cli_server.serve_forever, daemon=True)
        cli_thread.start()
        try:
            stdout, stderr, tty = io.StringIO(), io.StringIO(), _FakeTTY("2\nja\n")
            self.print_patch.stop()
            try:
                with patch.object(wifi_diagnose, "_open_tty", return_value=tty), \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = wifi_diagnose.main([
                        "--site-ref", SITE_REF, "--client-select", "--token-file", self.token_file,
                        "--base-url", f"http://127.0.0.1:{cli_server.server_port}",
                    ])
            finally:
                self.print_patch.start()
            self.assertEqual(code, 0, stdout.getvalue() + stderr.getvalue())
            report = json.loads(stdout.getvalue())
            connection_data = report["client"]["connections"]
            self.assertTrue(connection_data["partial"])
            item = connection_data["data"]["items"][0]
            self.assertEqual(item, {"kind": "connection", "start_ms": now_ms - 1000,
                                    "duration_ms": TWO_DAYS_MS})
            self.assertNotIn("end_ms", item)
            self.assertNotIn("state", item)
            self.assertEqual(len(_CliHandler.requests), 9)
            self.assertTrue(all(method == "GET" for method, _, _ in _CliHandler.requests))
            self.assertIn(CONNECTIONS_ROUTE, [path for _, path, _ in _CliHandler.requests])
            for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                            CLIENT_REF_1, CLIENT_REF_2):
                self.assertNotIn(private, stdout.getvalue() + stderr.getvalue() + tty.getvalue())
        finally:
            cli_server.shutdown()
            cli_thread.join(timeout=2)
            cli_server.server_close()


if __name__ == "__main__":
    unittest.main()
