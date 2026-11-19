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

from app.client_timeline import project_client_timeline
from app.client_health_timeline import project_client_health_timeline
from app.client_history import project_client_history
from tools import wifi_diagnose
from tests.test_wifi_diagnose import (
    CALLER_TOKEN,
    PRIVATE_IP,
    PRIVATE_MARKER,
    PRIVATE_NAME,
    SITE_REF,
    _complete_payloads,
)
from tests.test_wifi_diagnose_client import (
    CLIENT_REF_1,
    CLIENT_REF_2,
    CLIENTS_ROUTE,
    SITE_ROUTES,
    _FakeTTY,
    _client,
)


CLIENT_TIMELINE_ROUTES = tuple(
    f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/timeline/{kind}"
    for kind in ("connect", "disconnect", "roaming", "blocked")
)
CLIENT_CONNECTION_ROUTE = f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/connections"
CLIENT_HEALTH_TIMELINE_ROUTE = f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/health/timeline"
CLIENT_HISTORY_ROUTE = f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/history"
PRIVATE_CLIENT_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_CLIENT_MAC = "11:22:33:44:55:66"
OTHER_CLIENT_REF = "d" * 24
OTHER_SITE_REF = "e" * 24
KINDS = ("connect", "disconnect", "roaming", "blocked")
TYPE_BY_KIND = dict(zip(KINDS, (0, 1, 2, 3)))


def _timeline_payload(kind: str, *, site_ref: str = SITE_REF,
                      client_ref: str = CLIENT_REF_2,
                      event_type: int | None = None,
                      bad_event: bool = False,
                      include_session_mac: bool = True) -> dict[str, object]:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 86_400_000
    event: dict[str, object] = {
        "time": end_ms - 1000,
        "eventType": 999 if bad_event else (TYPE_BY_KIND[kind] if event_type is None else event_type),
        "content": PRIVATE_NAME,
        "attributes": {"ssid": PRIVATE_MARKER, "ip": PRIVATE_IP,
                       "mac": OTHER_CLIENT_MAC},
    }
    session = {"start": end_ms - 5000, "end": end_ms, "events": [event]}
    if include_session_mac:
        session["mac"] = PRIVATE_CLIENT_MAC
    projected = project_client_timeline(
        [session],
        start_ms, end_ms, PRIVATE_CLIENT_MAC,
    )
    return {
        **projected, "site_ref": site_ref, "client_ref": client_ref,
        "kind": kind, "window_start_ms": start_ms, "window_end_ms": end_ms,
    }


def _connections_payload() -> dict[str, object]:
    end_ms = int(time.time() * 1000)
    return {
        "status": "ok", "resource": "client_connection_history",
        "client_ref": CLIENT_REF_2,
        "window_start_ms": end_ms - 86_400_000, "window_end_ms": end_ms,
        "count": 1,
        "items": [{"kind": "connection", "start_ms": end_ms - 2000,
                   "end_ms": end_ms - 1000, "duration_ms": 1000}],
    }


def _health_timeline_payload(*, site_ref: str = SITE_REF,
                             client_ref: str = CLIENT_REF_2,
                             invalid_point: bool = False,
                             hostile: bool = False) -> dict[str, object]:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 86_400_000
    source = {"scores": [
        {"time": start_ms + 10, "score": 61},
        {"time": end_ms, "score": True if invalid_point else 84},
    ]}
    if hostile:
        source["incident"] = PRIVATE_MARKER
        source["scores"][1].update({"mac": PRIVATE_CLIENT_MAC, "name": PRIVATE_NAME,
                                    "ip": PRIVATE_IP, "note": PRIVATE_MARKER})
    projected = project_client_health_timeline(source, start_ms, end_ms)
    return {**projected, "site_ref": site_ref, "client_ref": client_ref,
            "window_start_ms": start_ms, "window_end_ms": end_ms}


def _client_history_payload(*, site_ref: str = SITE_REF,
                            client_ref: str = CLIENT_REF_2,
                            missing_safe_field: bool = False) -> dict[str, object]:
    row = {
        "mac": PRIVATE_CLIENT_MAC, "download": 1234, "upload": 5678,
        "duration": 900, "lastSeen": 1767355000, "port": 3, "vid": 42,
        "reasonType": 4, "guest": False, "associationTime": 12,
        "associated": 1767354000, "id": "private-history-row-id",
        "name": PRIVATE_NAME, "ssid": PRIVATE_MARKER, "reason": PRIVATE_NAME,
        "deviceName": PRIVATE_NAME, "ip": PRIVATE_IP, "ipv6List": ["2001:db8::1"],
        "authInfo": [{"authType": 1, "info": PRIVATE_MARKER}],
    }
    if missing_safe_field:
        row.pop("duration")
    projected = project_client_history([row], PRIVATE_CLIENT_MAC)
    return {**projected, "site_ref": site_ref, "client_ref": client_ref}


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


class WifiDiagnoseClientTimelineTests(unittest.TestCase):
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

    def set_responses(self, *, timeline_overrides: dict[str, tuple[int, object, dict[str, str]]] | None = None,
                      health_overrides: dict[str, tuple[int, object, dict[str, str]]] | None = None,
                      connection_payload: object | None = None,
                      clients: list[dict[str, object]] | None = None) -> None:
        _FakeConnector.requests = []
        payloads = _complete_payloads(SITE_REF)
        client_items = clients if clients is not None else [
            _client(CLIENT_REF_1, channel=1, rssi=-50, snr=30),
            _client(CLIENT_REF_2, channel=36, rssi=-75, snr=12, active=False),
        ]
        _FakeConnector.responses = {
            "/v1/sites": (200, payloads["/v1/sites"], {}),
            CLIENTS_ROUTE: (200, {"status": "ok", "resource": "clients",
                                  "count": len(client_items), "items": client_items}, {}),
            CLIENT_CONNECTION_ROUTE: (200, connection_payload or _connections_payload(), {}),
            CLIENT_HISTORY_ROUTE: (200, _client_history_payload(), {}),
        }
        for route in SITE_ROUTES:
            _FakeConnector.responses[route] = (200, payloads[route], {})
        for kind, route in zip(KINDS, CLIENT_TIMELINE_ROUTES):
            _FakeConnector.responses[route] = (200, _timeline_payload(kind), {})
        _FakeConnector.responses[CLIENT_HEALTH_TIMELINE_ROUTE] = (
            200, _health_timeline_payload(), {})
        if timeline_overrides:
            _FakeConnector.responses.update(timeline_overrides)
        if health_overrides:
            _FakeConnector.responses.update(health_overrides)

    def invoke(self, tty: _FakeTTY, *extra: str) -> tuple[int, str, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(wifi_diagnose, "_open_tty", lambda: tty), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main([
                "--site-ref", SITE_REF, "--token-file", self.token_file,
                "--base-url", self.base_url, "--client-select", "--client-timeline", *extra,
            ])
        return code, stdout.getvalue(), stderr.getvalue(), tty.getvalue()

    def test_direct_client_ref_runs_full_fixed_diagnostic_without_exposing_ref(self) -> None:
        report = wifi_diagnose.run(
            SITE_REF, self.token_file, base_url=self.base_url,
            client_ref=CLIENT_REF_2, client_timeline=True)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["client"]["connections"]["status"], "ok")
        self.assertEqual(set(report["client"]["timelines"]), set(KINDS) | {"association"})
        self.assertEqual(len(_FakeConnector.requests), 15)
        serialized = json.dumps(report)
        self.assertNotIn(CLIENT_REF_2, serialized)
        self.assertNotIn(CLIENT_REF_1, serialized)

    def test_direct_client_ref_must_be_present_in_fresh_site_inventory(self) -> None:
        with self.assertRaises(wifi_diagnose.CliError) as caught:
            wifi_diagnose.run(SITE_REF, self.token_file, base_url=self.base_url,
                              client_ref="f" * 24, client_timeline=True)
        self.assertEqual(caught.exception.code, "client_ref_unknown")
        self.assertEqual([path for _, path, _ in _FakeConnector.requests],
                         ["/v1/sites", CLIENTS_ROUTE])

    def test_uses_fresh_ref_and_exactly_thirteen_gets_with_separate_timeline_results(self) -> None:
        tty = _FakeTTY("2\nja\n")
        code, stdout, stderr, prompt = self.invoke(tty)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        expected = [("GET", "/v1/sites"), ("GET", CLIENTS_ROUTE),
                    *(('GET', route) for route in SITE_ROUTES),
                    ("GET", CLIENT_CONNECTION_ROUTE),
                    *(('GET', route) for route in CLIENT_TIMELINE_ROUTES),
                    ("GET", CLIENT_HEALTH_TIMELINE_ROUTE),
                    ("GET", CLIENT_HISTORY_ROUTE)]
        self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests], expected)
        self.assertEqual(len(_FakeConnector.requests), 15)
        for method, _path, headers in _FakeConnector.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")
        report = json.loads(stdout)
        self.assertEqual(report["status"], "ok")
        client = report["client"]
        self.assertEqual(client["connections"]["status"], "ok")
        self.assertEqual(client["timelines"]["association"]["source_kind"], "disconnect")
        self.assertEqual(client["timelines"]["disconnect"]["status"], "ok")
        self.assertEqual(client["timelines"]["blocked"]["status"], "ok")
        timelines = client["timelines"]
        self.assertEqual(set(timelines), set(KINDS) | {"association"})
        for kind, expected_type in TYPE_BY_KIND.items():
            result = timelines[kind]
            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["partial"])
            self.assertEqual(result["capability_status"], "unknown")
            self.assertEqual(result["data"]["sessions"][0]["events"][0]["event_type"], expected_type)
            self.assertEqual(result["window"]["end_ms"] - result["window"]["start_ms"], 86_400_000)
        health = client["health_timeline"]
        self.assertEqual(health["status"], "ok")
        self.assertFalse(health["partial"])
        self.assertEqual(health["capability_status"], "unknown")
        self.assertEqual([item["score"] for item in health["data"]["scores"]], [61, 84])
        self.assertEqual(health["window"]["end_ms"] - health["window"]["start_ms"], 86_400_000)
        history = client["history"]
        self.assertEqual(history["status"], "ok")
        self.assertFalse(history["partial"])
        self.assertEqual(history["capability_status"], "unknown")
        self.assertEqual(history["data"]["count"], 1)
        self.assertEqual(history["data"]["rows"][0]["download"], 1234)
        self.assertEqual(history["data"]["rows"][0]["guest"], False)
        for private in (CALLER_TOKEN, CLIENT_REF_1, CLIENT_REF_2, PRIVATE_CLIENT_MAC,
                        OTHER_CLIENT_MAC, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_one_timeline_failure_is_isolated_and_capability_remains_unknown(self) -> None:
        failed_route = CLIENT_TIMELINE_ROUTES[1]
        self.set_responses(timeline_overrides={
            failed_route: (502, {"error": PRIVATE_MARKER, "message": PRIVATE_NAME}, {}),
        })
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["client"]["timelines"]["association"]["status"], "error")
        self.assertEqual(report["client"]["timelines"]["association"]["capability_status"], "unknown")
        self.assertEqual(report["client"]["timelines"]["connect"]["status"], "ok")
        for private in (CALLER_TOKEN, PRIVATE_MARKER, PRIVATE_NAME):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_partial_projector_response_keeps_only_bounded_numeric_event_values(self) -> None:
        route = CLIENT_TIMELINE_ROUTES[0]
        payload = _timeline_payload("connect", bad_event=True)
        payload["private_marker"] = PRIVATE_MARKER
        self.set_responses(timeline_overrides={route: (200, payload, {})})
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        timeline = report["client"]["timelines"]["connect"]
        self.assertTrue(timeline["partial"])
        event = timeline["data"]["sessions"][0]["events"][0]
        self.assertNotIn("event_type", event)
        for private in (CALLER_TOKEN, PRIVATE_CLIENT_MAC, OTHER_CLIENT_MAC,
                        PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER, "attributes", "content"):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_missing_session_mac_fixture_is_not_emitted_as_client_data(self) -> None:
        route = CLIENT_TIMELINE_ROUTES[0]
        payload = _timeline_payload("connect", include_session_mac=False)
        self.assertTrue(payload["partial"])
        self.assertEqual(payload["data"], {"sessions": []})
        self.set_responses(timeline_overrides={route: (200, payload, {})})
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        timeline = report["client"]["timelines"]["connect"]
        self.assertTrue(timeline["partial"])
        self.assertEqual(timeline["data"], {"sessions": []})
        self.assertEqual(report["client"]["timelines"]["association"]["status"], "ok")
        for private in (CALLER_TOKEN, CLIENT_REF_2, PRIVATE_CLIENT_MAC,
                        PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_wrong_site_or_client_binding_is_confined_to_affected_kind(self) -> None:
        wrong_site = _timeline_payload("roaming", site_ref=OTHER_SITE_REF)
        wrong_client = _timeline_payload("blocked", client_ref=OTHER_CLIENT_REF)
        self.set_responses(timeline_overrides={
            CLIENT_TIMELINE_ROUTES[2]: (200, wrong_site, {}),
            CLIENT_TIMELINE_ROUTES[1]: (200, wrong_client, {}),
        })
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertEqual(report["client"]["timelines"]["roaming"]["status"], "error")
        self.assertEqual(report["client"]["timelines"]["disconnect"]["status"], "error")
        self.assertEqual(report["client"]["timelines"]["connect"]["status"], "ok")
        for private in (CALLER_TOKEN, OTHER_SITE_REF, OTHER_CLIENT_REF,
                        PRIVATE_CLIENT_MAC, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_health_timeline_failure_partial_and_bad_binding_are_separate_and_sanitized(self) -> None:
        wrong_ref = _health_timeline_payload(client_ref=OTHER_CLIENT_REF)
        self.set_responses(health_overrides={
            CLIENT_HEALTH_TIMELINE_ROUTE: (200, wrong_ref, {}),
        })
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        health = report["client"]["health_timeline"]
        self.assertEqual(health["status"], "error")
        self.assertEqual(health["capability_status"], "unknown")
        self.assertEqual(report["client"]["timelines"]["connect"]["status"], "ok")
        self.assertEqual(report["status"], "partial")
        self.assertEqual(len(_FakeConnector.requests), 15)
        self.assertTrue(all(method == "GET" for method, _, _ in _FakeConnector.requests))
        for private in (CALLER_TOKEN, OTHER_CLIENT_REF, PRIVATE_CLIENT_MAC,
                        PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

        self.set_responses(health_overrides={
            CLIENT_HEALTH_TIMELINE_ROUTE: (200, _health_timeline_payload(invalid_point=True), {}),
        })
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        health = json.loads(stdout)["client"]["health_timeline"]
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["partial"])
        self.assertEqual(health["capability_status"], "unknown")
        self.assertNotIn("score", health["data"]["scores"][1])
        for private in (CALLER_TOKEN, PRIVATE_CLIENT_MAC, PRIVATE_NAME,
                        PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_health_timeline_transport_error_isolated_and_text_mode_has_no_identity_values(self) -> None:
        self.set_responses(health_overrides={
            CLIENT_HEALTH_TIMELINE_ROUTE: (502, {"error": PRIVATE_MARKER, "name": PRIVATE_NAME}, {}),
        })
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertEqual(report["client"]["health_timeline"]["status"], "error")
        self.assertEqual(report["client"]["health_timeline"]["capability_status"], "unknown")
        self.assertEqual(report["client"]["timelines"]["association"]["status"], "ok")
        self.assertEqual(len(_FakeConnector.requests), 15)

    def test_history_partial_missing_safe_fields_and_wrong_binding_are_separate(self) -> None:
        payload = _client_history_payload(missing_safe_field=True)
        self.set_responses(health_overrides={
            CLIENT_HISTORY_ROUTE: (200, payload, {}),
        })
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        history = report["client"]["history"]
        self.assertEqual(history["status"], "ok")
        self.assertTrue(history["partial"])
        self.assertEqual(history["data"]["rows"][0]["download"], 1234)
        self.assertNotIn("duration", history["data"]["rows"][0])
        self.assertEqual(report["client"]["timelines"]["connect"]["status"], "ok")
        self.assertEqual(len(_FakeConnector.requests), 15)
        for private in (CALLER_TOKEN, CLIENT_REF_2, PRIVATE_CLIENT_MAC, PRIVATE_NAME,
                        PRIVATE_IP, PRIVATE_MARKER, "private-history-row-id", "authInfo"):
            self.assertNotIn(private, stdout + stderr + prompt)

        wrong = _client_history_payload(client_ref=OTHER_CLIENT_REF)
        self.set_responses(health_overrides={CLIENT_HISTORY_ROUTE: (200, wrong, {})})
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        history = json.loads(stdout)["client"]["history"]
        self.assertEqual(history["status"], "error")
        self.assertEqual(history["capability_status"], "unknown")
        self.assertEqual(len(_FakeConnector.requests), 15)
        for private in (CALLER_TOKEN, OTHER_CLIENT_REF, PRIVATE_CLIENT_MAC,
                        PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)
        for private in (CALLER_TOKEN, PRIVATE_CLIENT_MAC, PRIVATE_NAME,
                        PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

        self.set_responses()
        text_tty = _FakeTTY("2\nja\n")
        code, stdout, stderr, prompt = self.invoke(text_tty, "--format", "text")
        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn("Client-Gesundheits-Zeitreihe:", stdout)
        self.assertIn("Weitere Details: erneut mit --format json ausführen.", stdout)
        self.assertNotIn("61", stdout)
        self.assertNotIn(CLIENT_REF_2, stdout + stderr + prompt)
        self.assertNotIn(PRIVATE_CLIENT_MAC, stdout + stderr + prompt)
        self.assertEqual(len(_FakeConnector.requests), 15)

    def test_missing_session_mac_raw_projector_session_is_omitted(self) -> None:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - 86_400_000
        projected = project_client_timeline(
            [{"start": end_ms - 1000, "end": end_ms,
              "events": [{"time": end_ms - 500, "eventType": 2,
                          "content": PRIVATE_NAME,
                          "attributes": {"mac": PRIVATE_CLIENT_MAC}}]}],
            start_ms, end_ms, PRIVATE_CLIENT_MAC)
        payload = {**projected, "site_ref": SITE_REF, "client_ref": CLIENT_REF_2,
                   "kind": "roaming", "window_start_ms": start_ms,
                   "window_end_ms": end_ms}
        self.set_responses(timeline_overrides={
            CLIENT_TIMELINE_ROUTES[2]: (200, payload, {}),
        })
        code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        roaming = json.loads(stdout)["client"]["timelines"]["roaming"]
        self.assertEqual(roaming["status"], "ok")
        self.assertTrue(roaming["partial"])
        self.assertEqual(roaming["data"]["sessions"], [])
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_CLIENT_MAC,
                        CLIENT_REF_2, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_projector_bounds_reject_oversized_sessions_or_events_for_only_that_kind(self) -> None:
        base = _timeline_payload("connect")
        session = base["data"]["sessions"][0]
        for sessions in (
            [session] * 129,
            [{**session, "events": session["events"] * 9} for _ in range(128)],
        ):
            payload = dict(base)
            payload["data"] = {"sessions": sessions}
            self.set_responses(timeline_overrides={CLIENT_TIMELINE_ROUTES[0]: (200, payload, {})})
            code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
            self.assertEqual(code, 0, stdout + stderr)
            report = json.loads(stdout)
            timeline = report["client"]["timelines"]["connect"]
            self.assertEqual(timeline["status"], "error")
            self.assertEqual(timeline["capability_status"], "unknown")
            self.assertEqual(report["client"]["timelines"]["association"]["status"], "ok")
            for private in (CALLER_TOKEN, CLIENT_REF_2, PRIVATE_CLIENT_MAC,
                            PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
                self.assertNotIn(private, stdout + stderr + prompt)

    def test_invalid_projection_counts_are_rejected_without_affecting_other_kinds(self) -> None:
        base = _timeline_payload("roaming")
        for key, value in (("omitted_field_count", -1),
                           ("missing_fields", ["sessions.start"] * 4097)):
            payload = dict(base)
            payload[key] = value
            self.set_responses(timeline_overrides={CLIENT_TIMELINE_ROUTES[2]: (200, payload, {})})
            code, stdout, stderr, prompt = self.invoke(_FakeTTY("2\nja\n"))
            self.assertEqual(code, 0, stdout + stderr)
            report = json.loads(stdout)
            self.assertEqual(report["client"]["timelines"]["roaming"]["status"], "error")
            self.assertEqual(report["client"]["timelines"]["connect"]["status"], "ok")
            self.assertEqual(report["client"]["timelines"]["roaming"]["capability_status"], "unknown")
            for private in (CALLER_TOKEN, CLIENT_REF_2, PRIVATE_CLIENT_MAC,
                            PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
                self.assertNotIn(private, stdout + stderr + prompt)

    def test_ap_conflict_invalid_client_choice_or_timeline_flag_without_selection_stops_early(self) -> None:
        for extra in (("--ap-ref", "f" * 24),):
            with self.subTest(extra=extra):
                code, stdout, stderr, _ = self.invoke(_FakeTTY("2\nja\n"), *extra)
                self.assertNotEqual(code, 0)
                self.assertEqual(_FakeConnector.requests, [])
                self.assertNotIn(CALLER_TOKEN, stdout + stderr)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main([
                "--site-ref", SITE_REF, "--token-file", self.token_file,
                "--base-url", self.base_url, "--client-timeline",
            ])
        self.assertNotEqual(code, 0)
        self.assertIn("client_timeline_requires_selection", stdout.getvalue())
        self.assertEqual(_FakeConnector.requests, [])


if __name__ == "__main__":
    unittest.main()
