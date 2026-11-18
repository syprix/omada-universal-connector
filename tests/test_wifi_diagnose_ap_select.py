from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from tools import wifi_diagnose
from tests.test_wifi_diagnose import (
    CALLER_TOKEN, PRIVATE_IP, PRIVATE_MARKER, PRIVATE_NAME, SITE_REF, _complete_payloads,
)
from tests.test_wifi_diagnose_ap import (
    AP_REF, DEVICE_ROUTE, HEALTH_ROUTE, LAN_TRAFFIC_ROUTE, RADIO_ROUTE, RF_SCAN_ROUTE,
    WIFI_NEIGHBORS_ROUTE, SPEED_TEST_ROUTE, WIRED_DOWNLINK_ROUTE, WIRED_UPLINK_ROUTE,
    PORTS_ROUTE, LLDP_CONFIG_ROUTE, PORT_VLANS_ROUTE,
    _ap_wifi_neighbors_payload, _ap_speed_test_payload, _ap_wired_downlink_payload,
    _ap_wired_uplink_payload,
    WLAN_OVERRIDES_ROUTE, _ap_wlan_overrides_payload,
            _ap_ports_payload, _ap_lldp_config_payload, _ap_port_vlans_payload,
    SITE_ROUTES, TIMELINE_ROUTE, _ap_health_payload, _ap_lan_traffic_payload,
    _ap_radio_config_payload, _ap_rf_scan_payload, _ap_timeline_payload,
)
from tests.test_wifi_diagnose_client import _FakeTTY


AP_REF_2 = "c" * 24
AP_REF_3 = "d" * 24
PRIVATE_AP_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_AP_IP = "192.0.2.244"
PRIVATE_AP_IPV6 = "2001:db8::244"
PRIVATE_AP_NAME = "private-ap-name-marker"
TTY_SAFE_NAME = "West Wing AP"
HOSTILE_AP_NAME = "\x1b[31mHostile\nAP 192.0.2.244 AA:BB:CC:DD:EE:FF\x1b[0m"
AP_PATHS = (HEALTH_ROUTE, TIMELINE_ROUTE, RADIO_ROUTE, RF_SCAN_ROUTE, LAN_TRAFFIC_ROUTE,
            WIFI_NEIGHBORS_ROUTE)


def _ap_rows(*, names: tuple[str, str, str] | None = None,
             models: tuple[str, str, str] = ("EAP-1", "EAP-2", "EAP-3"),
             refs: tuple[str, str, str] = (AP_REF, AP_REF_2, AP_REF_3),
             types: tuple[str, str, str] = ("AP", "access point", "accesspoint")) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for index, (ref, model, device_type) in enumerate(zip(refs, models, types)):
        row: dict[str, object] = {
            "device_ref": ref, "device_type": device_type, "model": model,
            "firmware": "1.2.3", "state": 1,
        }
        if names is not None:
            row["device_name"] = names[index]
        values.append(row)
    return values


class _ApSelectHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict[str, str]]] = []
    responses: dict[str, object] = {}

    def _respond(self, method: str) -> None:
        type(self).requests.append((method, self.path, dict(self.headers.items())))
        status = 200 if self.path in type(self).responses and method == "GET" else 405
        body = json.dumps(type(self).responses.get(self.path, {"error": PRIVATE_MARKER})).encode()
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

    def do_DELETE(self) -> None:  # noqa: N802
        self._respond("DELETE")

    def log_message(self, *_args: object) -> None:
        return


class WifiDiagnoseApSelectTests(unittest.TestCase):
    def setUp(self) -> None:
        _ApSelectHandler.requests = []
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(CALLER_TOKEN + "\n")
        os.chmod(self.token_file, 0o600)
        payloads = _complete_payloads(SITE_REF)
        _ApSelectHandler.responses = {
            "/v1/sites": {"status": "ok", "resource": "sites", "count": 1,
                           "items": [{"site_ref": SITE_REF}]},
            DEVICE_ROUTE: {"status": "ok", "resource": "devices", "count": 3,
                           "items": _ap_rows()},
        }
        for ap_ref in (AP_REF, AP_REF_2, AP_REF_3):
            health = _ap_health_payload(device_ref=ap_ref)
            timeline = _ap_timeline_payload(device_ref=ap_ref)
            radio = _ap_radio_config_payload()
            radio["device_ref"] = ap_ref
            rf_scan = _ap_rf_scan_payload()
            rf_scan["device_ref"] = ap_ref
            traffic = _ap_lan_traffic_payload(device_ref=ap_ref)
            _ApSelectHandler.responses.update({
                f"/v1/sites/{SITE_REF}/aps/{ap_ref}/health": health,
                f"/v1/sites/{SITE_REF}/aps/{ap_ref}/health/timeline": timeline,
                f"/v1/sites/{SITE_REF}/aps/{ap_ref}/radio-config": radio,
                f"/v1/sites/{SITE_REF}/aps/{ap_ref}/rf-scan": rf_scan,
                f"/v1/sites/{SITE_REF}/aps/{ap_ref}/lan-traffic": traffic,
                f"/v1/sites/{SITE_REF}/aps/{ap_ref}/wifi-neighbors":
                    _ap_wifi_neighbors_payload(device_ref=ap_ref),
                f"/v1/sites/{SITE_REF}/aps/{ap_ref}/speed-test-results":
                    _ap_speed_test_payload(device_ref=ap_ref),
                f"/v1/sites/{SITE_REF}/aps/{ap_ref}/wired-downlink":
                    _ap_wired_downlink_payload(device_ref=ap_ref),
                WIRED_UPLINK_ROUTE.replace(AP_REF, ap_ref):
                    _ap_wired_uplink_payload(device_ref=ap_ref),
                PORTS_ROUTE.replace(AP_REF, ap_ref):
                    _ap_ports_payload(device_ref=ap_ref),
                LLDP_CONFIG_ROUTE.replace(AP_REF, ap_ref):
                    _ap_lldp_config_payload(device_ref=ap_ref),
                PORT_VLANS_ROUTE.replace(AP_REF, ap_ref):
                    _ap_port_vlans_payload(device_ref=ap_ref),
                WLAN_OVERRIDES_ROUTE.replace(AP_REF, ap_ref):
                    _ap_wlan_overrides_payload(device_ref=ap_ref),
            })
        for route in SITE_ROUTES:
            _ApSelectHandler.responses[route] = payloads[route]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ApSelectHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temp.cleanup()

    def invoke(self, *extra: str, tty: _FakeTTY | None = None) -> tuple[int, str, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(wifi_diagnose, "_open_tty", return_value=tty), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main([
                "--site-ref", SITE_REF, "--ap-select", "--token-file", self.token_file,
                "--base-url", self.base_url, *extra,
            ])
        return code, stdout.getvalue(), stderr.getvalue(), tty.getvalue() if tty else ""

    def _assert_no_ap_query(self) -> None:
        self.assertFalse(any("/aps/" in path for _, path, _ in _ApSelectHandler.requests))

    def _assert_requests_are_get_only(self) -> None:
        for method, _path, headers in _ApSelectHandler.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")

    def test_fresh_site_bound_inventory_selection_uses_one_inventory_and_fourteen_gets(self) -> None:
        _ApSelectHandler.responses[DEVICE_ROUTE] = {
            "status": "ok", "resource": "devices", "count": 3,
            "items": _ap_rows(names=(PRIVATE_AP_NAME, PRIVATE_AP_NAME + "-2",
                                     PRIVATE_AP_NAME + "-3")),
        }
        tty = _FakeTTY("2\nja\n")
        code, stdout, stderr, prompt = self.invoke(tty=tty)
        self.assertEqual(code, 0, stdout + stderr)
        paths = [path for _, path, _ in _ApSelectHandler.requests]
        self.assertEqual(paths.count(DEVICE_ROUTE), 1)
        self.assertEqual(paths[:2], ["/v1/sites", DEVICE_ROUTE])
        self.assertEqual(paths[2:8], list(SITE_ROUTES))
        self.assertEqual(paths[8:], [
            f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/health",
            f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/health/timeline",
            f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/radio-config",
            f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/rf-scan",
            f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/lan-traffic",
            f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/wifi-neighbors",
            f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/speed-test-results",
            f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/wired-downlink",
            WIRED_UPLINK_ROUTE.replace(AP_REF, AP_REF_2),
            PORTS_ROUTE.replace(AP_REF, AP_REF_2),
            LLDP_CONFIG_ROUTE.replace(AP_REF, AP_REF_2),
            PORT_VLANS_ROUTE.replace(AP_REF, AP_REF_2),
            WLAN_OVERRIDES_ROUTE.replace(AP_REF, AP_REF_2),
        ])
        self.assertEqual(len(_ApSelectHandler.requests), 21)
        self._assert_requests_are_get_only()
        report = json.loads(stdout)
        self.assertEqual(report["ap"]["status"], "ok")
        self.assertNotIn("device_ref", report["ap"])
        for private in (CALLER_TOKEN, PRIVATE_AP_NAME, PRIVATE_AP_MAC, PRIVATE_AP_IP,
                        AP_REF, AP_REF_2, AP_REF_3, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr)
        self.assertNotIn(PRIVATE_AP_NAME, prompt)
        self.assertNotIn(PRIVATE_AP_NAME + "-2", prompt)
        self.assertNotIn(PRIVATE_AP_NAME + "-3", prompt)

    def test_no_tty_eof_bad_index_or_missing_confirmation_sends_no_ap_queries(self) -> None:
        scenarios = ((None, "ap_selection_unavailable"),
                     (_FakeTTY(""), None),
                     (_FakeTTY("9\nja\n"), "ap_selection_invalid"),
                     (_FakeTTY("1\nno\n"), "ap_selection_cancelled"))
        for tty, expected_error in scenarios:
            with self.subTest(error=expected_error):
                _ApSelectHandler.requests = []
                code, stdout, stderr, prompt = self.invoke(tty=tty)
                self.assertNotEqual(code, 0)
                if expected_error is not None:
                    self.assertEqual(json.loads(stdout)["error"], expected_error)
                self._assert_no_ap_query()
                self.assertEqual([p for _, p, _ in _ApSelectHandler.requests].count(DEVICE_ROUTE), 1)
                self._assert_requests_are_get_only()
                for private in (CALLER_TOKEN, PRIVATE_AP_MAC, PRIVATE_AP_IP,
                                PRIVATE_AP_NAME, PRIVATE_MARKER):
                    self.assertNotIn(private, stdout + stderr + prompt)

    def test_equal_models_without_name_opt_in_fail_closed_as_ambiguous(self) -> None:
        _ApSelectHandler.responses[DEVICE_ROUTE] = {
            "status": "ok", "resource": "devices", "count": 3,
            "items": _ap_rows(models=("EAP-Identical",) * 3),
        }
        code, stdout, stderr, prompt = self.invoke(tty=_FakeTTY("1\nja\n"))
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(stdout)["error"], "ap_selection_ambiguous")
        self._assert_no_ap_query()
        for private in (CALLER_TOKEN, PRIVATE_AP_MAC, PRIVATE_AP_IP, PRIVATE_AP_NAME,
                        AP_REF, AP_REF_2, AP_REF_3, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_show_ap_names_is_tty_only_escaped_and_never_in_report_or_logs(self) -> None:
        _ApSelectHandler.responses[DEVICE_ROUTE] = {
            "status": "ok", "resource": "devices", "count": 3,
            "items": _ap_rows(names=(TTY_SAFE_NAME, "East Wing AP", "Other AP")),
        }
        code, stdout, stderr, prompt = self.invoke("--show-ap-names", tty=_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn(TTY_SAFE_NAME, prompt)
        self.assertNotIn("\x1b", prompt)
        self.assertNotIn(PRIVATE_AP_IP, prompt)
        self.assertNotIn(PRIVATE_AP_MAC, prompt)
        for private in (TTY_SAFE_NAME, "East Wing AP", "Other AP", PRIVATE_AP_IP,
                        PRIVATE_AP_MAC, PRIVATE_AP_NAME, CALLER_TOKEN):
            self.assertNotIn(private, stdout + stderr)
        self.assertEqual(len(_ApSelectHandler.requests), 21)
        self._assert_requests_are_get_only()

    def test_hostile_ap_names_are_rejected_without_terminal_control_or_identity_leaks(self) -> None:
        _ApSelectHandler.responses[DEVICE_ROUTE] = {
            "status": "ok", "resource": "devices", "count": 3,
            "items": _ap_rows(names=(TTY_SAFE_NAME, HOSTILE_AP_NAME, "Other AP")),
        }
        code, stdout, stderr, prompt = self.invoke("--show-ap-names", tty=_FakeTTY("2\nja\n"))
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(stdout)["error"], "ap_names_unavailable")
        self._assert_no_ap_query()
        self.assertNotIn("\x1b", stdout + stderr + prompt)
        self.assertNotIn(PRIVATE_AP_IP, stdout + stderr + prompt)
        self.assertNotIn(PRIVATE_AP_MAC, stdout + stderr + prompt)
        self.assertNotIn(HOSTILE_AP_NAME, stdout + stderr + prompt)

    def test_embedded_ipv4_ipv6_mac_and_reference_names_fail_closed(self) -> None:
        hostile_names = (
            f"AP 192.0.2.244 {PRIVATE_AP_IPV6} {PRIVATE_AP_MAC}",
            f"AP {PRIVATE_AP_IPV6}",
            f"AP {PRIVATE_AP_MAC}",
            f"AP {PRIVATE_AP_IP}",
            f"AP {AP_REF_2}",
        )
        for hostile in hostile_names:
            with self.subTest(hostile=hostile):
                _ApSelectHandler.requests = []
                _ApSelectHandler.responses[DEVICE_ROUTE] = {
                    "status": "ok", "resource": "devices", "count": 3,
                    "items": _ap_rows(names=("West AP", hostile, "East AP")),
                }
                code, stdout, stderr, prompt = self.invoke(
                    "--show-ap-names", tty=_FakeTTY("2\nja\n"))
                self.assertNotEqual(code, 0)
                self.assertEqual(json.loads(stdout)["error"], "ap_names_unavailable")
                self._assert_no_ap_query()
                self.assertEqual([p for _, p, _ in _ApSelectHandler.requests].count(DEVICE_ROUTE), 1)
                self._assert_requests_are_get_only()
                for private in (PRIVATE_AP_IP, PRIVATE_AP_IPV6, PRIVATE_AP_MAC,
                                AP_REF_2, CALLER_TOKEN, PRIVATE_MARKER):
                    self.assertNotIn(private, stdout + stderr + prompt)

    def test_duplicate_name_and_invalid_inventory_shapes_fail_before_ap_queries(self) -> None:
        cases = (
            ({"status": "ok", "resource": "devices", "count": 2,
              "items": _ap_rows()[:1]}, "ap_inventory_invalid"),
            ({"status": "ok", "resource": "devices", "count": 3,
              "items": [*_ap_rows()[:2], _ap_rows()[1]]}, "ap_inventory_invalid"),
            ({"status": "ok", "resource": "devices", "count": 3,
              "items": _ap_rows(refs=(AP_REF, AP_REF_2, "not-a-ref"))}, "ap_inventory_invalid"),
            ({"status": "ok", "resource": "devices", "count": 3,
              "items": _ap_rows(types=("AP", "unrecognized", "AP"))}, None),
        )
        for payload, expected_error in cases:
            with self.subTest(error=expected_error, payload=payload):
                _ApSelectHandler.requests = []
                _ApSelectHandler.responses[DEVICE_ROUTE] = payload
                code, stdout, stderr, prompt = self.invoke(tty=_FakeTTY("1\nja\n"))
                self.assertNotEqual(code, 0)
                if expected_error is not None:
                    self.assertEqual(json.loads(stdout)["error"], expected_error)
                else:
                    self.assertNotEqual(json.loads(stdout).get("error"), None)
                self._assert_no_ap_query()
                self.assertEqual([p for _, p, _ in _ApSelectHandler.requests].count(DEVICE_ROUTE), 1)
                for private in (CALLER_TOKEN, PRIVATE_AP_MAC, PRIVATE_AP_IP,
                                PRIVATE_AP_NAME, PRIVATE_MARKER):
                    self.assertNotIn(private, stdout + stderr + prompt)

        _ApSelectHandler.requests = []
        _ApSelectHandler.responses[DEVICE_ROUTE] = {
            "status": "ok", "resource": "devices", "count": 3,
            "items": _ap_rows(models=("EAP-Identical", "EAP-Identical", "EAP-3"),
                               names=("duplicate", "duplicate", "unique")),
        }
        code, stdout, stderr, prompt = self.invoke("--show-ap-names", tty=_FakeTTY("1\nja\n"))
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(stdout)["error"], "ap_selection_ambiguous")
        self._assert_no_ap_query()
        self.assertNotIn("duplicate", stdout + stderr)

    def test_known_non_ap_devices_are_ignored_when_building_ap_candidates(self) -> None:
        _ApSelectHandler.responses[DEVICE_ROUTE] = {
            "status": "ok", "resource": "devices", "count": 3,
            "items": _ap_rows(types=("AP", "switch", "AP")),
        }
        code, stdout, stderr, prompt = self.invoke(tty=_FakeTTY("2\nja\n"))
        self.assertEqual(code, 0, stdout + stderr)
        paths = [path for _, path, _ in _ApSelectHandler.requests]
        self.assertEqual(paths.count(DEVICE_ROUTE), 1)
        self.assertIn(f"/v1/sites/{SITE_REF}/aps/{AP_REF_3}/health", paths)
        self.assertNotIn(f"/v1/sites/{SITE_REF}/aps/{AP_REF_2}/health", paths)
        self.assertEqual(len(paths), 21)
        self._assert_requests_are_get_only()

    def test_ap_and_client_selection_flags_are_mutually_exclusive(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        _ApSelectHandler.requests = []
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main([
                "--site-ref", SITE_REF, "--ap-select", "--client-select",
                "--token-file", self.token_file, "--base-url", self.base_url,
            ])
        self.assertNotEqual(code, 0)
        self.assertEqual(_ApSelectHandler.requests, [])
        self.assertNotIn(CALLER_TOKEN, stdout.getvalue() + stderr.getvalue())

    def test_show_names_requires_selection_and_selection_conflicts_with_explicit_ref(self) -> None:
        for arguments in (
            ["--site-ref", SITE_REF, "--show-ap-names", "--token-file", self.token_file,
             "--base-url", self.base_url],
            ["--site-ref", SITE_REF, "--ap-select", "--ap-ref", AP_REF,
             "--token-file", self.token_file, "--base-url", self.base_url],
        ):
            with self.subTest(arguments=arguments):
                _ApSelectHandler.requests = []
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = wifi_diagnose.main(arguments)
                self.assertNotEqual(code, 0)
                self.assertEqual(_ApSelectHandler.requests, [])
                self.assertNotIn(CALLER_TOKEN, stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
