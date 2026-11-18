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
from tests.test_wifi_diagnose import (
    CALLER_TOKEN,
    PRIVATE_IP,
    PRIVATE_MARKER,
    PRIVATE_NAME,
    SITE_REF,
    _complete_payloads,
)
from tests.test_wifi_diagnose_ap import (
    AP_REF, LAN_TRAFFIC_ROUTE, WIFI_NEIGHBORS_ROUTE, SPEED_TEST_ROUTE, WIRED_DOWNLINK_ROUTE,
    WIRED_UPLINK_ROUTE, PORTS_ROUTE, LLDP_CONFIG_ROUTE, _ap_lldp_config_payload,
    PORT_VLANS_ROUTE, _ap_port_vlans_payload,
    WLAN_OVERRIDES_ROUTE, _ap_wlan_overrides_payload,
    _ap_ports_payload, _ap_wifi_neighbors_payload, _ap_speed_test_payload,
    _ap_wired_downlink_payload, _ap_wired_uplink_payload,
    _ap_health_payload,
    _ap_lan_traffic_payload,
    _ap_radio_config_payload,
    _ap_rf_scan_payload,
    _ap_timeline_payload,
    _device,
)
from tests.test_wifi_diagnose_client import (
    CLIENT_REF_1,
    CLIENT_REF_2,
    CLIENTS_ROUTE,
    CONNECTIONS_ROUTE,
    SITE_ROUTES as CLIENT_SITE_ROUTES,
    _FakeTTY,
    _client,
    _connection_payload,
)
from tools import wifi_diagnose


OTHER_SITE_REF = "b" * 24
OTHER_CLIENT_REF = "d" * 24
PRIVATE_CLIENT_MAC = "AA-BB-CC-DD-EE-FF"
ANSI_MARKER = "\x1b[31mTERM-CONTROL\x1b[0m"
SITE_ROUTES = tuple(path.replace(SITE_REF, SITE_REF) for path in CLIENT_SITE_ROUTES) + (
    f"/v1/sites/{SITE_REF}/wifi/wids-summary",
    f"/v1/sites/{SITE_REF}/wifi/wids-blacklist-summary",
    f"/v1/sites/{SITE_REF}/wifi/band-steering",
    f"/v1/sites/{SITE_REF}/wifi/optimization",
    f"/v1/sites/{SITE_REF}/wifi/roaming",
    f"/v1/sites/{SITE_REF}/topology/network-summary",
)
CLIENT_TIMELINE_ROUTES = tuple(
    f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/timeline/{kind}"
    for kind in ("connect", "association", "roaming", "disconnect")
)
CLIENT_HEALTH_TIMELINE_ROUTE = f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/health/timeline"
CLIENT_HISTORY_ROUTE = f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/history"


def _timeline_payload(kind: str, *, site_ref: str = SITE_REF,
                      client_ref: str = CLIENT_REF_2) -> dict[str, object]:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 86_400_000
    projected = project_client_timeline(
        [{"mac": PRIVATE_CLIENT_MAC, "start": end_ms - 2000, "end": end_ms,
          "events": [{"time": end_ms - 1000,
                      "eventType": {"connect": 0, "association": 1,
                                    "roaming": 2, "disconnect": 3}[kind],
                      "content": PRIVATE_NAME,
                      "attributes": {"ip": PRIVATE_IP, "ssid": PRIVATE_MARKER}}]}],
        start_ms, end_ms, PRIVATE_CLIENT_MAC,
    )
    return {**projected, "site_ref": site_ref, "client_ref": client_ref,
            "kind": kind, "window_start_ms": start_ms, "window_end_ms": end_ms}


def _health_timeline_payload() -> dict[str, object]:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 86_400_000
    projected = project_client_health_timeline(
        {"scores": [{"time": start_ms + 1, "score": 70},
                    {"time": end_ms, "score": 82}]}, start_ms, end_ms)
    return {**projected, "site_ref": SITE_REF, "client_ref": CLIENT_REF_2,
            "window_start_ms": start_ms, "window_end_ms": end_ms}


def _client_history_payload() -> dict[str, object]:
    row = {
        "mac": PRIVATE_CLIENT_MAC, "download": 1234, "upload": 5678,
        "duration": 900, "lastSeen": 1767355000, "port": 3, "vid": 42,
        "reasonType": 4, "guest": False, "associationTime": 12,
        "associated": 1767354000, "id": "private-history-id", "name": PRIVATE_NAME,
        "ssid": PRIVATE_MARKER, "reason": PRIVATE_MARKER, "deviceName": PRIVATE_NAME,
        "ip": PRIVATE_IP, "ipv6List": ["2001:db8::2"],
        "authInfo": [{"authType": 1, "info": PRIVATE_MARKER}],
    }
    projected = project_client_history([row], PRIVATE_CLIENT_MAC)
    return {**projected, "site_ref": SITE_REF, "client_ref": CLIENT_REF_2}


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


class WifiDiagnoseTextTests(unittest.TestCase):
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

    def set_responses(self, *, overrides: dict[str, tuple[int, object, dict[str, str]]] | None = None,
                      include_ap: bool = False,
                      include_client: bool = False) -> None:
        _FakeConnector.requests = []
        payloads = _complete_payloads(SITE_REF)
        for route in SITE_ROUTES:
            payload = payloads[route]
            if isinstance(payload, dict):
                payload.update({"name": PRIVATE_NAME, "ip": PRIVATE_IP,
                                "mac": PRIVATE_CLIENT_MAC, "hostile": ANSI_MARKER})
        _FakeConnector.responses = {
            "/v1/sites": (200, payloads["/v1/sites"], {}),
        }
        for route in SITE_ROUTES:
            _FakeConnector.responses[route] = (200, payloads[route], {})
        if include_ap:
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/devices"] = (
                200, {"status": "ok", "resource": "devices", "count": 1,
                      "items": [_device(AP_REF, "AP")]}, {})
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health"] = (
                200, _ap_health_payload(), {})
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health/timeline"] = (
                200, _ap_timeline_payload(), {})
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/radio-config"] = (
                200, _ap_radio_config_payload(), {})
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/rf-scan"] = (
                200, _ap_rf_scan_payload(), {})
            _FakeConnector.responses[LAN_TRAFFIC_ROUTE] = (
                200, _ap_lan_traffic_payload(), {})
            _FakeConnector.responses[WIFI_NEIGHBORS_ROUTE] = (
                200, _ap_wifi_neighbors_payload(), {})
            _FakeConnector.responses[SPEED_TEST_ROUTE] = (
                200, _ap_speed_test_payload(), {})
            _FakeConnector.responses[WIRED_DOWNLINK_ROUTE] = (
                200, _ap_wired_downlink_payload(), {})
            _FakeConnector.responses[WIRED_UPLINK_ROUTE] = (
                200, _ap_wired_uplink_payload(), {})
            _FakeConnector.responses[PORTS_ROUTE] = (200, _ap_ports_payload(), {})
            _FakeConnector.responses[LLDP_CONFIG_ROUTE] = (
                200, _ap_lldp_config_payload(), {})
            _FakeConnector.responses[PORT_VLANS_ROUTE] = (
                200, _ap_port_vlans_payload(), {})
            _FakeConnector.responses[WLAN_OVERRIDES_ROUTE] = (
                200, _ap_wlan_overrides_payload(), {})
        if include_client:
            _FakeConnector.responses[CLIENTS_ROUTE] = (
                200, {"status": "ok", "resource": "clients", "count": 2,
                      "items": [
                          _client(CLIENT_REF_1, channel=1, rssi=-50, snr=30),
                          _client(CLIENT_REF_2, channel=36, rssi=-75, snr=12, active=False),
                      ]}, {})
            _FakeConnector.responses[CONNECTIONS_ROUTE] = (200, _connection_payload(), {})
            for kind, route in zip(("connect", "association", "roaming", "disconnect"),
                                   CLIENT_TIMELINE_ROUTES):
                _FakeConnector.responses[route] = (200, _timeline_payload(kind), {})
            _FakeConnector.responses[CLIENT_HEALTH_TIMELINE_ROUTE] = (
                200, _health_timeline_payload(), {})
            _FakeConnector.responses[CLIENT_HISTORY_ROUTE] = (
                200, _client_history_payload(), {})
        if overrides:
            _FakeConnector.responses.update(overrides)

    def invoke(self, *extra: str, tty: _FakeTTY | None = None) -> tuple[int, str, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(wifi_diagnose, "_open_tty", lambda: tty), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main([
                "--site-ref", SITE_REF, "--token-file", self.token_file,
                "--base-url", self.base_url, *extra,
            ])
        return code, stdout.getvalue(), stderr.getvalue(), tty.getvalue() if tty else ""

    @staticmethod
    def _paths() -> list[str]:
        return [path for _method, path, _headers in _FakeConnector.requests]

    def test_json_remains_default_and_explicit_json_matches_without_extra_gets(self) -> None:
        code_default, default_out, default_err, _ = self.invoke()
        default_paths = self._paths()
        self.assertEqual(code_default, 0, default_out + default_err)
        default_object = json.loads(default_out)
        self.assertEqual(default_err, "")

        self.set_responses()
        code_json, json_out, json_err, _ = self.invoke("--format", "json")
        self.assertEqual(code_json, 0, json_out + json_err)
        self.assertEqual(json_err, "")
        self.assertEqual(json.loads(json_out), default_object)
        self.assertEqual(self._paths(), default_paths)
        self.assertEqual(default_paths, ["/v1/sites", *SITE_ROUTES])

    def test_german_text_report_contains_fixed_sections_and_validated_site_values_only(self) -> None:
        code, stdout, stderr, _ = self.invoke("--format", "text")
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        self.assertEqual(self._paths(), ["/v1/sites", *SITE_ROUTES])
        for label in (
            "Gesamtzustand", "Standortquellen", "WLAN-Gesundheit (Zeitreihe)",
            "WLAN-Gesundheit (Details)", "WLAN-Kanäle", "Client-Signalverteilung",
            "Band-Steering-Einstellung", "WLAN-Optimierungseinstellung",
            "Roaming-Einstellungen", "Band-Steering-Moduscode: 1",
            "RRM timeRangeEnable: nein", "Roaming fastRoamingEnable: ja",
            "Verfügbare Rohwerte",
        ):
            self.assertIn(label, stdout)
        for safe_value in ("71", "Kanalband 2g", "channel=6",
                           "Signalgruppe 1", "Signalgruppe 4",
                           "WLAN-Gesundheitswert (Rohwert): 71",
                           "clientsPercent (Rohwert): 20"):
            self.assertIn(safe_value, stdout)
        self.assertNotIn("%", stdout)
        for private in (CALLER_TOKEN, SITE_REF, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                        PRIVATE_CLIENT_MAC, ANSI_MARKER, "None", "null"):
            self.assertNotIn(private, stdout + stderr)
        self.assertNotIn("Ursache:", stdout)

    def test_partial_empty_null_and_error_sources_are_reported_without_raw_body(self) -> None:
        timeline = _complete_payloads(SITE_REF)[SITE_ROUTES[0]]
        assert isinstance(timeline, dict)
        timeline["data"] = None
        self.set_responses(overrides={
            SITE_ROUTES[0]: (200, timeline, {}),
            SITE_ROUTES[1]: (502, {"message": PRIVATE_NAME, "body": PRIVATE_MARKER}, {}),
            SITE_ROUTES[2]: (200, {"status": "ok", "resource": "site_dashboard_channels",
                                   "site_ref": SITE_REF, "partial": True,
                                   "data": {"bands": {}}}, {}),
        })
        code, stdout, stderr, _ = self.invoke("--format", "text")
        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn("Gesamtzustand", stdout)
        self.assertIn("teilweise", stdout)
        self.assertIn("WLAN-Gesundheit (Zeitreihe)", stdout)
        self.assertIn("WLAN-Gesundheit (Details)", stdout)
        self.assertIn("WLAN-Kanäle", stdout)
        self.assertIn("Client-Signalverteilung", stdout)
        self.assertEqual(self._paths(), ["/v1/sites", *SITE_ROUTES])
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER, SITE_REF,
                        PRIVATE_CLIENT_MAC, ANSI_MARKER):
            self.assertNotIn(private, stdout + stderr)

    def test_ap_text_shows_status_and_json_details_hint_without_identifiers(self) -> None:
        self.set_responses(include_ap=True)
        health_path = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health"
        health_response = _FakeConnector.responses[health_path]
        health_payload = health_response[1]
        assert isinstance(health_payload, dict)
        health_payload.update({"device_name": PRIVATE_NAME, "ip": PRIVATE_IP,
                               "mac": PRIVATE_CLIENT_MAC, "hostile": ANSI_MARKER})
        _FakeConnector.responses[health_path] = (health_response[0], health_payload, health_response[2])
        code, stdout, stderr, _ = self.invoke("--format", "text", "--ap-ref", AP_REF)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn("AP-Abfragen", stdout)
        self.assertIn("AP-LAN-Verkehrszähler", stdout)
        self.assertIn("Weitere Details: erneut mit --format json ausführen.", stdout)
        self.assertEqual(len(self._paths()), 21)
        for private in (CALLER_TOKEN, SITE_REF, AP_REF, PRIVATE_NAME, PRIVATE_IP,
                        PRIVATE_MARKER, PRIVATE_CLIENT_MAC, ANSI_MARKER):
            self.assertNotIn(private, stdout + stderr)

    def test_client_and_timeline_text_reports_source_status_and_json_hint_only(self) -> None:
        self.set_responses(include_client=True)
        timeline_payload = _FakeConnector.responses[CLIENT_TIMELINE_ROUTES[0]][1]
        assert isinstance(timeline_payload, dict)
        timeline_payload.update({"name": PRIVATE_NAME, "ip": PRIVATE_IP,
                                 "mac": PRIVATE_CLIENT_MAC, "hostile": ANSI_MARKER})
        _FakeConnector.responses[CLIENT_TIMELINE_ROUTES[0]] = (
            200, timeline_payload, {})
        tty = _FakeTTY("2\nja\n")
        code, stdout, stderr, prompt = self.invoke(
            "--format", "text", "--client-select", "--client-timeline", tty=tty)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn("Client-Abfragen", stdout)
        self.assertIn("Client-Zeitreihen", stdout)
        self.assertIn("Client-Gesundheits-Zeitreihe", stdout)
        self.assertIn("Client-Verlauf", stdout)
        self.assertIn("Weitere Details: erneut mit --format json ausführen.", stdout)
        self.assertEqual(len(self._paths()), 15)
        for private in (CALLER_TOKEN, SITE_REF, CLIENT_REF_1, CLIENT_REF_2,
                        PRIVATE_CLIENT_MAC, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                        ANSI_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_client_health_timeline_error_is_shown_as_partial_in_text_not_success(self) -> None:
        self.set_responses(include_client=True, overrides={
            CLIENT_HEALTH_TIMELINE_ROUTE: (
                502, {"error": PRIVATE_MARKER, "message": PRIVATE_NAME}, {}),
        })
        tty = _FakeTTY("2\nja\n")
        code, stdout, stderr, prompt = self.invoke(
            "--format", "text", "--client-select", "--client-timeline", tty=tty)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn("Gesamtzustand: teilweise", stdout)
        self.assertIn("Client-Gesundheits-Zeitreihe: Fehler", stdout)
        self.assertIn("Weitere Details: erneut mit --format json ausführen.", stdout)
        self.assertEqual(len(self._paths()), 15)
        for private in (CALLER_TOKEN, SITE_REF, CLIENT_REF_1, CLIENT_REF_2,
                        PRIVATE_CLIENT_MAC, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                        ANSI_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)


if __name__ == "__main__":
    unittest.main()
