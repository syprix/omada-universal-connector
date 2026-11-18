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
    CALLER_TOKEN,
    PRIVATE_IP,
    PRIVATE_MARKER,
    PRIVATE_NAME,
    SITE_REF,
    _complete_payloads,
)
from tests.test_wifi_diagnose_ap import (
    AP_REF,
    _ap_health_payload,
    _ap_radio_config_payload,
    _ap_rf_scan_payload,
    _ap_timeline_payload,
    _device,
    PORT_VLANS_ROUTE,
    _ap_port_vlans_payload,
    WLAN_OVERRIDES_ROUTE,
    _ap_wlan_overrides_payload,
)
from tests.test_wifi_diagnose_ap_lan_traffic import LAN_TRAFFIC_ROUTE, _lan_traffic_payload
from tests.test_wifi_diagnose_ap import (WIFI_NEIGHBORS_ROUTE, SPEED_TEST_ROUTE,
                                         WIRED_DOWNLINK_ROUTE, WIRED_UPLINK_ROUTE,
                                         PORTS_ROUTE, _ap_ports_payload,
                                         LLDP_CONFIG_ROUTE, _ap_lldp_config_payload,
                                         _ap_wifi_neighbors_payload,
                                         _ap_speed_test_payload,
                                         _ap_wired_downlink_payload,
                                         _ap_wired_uplink_payload)
from tests.test_wifi_diagnose_client import (
    CLIENT_REF_1,
    CLIENT_REF_2,
    _FakeTTY,
    _client,
    _connection_payload,
)


OTHER_SITE_REF = "b" * 24
CLIENTS_ROUTE = f"/v1/sites/{SITE_REF}/clients"
DEVICES_ROUTE = f"/v1/sites/{SITE_REF}/devices"
SITE_ROUTES = (
    f"/v1/sites/{SITE_REF}/wifi/health/timeline",
    f"/v1/sites/{SITE_REF}/wifi/health/details",
    f"/v1/sites/{SITE_REF}/wifi/channels",
    f"/v1/sites/{SITE_REF}/wifi/client-signal-distribution",
    f"/v1/sites/{SITE_REF}/wifi/6ghz-ap-presence",
    f"/v1/sites/{SITE_REF}/wifi/rogue-ap-results",
    f"/v1/sites/{SITE_REF}/wifi/wids-summary",
    f"/v1/sites/{SITE_REF}/wifi/wids-blacklist-summary",
)
SITE_POLICY_ROUTES = (
    f"/v1/sites/{SITE_REF}/wifi/band-steering",
    f"/v1/sites/{SITE_REF}/wifi/optimization",
    f"/v1/sites/{SITE_REF}/wifi/roaming",
)
SITE_TOPOLOGY_ROUTE = f"/v1/sites/{SITE_REF}/topology/network-summary"
CONNECTIONS_ROUTE = f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF_2}/connections"


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


class WifiDiagnoseSiteAutoTests(unittest.TestCase):
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

    def set_responses(self, site_items: list[dict[str, object]] | None = None,
                      site_count: int | None = None,
                      include_ap: bool = False,
                      include_client: bool = False) -> None:
        _FakeConnector.requests = []
        payloads = _complete_payloads(SITE_REF)
        items = site_items if site_items is not None else [
            {"site_ref": SITE_REF, "site_name": PRIVATE_NAME,
             "description": PRIVATE_MARKER, "ip": PRIVATE_IP},
        ]
        _FakeConnector.responses = {
            "/v1/sites": (200, {
                "status": "ok", "resource": "sites",
                "count": len(items) if site_count is None else site_count,
                "items": items,
            }, {}),
        }
        for route in (*SITE_ROUTES, *SITE_POLICY_ROUTES):
            _FakeConnector.responses[route] = (200, payloads[route], {})
        _FakeConnector.responses[SITE_TOPOLOGY_ROUTE] = (
            200, payloads[SITE_TOPOLOGY_ROUTE], {})
        if include_client:
            _FakeConnector.responses[CLIENTS_ROUTE] = (200, {
                "status": "ok", "resource": "clients", "count": 2,
                "items": [
                    _client(CLIENT_REF_1, channel=1, rssi=-50, snr=30),
                    _client(CLIENT_REF_2, channel=36, rssi=-75, snr=12, active=False),
                ],
            }, {})
            _FakeConnector.responses[CONNECTIONS_ROUTE] = (200, _connection_payload(), {})
        if include_ap:
            _FakeConnector.responses[DEVICES_ROUTE] = (200, {
                "status": "ok", "resource": "devices", "count": 1,
                "items": [_device(AP_REF, "AP")],
            }, {})
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health"] = (
                200, _ap_health_payload(), {})
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health/timeline"] = (
                200, _ap_timeline_payload(), {})
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/radio-config"] = (
                200, _ap_radio_config_payload(), {})
            _FakeConnector.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/rf-scan"] = (
                200, _ap_rf_scan_payload(), {})
            _FakeConnector.responses[LAN_TRAFFIC_ROUTE] = (200, _lan_traffic_payload(), {})
            _FakeConnector.responses[WIFI_NEIGHBORS_ROUTE] = (200, _ap_wifi_neighbors_payload(), {})
            _FakeConnector.responses[SPEED_TEST_ROUTE] = (200, _ap_speed_test_payload(), {})
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

    def invoke(self, *extra: str, tty: _FakeTTY | None = None) -> tuple[int, str, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(wifi_diagnose, "_open_tty", lambda: tty), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main([
                "--site-auto", "--token-file", self.token_file,
                "--base-url", self.base_url, *extra,
            ])
        return code, stdout.getvalue(), stderr.getvalue(), tty.getvalue() if tty else ""

    def test_exactly_one_site_runs_all_fixed_reads_after_one_inventory_request(self) -> None:
        code, stdout, stderr, _ = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                         [("GET", "/v1/sites"), *(('GET', route) for route in SITE_ROUTES),
                          *(('GET', route) for route in SITE_POLICY_ROUTES),
                          ("GET", SITE_TOPOLOGY_ROUTE)])
        self.assertEqual(sum(path == "/v1/sites" for _, path, _ in _FakeConnector.requests), 1)
        report = json.loads(stdout)
        self.assertNotIn("site_ref", report)
        self.assertEqual(report["status"], "ok")
        for route in report["results"].values():
            self.assertEqual(route["status"], "ok")
            self.assertEqual(route["capability_status"], "unknown")
        for method, _path, headers in _FakeConnector.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr)

    def test_zero_multiple_duplicate_malformed_or_inconsistent_site_inventory_stops_early(self) -> None:
        cases = (
            ([], 0),
            ([{"site_ref": SITE_REF}, {"site_ref": OTHER_SITE_REF}], 2),
            ([{"site_ref": SITE_REF}, {"site_ref": SITE_REF}], 2),
            ([{"site_ref": "not-a-ref"}], 1),
            ([{"site_name": PRIVATE_NAME}], 1),
            ([{"site_ref": SITE_REF}], 2),
        )
        for items, count in cases:
            with self.subTest(items=items, count=count):
                self.set_responses(site_items=items, site_count=count)
                code, stdout, stderr, _ = self.invoke()
                self.assertNotEqual(code, 0)
                self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                                 [("GET", "/v1/sites")])
                for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                                SITE_REF, OTHER_SITE_REF):
                    self.assertNotIn(private, stdout + stderr)

    def test_4000_site_inventory_bound_is_fail_closed_at_and_above_limit(self) -> None:
        for count, expected_error in ((4000, "site_auto_multiple_sites"),
                                      (4001, "site_inventory_invalid")):
            with self.subTest(count=count):
                items = [{"site_ref": f"{index:024x}"} for index in range(1, count + 1)]
                self.set_responses(site_items=items, site_count=count)
                code, stdout, stderr, _ = self.invoke()
                self.assertNotEqual(code, 0)
                self.assertEqual([(method, path) for method, path, _ in _FakeConnector.requests],
                                 [("GET", "/v1/sites")])
                self.assertEqual(json.loads(stdout)["error"], expected_error)
                self.assertNotIn(CALLER_TOKEN, stdout + stderr)
                self.assertNotIn(PRIVATE_NAME, stdout + stderr)

    def test_site_auto_uses_one_inventory_snapshot_before_client_selection(self) -> None:
        self.set_responses(include_client=True)
        tty = _FakeTTY("2\nja\n")
        code, stdout, stderr, prompt = self.invoke("--client-select", tty=tty)
        self.assertEqual(code, 0, stdout + stderr)
        request_paths = [path for _method, path, _ in _FakeConnector.requests]
        self.assertEqual(request_paths, ["/v1/sites", CLIENTS_ROUTE,
                                         *(route for route in SITE_ROUTES
                                           if "/wids-" not in route),
                                         CONNECTIONS_ROUTE])
        self.assertEqual(request_paths.count("/v1/sites"), 1)
        self.assertEqual(request_paths[0], "/v1/sites")
        self.assertEqual(request_paths[1], CLIENTS_ROUTE)
        self.assertNotIn("site_ref", json.loads(stdout))
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER,
                        CLIENT_REF_1, CLIENT_REF_2):
            self.assertNotIn(private, stdout + stderr + prompt)

    def test_site_auto_is_compatible_with_ap_selector_and_uses_selected_site_ref(self) -> None:
        self.set_responses(include_ap=True)
        code, stdout, stderr, _ = self.invoke("--ap-ref", AP_REF)
        self.assertEqual(code, 0, stdout + stderr)
        paths = [path for _method, path, _ in _FakeConnector.requests]
        self.assertEqual(paths, ["/v1/sites", DEVICES_ROUTE,
                                 *(route for route in SITE_ROUTES
                                   if "/wids-" not in route),
                                 f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health",
                                 f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health/timeline",
                                 f"/v1/sites/{SITE_REF}/aps/{AP_REF}/radio-config",
                                 f"/v1/sites/{SITE_REF}/aps/{AP_REF}/rf-scan",
                                 LAN_TRAFFIC_ROUTE, WIFI_NEIGHBORS_ROUTE, SPEED_TEST_ROUTE,
                                 WIRED_DOWNLINK_ROUTE, WIRED_UPLINK_ROUTE, PORTS_ROUTE,
                                 LLDP_CONFIG_ROUTE, PORT_VLANS_ROUTE,
                                 WLAN_OVERRIDES_ROUTE])
        self.assertEqual(len(_FakeConnector.requests), 21)
        for method, _path, headers in _FakeConnector.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")
        self.assertEqual(paths.count("/v1/sites"), 1)
        report = json.loads(stdout)
        self.assertNotIn("site_ref", report)
        self.assertEqual(report["ap"]["status"], "ok")
        self.assertEqual(report["ap"]["lan_traffic"]["status"], "ok")
        self.assertFalse(report["ap"]["lan_traffic"]["partial"])
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, stdout + stderr)

    def test_site_ref_and_site_auto_are_mutually_exclusive(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wifi_diagnose.main([
                "--site-ref", SITE_REF, "--site-auto", "--token-file", self.token_file,
                "--base-url", self.base_url,
            ])
        self.assertNotEqual(code, 0)
        self.assertEqual(_FakeConnector.requests, [])
        self.assertNotIn(CALLER_TOKEN, stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
