from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from tools import wifi_diagnose
from tests.test_wifi_diagnose import (
    CALLER_TOKEN,
    PRIVATE_IP,
    PRIVATE_MARKER,
    PRIVATE_NAME,
    SITE_REF,
    _complete_payloads,
)


CLIENT_REF_1 = "b" * 24
CLIENT_REF_2 = "c" * 24
OTHER_CLIENT_REF = "d" * 24
OTHER_SITE_REF = "e" * 24
CLIENTS_ROUTE = f"/v1/sites/{SITE_REF}/clients"
CONNECTIONS_ROUTE = f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/connections"
SITE_ROUTES = (
    f"/v1/sites/{SITE_REF}/wifi/health/timeline",
    f"/v1/sites/{SITE_REF}/wifi/health/details",
    f"/v1/sites/{SITE_REF}/wifi/channels",
    f"/v1/sites/{SITE_REF}/wifi/client-signal-distribution",
    f"/v1/sites/{SITE_REF}/wifi/6ghz-ap-presence",
    f"/v1/sites/{SITE_REF}/wifi/rogue-ap-results",
)


class _FakeTTY:
    def __init__(self, input_text: str) -> None:
        self._input = io.StringIO(input_text)
        self._output = io.StringIO()
        self._closed_output: str | None = None

    def isatty(self) -> bool:
        return True

    def readline(self, size: int = -1) -> str:
        return self._input.readline(size)

    def write(self, value: str) -> int:
        return self._output.write(value)

    def flush(self) -> None:
        self._output.flush()

    def close(self) -> None:
        if self._closed_output is None:
            self._closed_output = self._output.getvalue()

    def getvalue(self) -> str:
        return self._closed_output if self._closed_output is not None else self._output.getvalue()


def _client(ref: str, *, channel: int, rssi: int, snr: int,
            active: bool = True) -> dict[str, object]:
    return {
        "client_ref": ref, "wireless": True, "radio_id": 1,
        "channel": channel, "rssi": rssi, "snr": snr, "active": active,
    }


def _connection_payload(client_ref: str = CLIENT_REF_2,
                        site_ref: str = SITE_REF) -> dict[str, object]:
    end_ms = int(time.time() * 1000)
    return {
        "status": "ok", "resource": "client_connection_history",
        "site_ref": site_ref, "client_ref": client_ref,
        "window_start_ms": end_ms - 86_400_000, "window_end_ms": end_ms,
        "count": 1,
        "items": [{"kind": "connection", "start_ms": end_ms - 1000,
                   "end_ms": end_ms, "duration_ms": 1000}],
    }


class _FakeConnector(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict[str, str]]] = []
    responses: dict[str, tuple[int, object, dict[str, str]]] = {}

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(("GET", self.path, dict(self.headers.items())))
        status, payload, headers = type(self).responses.get(
            self.path, (404, {"error": PRIVATE_MARKER}, {}))
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
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

    def do_PUT(self) -> None:  # noqa: N802
        type(self).requests.append(("PUT", self.path, dict(self.headers.items())))
        self.send_error(405)

    def do_PATCH(self) -> None:  # noqa: N802
        type(self).requests.append(("PATCH", self.path, dict(self.headers.items())))
        self.send_error(405)

    def log_message(self, *_args: object) -> None:
        return


class WifiDiagnoseClientTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeConnector.requests = []
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(CALLER_TOKEN + "\n")
        os.chmod(self.token_file, 0o600)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeConnector)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.set_responses()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temp.cleanup()

    def set_responses(self, *, clients: list[dict[str, object]] | None = None,
                      client_count: int | None = None,
                      connection_payload: object | None = None) -> None:
        _FakeConnector.requests = []
        payloads = _complete_payloads(SITE_REF)
        client_items = clients if clients is not None else [
            _client(CLIENT_REF_1, channel=1, rssi=-50, snr=30),
            _client(CLIENT_REF_2, channel=36, rssi=-75, snr=12, active=False),
        ]
        _FakeConnector.responses = {
            "/v1/sites": (200, payloads["/v1/sites"], {}),
            CLIENTS_ROUTE: (200, {
                "status": "ok", "resource": "clients",
                "count": len(client_items) if client_count is None else client_count,
                "items": client_items,
            }, {}),
            CONNECTIONS_ROUTE: (200,
                                _connection_payload() if connection_payload is None else connection_payload,
                                {}),
        }
        for route in SITE_ROUTES:
            _FakeConnector.responses[route] = (200, payloads[route], {})

    def invoke(self, tty: _FakeTTY | None, *extra: str) -> tuple[int, str, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        opener = (lambda: tty) if tty is not None else (lambda: io.StringIO("2\nja\n"))
        with patch.object(wifi_diagnose, "_open_tty", opener, create=True), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main([
                "--site-ref", SITE_REF, "--token-file", self.token_file,
                "--base-url", self.base_url, "--client-select", *extra,
            ])
        return code, stdout.getvalue(), stderr.getvalue(), tty.getvalue() if tty else ""

    def test_fresh_inventory_tty_choice_then_four_site_reads_and_one_bound_connections_read(self) -> None:
        tty = _FakeTTY("2\nja\n")
        code, stdout, stderr, prompt = self.invoke(tty)
        self.assertEqual(code, 0, stdout + stderr + prompt)
        self.assertEqual(stderr, "")
        self.assertEqual(
            [(method, path) for method, path, _ in _FakeConnector.requests],
            [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE),
             *(('GET', route) for route in SITE_ROUTES),
             ("GET", CONNECTIONS_ROUTE)],
        )
        self.assertLess(prompt.find("1"), len(prompt))
        report = json.loads(stdout)
        self.assertEqual(report["status"], "ok", stdout)
        client = report["client"]
        self.assertEqual(client["status"], "ok")
        self.assertEqual(client["capability_status"], "unknown")
        self.assertEqual(client["selection"], {
            "wireless": True, "radio_id": 1, "channel": 36,
            "rssi": -75, "snr": 12, "active": False,
        })
        self.assertEqual(client["connections"]["status"], "ok")
        self.assertEqual(client["connections"]["capability_status"], "unknown")
        self.assertEqual(client["connections"]["data"]["count"], 1)
        rendered = stdout + stderr + prompt
        for private in (CALLER_TOKEN, CLIENT_REF_1, CLIENT_REF_2,
                        PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER, "AA:BB:CC:DD:EE:FF"):
            self.assertNotIn(private, rendered)
        for method, _path, headers in _FakeConnector.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")

    def test_prevalidated_current_inventory_keeps_mcp_client_reference_current(self) -> None:
        payloads = _complete_payloads(SITE_REF)
        clients = {"status": "ok", "resource": "clients", "count": 1,
                   "items": [_client(CLIENT_REF_2, channel=36, rssi=-75,
                                     snr=12, active=False)]}
        calls: list[str] = []

        def requester(path: str) -> object:
            calls.append(path)
            if path in payloads:
                return payloads[path]
            if path == CONNECTIONS_ROUTE:
                return _connection_payload()
            raise wifi_diagnose.CliError("not_found")

        report = wifi_diagnose.run(
            SITE_REF, "", client_ref=CLIENT_REF_2, requester=requester,
            current_inventory={
                "sites": {"status": "ok", "resource": "sites", "count": 1,
                          "items": [{"site_ref": SITE_REF}]},
                "clients": clients,
            },
        )
        self.assertIn(report["status"], {"ok", "partial"})
        self.assertEqual(report["client"]["connections"]["status"], "ok")
        self.assertNotIn("/v1/sites", calls)
        self.assertNotIn(CLIENTS_ROUTE, calls)
        self.assertIn(CONNECTIONS_ROUTE, calls)
        prior_call_count = len(calls)
        with self.assertRaisesRegex(wifi_diagnose.CliError, "client_ref_unknown"):
            wifi_diagnose.run(
                SITE_REF, "", client_ref=CLIENT_REF_2, requester=requester,
                current_inventory={
                    "sites": {"status": "ok", "resource": "sites", "count": 1,
                              "items": [{"site_ref": SITE_REF}]},
                    "clients": {"status": "ok", "resource": "clients", "count": 1,
                                "items": [_client(CLIENT_REF_1, channel=1,
                                                  rssi=-50, snr=30)]},
                },
            )
        self.assertEqual(len(calls), prior_call_count)

    def test_no_tty_eof_cancel_and_invalid_choice_make_no_client_request(self) -> None:
        for input_text in ("", "x\n", "3\nja\n", "2\nnein\n"):
            with self.subTest(input=input_text):
                self.set_responses()
                tty = _FakeTTY(input_text)
                code, stdout, stderr, prompt = self.invoke(tty)
                self.assertNotEqual(code, 0)
                self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                                 [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE)])
                self.assertNotIn(CALLER_TOKEN, stdout + stderr + prompt)
                self.assertNotIn(PRIVATE_NAME, stdout + stderr + prompt)
        self.set_responses()
        code, stdout, stderr, _ = self.invoke(None)
        self.assertNotEqual(code, 0)
        self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                         [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE)])

    def test_duplicate_visible_fingerprint_is_ambiguous_and_stops_before_choice(self) -> None:
        duplicated = [
            _client(CLIENT_REF_1, channel=36, rssi=-60, snr=20),
            _client(CLIENT_REF_2, channel=36, rssi=-60, snr=20),
        ]
        self.set_responses(clients=duplicated, client_count=2)
        tty = _FakeTTY("1\nja\n")
        code, stdout, stderr, prompt = self.invoke(tty)
        self.assertNotEqual(code, 0)
        self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                         [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE)])
        self.assertNotIn(CLIENT_REF_1, stdout + stderr + prompt)

    def test_candidate_without_any_visible_selection_feature_cannot_be_selected(self) -> None:
        self.set_responses(clients=[{"client_ref": CLIENT_REF_1}], client_count=1)
        tty = _FakeTTY("1\nja\n")
        code, stdout, stderr, prompt = self.invoke(tty)
        self.assertNotEqual(code, 0)
        self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                         [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE)])
        for private in (CALLER_TOKEN, CLIENT_REF_1, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)


    def test_bad_client_count_and_duplicate_refs_fail_closed_before_tty_or_diagnostics(self) -> None:
        for clients, count in (
            ([_client(CLIENT_REF_1, channel=1, rssi=-40, snr=30)], 2),
            ([_client(CLIENT_REF_1, channel=1, rssi=-40, snr=30),
              _client(CLIENT_REF_1, channel=6, rssi=-60, snr=20)], 2),
            ([_client("not-a-ref", channel=1, rssi=-40, snr=30)], 1),
        ):
            with self.subTest(count=count, clients=clients):
                self.set_responses(clients=clients, client_count=count)
                tty = _FakeTTY("1\nja\n")
                code, stdout, stderr, _ = self.invoke(tty)
                self.assertNotEqual(code, 0)
                self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                                 [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE)])
                self.assertNotIn(CALLER_TOKEN, stdout + stderr)

        over_limit = [
            _client(f"{index:024x}", channel=index,
                    rssi=-(index % 90), snr=index % 40)
            for index in range(wifi_diagnose._MAX_CLIENT_INVENTORY + 1)
        ]
        self.set_responses(clients=over_limit, client_count=len(over_limit))
        tty = _FakeTTY("1\nja\n")
        code, stdout, stderr, _ = self.invoke(tty)
        self.assertNotEqual(code, 0)
        self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                         [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE)])
        self.assertNotIn(CALLER_TOKEN, stdout + stderr)

    def test_private_fields_in_inventory_fail_closed_without_echo(self) -> None:
        hostile = _client(CLIENT_REF_1, channel=1, rssi=-40, snr=30)
        hostile.update({"name": PRIVATE_NAME, "mac": "AA:BB:CC:DD:EE:FF",
                        "ip": PRIVATE_IP, "private": PRIVATE_MARKER})
        self.set_responses(clients=[hostile], client_count=1)
        tty = _FakeTTY("1\nja\n")
        code, stdout, stderr, prompt = self.invoke(tty)
        self.assertNotEqual(code, 0)
        self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                         [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE)])
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                        "AA:BB:CC:DD:EE:FF"):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_connections_binding_failure_and_partial_metadata_are_sanitized(self) -> None:
        for payload in (
            _connection_payload(client_ref=OTHER_CLIENT_REF),
            _connection_payload(site_ref=OTHER_SITE_REF),
            {**_connection_payload(), "partial": True,
             "missing_fields": [PRIVATE_MARKER], "unknown_field_count": 2,
             "items": [{"kind": "connection", "start_ms": 0,
                        "duration_ms": 1000, "name": PRIVATE_NAME,
                        "mac": "AA:BB:CC:DD:EE:FF", "ip": PRIVATE_IP,
                        "content": PRIVATE_MARKER}]},
        ):
            with self.subTest(payload=payload):
                self.set_responses(connection_payload=payload)
                tty = _FakeTTY("2\nja\n")
                code, stdout, stderr, prompt = self.invoke(tty)
                self.assertIn(code, (0, 1))
                report = json.loads(stdout)
                self.assertIn(report["client"]["connections"]["status"], {"ok", "error"})
                self.assertEqual(report["client"]["capability_status"], "unknown")
                for private in (CALLER_TOKEN, OTHER_CLIENT_REF, OTHER_SITE_REF,
                                PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
                    self.assertNotIn(private, stdout + stderr + prompt)

    def test_connection_duration_extending_past_window_is_preserved_as_uncertain(self) -> None:
        payload = _connection_payload()
        end_ms = payload["window_end_ms"]
        assert isinstance(end_ms, int)
        payload["items"] = [{"kind": "connection", "start_ms": end_ms - 1,
                             "duration_ms": 86_400_000}]
        payload["count"] = 1
        self.set_responses(connection_payload=payload)
        tty = _FakeTTY("2\nja\n")
        code, stdout, stderr, prompt = self.invoke(tty)
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        connections = report["client"]["connections"]
        self.assertTrue(connections["partial"])
        self.assertEqual(connections["data"], {
            "count": 1,
            "items": [{"kind": "connection", "start_ms": end_ms - 1,
                       "duration_ms": 86_400_000}],
        })
        self.assertNotIn("end_ms", connections["data"]["items"][0])
        for private in (CALLER_TOKEN, CLIENT_REF_2, PRIVATE_NAME, PRIVATE_IP,
                        PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_ap_and_client_drilldowns_are_mutually_exclusive(self) -> None:
        code, stdout, stderr, _ = self.invoke(None, "--ap-ref", "f" * 24)
        self.assertNotEqual(code, 0)
        self.assertEqual(_FakeConnector.requests, [])
        self.assertNotIn(CALLER_TOKEN, stdout + stderr)


if __name__ == "__main__":
    unittest.main()
