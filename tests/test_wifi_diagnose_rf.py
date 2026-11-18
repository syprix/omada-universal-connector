from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from tests.test_wifi_diagnose import (
    CALLER_TOKEN, PRIVATE_IP, PRIVATE_MARKER, PRIVATE_NAME, SITE_REF,
    _complete_payloads,
)
from tests.test_wifi_diagnose_ap import (
    AP_REF, DEVICE_ROUTE, HEALTH_ROUTE, LAN_TRAFFIC_ROUTE, WIFI_NEIGHBORS_ROUTE,
    SPEED_TEST_ROUTE, WIRED_DOWNLINK_ROUTE, WIRED_UPLINK_ROUTE, PORTS_ROUTE,
    LLDP_CONFIG_ROUTE, PORT_VLANS_ROUTE, _ap_lldp_config_payload,
    _ap_port_vlans_payload, _ap_ports_payload, _ap_speed_test_payload,
    _ap_wired_downlink_payload, _ap_wired_uplink_payload,
    OTHER_AP_REF, OTHER_SITE_REF,
    SITE_ROUTES, SITE_REF as AP_SITE_REF, TIMELINE_ROUTE, TOKEN_PATH,
    _ap_health_payload, _ap_lan_traffic_payload, _ap_timeline_payload,
    _ap_wifi_neighbors_payload, _device, WLAN_OVERRIDES_ROUTE,
    _ap_wlan_overrides_payload,
)


assert SITE_REF == AP_SITE_REF
RADIO_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/radio-config"
RF_SCAN_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/rf-scan"
PRIVATE_MAC = "aa:bb:cc:dd:ee:ff"


def _radio_config_payload(*, site_ref: str | None = None,
                          device_ref: str = AP_REF) -> dict[str, object]:
    raw = {
        "radioSetting2g": {"channel": 6, "channelWidth": 20, "freq": 2437,
                           "txPower": 17, "txPowerLevel": 2, "radioEnable": True},
        "radioSetting5g": {"channel": 36, "channelWidth": 80, "freq": 5180,
                           "txPower": 20, "txPowerLevel": 1, "radioEnable": True},
        "radioSetting5g1": {"channel": 36, "channelWidth": 80, "freq": 5180,
                            "txPower": 20, "txPowerLevel": 1, "radioEnable": True},
        "radioSetting5g2": {"channel": 100, "channelWidth": 80, "freq": 5500,
                            "txPower": 18, "txPowerLevel": 1, "radioEnable": False},
        "radioSetting6g": {"channel": 5, "channelWidth": 160, "freq": 5975,
                           "txPower": 16, "txPowerLevel": 1, "radioEnable": True},
        "ssid": PRIVATE_NAME, "mac": PRIVATE_MAC, "ip": PRIVATE_IP,
        "private_marker": PRIVATE_MARKER,
    }
    payload = {"status": "ok", "resource": "radio_config", "device_ref": device_ref,
               "data": OmadaOpenApiClient._sanitize_ap_entity("radio_config", raw)}
    if site_ref is not None:
        payload["site_ref"] = site_ref
    return payload


def _rf_scan_payload(*, site_ref: str | None = None,
                     device_ref: str = AP_REF) -> dict[str, object]:
    # Exercise the existing fixed-route adapter with a synthetic controller
    # result; no HTTP connection or real controller is involved.
    raw = {
        "channel2g": [{"chan": 6, "chanWidth": 2, "util": 41, "inter": []}],
        "channel5g": [{"chan": 36, "chanWidth": 5, "util": 15, "inter": []}],
        "channel5g2": [], "channel6g": [],
        "status2g": 1, "status5g": 1, "status5g2": 1, "status6g": 1,
    }
    client = OmadaOpenApiClient(OpenApiConfig(
        "https://controller.example", "ctrl", "unused-id", "unused-secret",
        cert_sha256="a" * 64))
    client._site_ids_by_ref[SITE_REF] = "synthetic-site-id"
    client._device_macs_by_site_ref[SITE_REF] = {device_ref: PRIVATE_MAC}
    client._access_token = lambda: "synthetic-upstream-token"
    client._request_json = lambda method, path, token=None: {"errorCode": 0, "result": raw}
    payload = client.read_ap_rf_scan(SITE_REF, device_ref)
    if site_ref is not None:
        payload["site_ref"] = site_ref
    return payload


class _FakeConnector(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict[str, str]]] = []
    responses: dict[str, tuple[int, object, dict[str, str]]] = {}

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(("GET", self.path, dict(self.headers.items())))
        status, payload, headers = type(self).responses.get(
            self.path, (404, {"error": "not_found"}, {}))
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


class WifiDiagnoseRfTests(unittest.TestCase):
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

    def set_responses(self) -> None:
        _FakeConnector.requests = []
        site_payloads = _complete_payloads(SITE_REF)
        _FakeConnector.responses = {
            TOKEN_PATH: (200, {"status": "ok", "items": [{"site_ref": SITE_REF}]}, {}),
            DEVICE_ROUTE: (200, {"status": "ok", "resource": "devices", "count": 1,
                                 "items": [_device()]}, {}),
            RADIO_ROUTE: (200, _radio_config_payload(), {}),
            RF_SCAN_ROUTE: (200, _rf_scan_payload(), {}),
            HEALTH_ROUTE: (200, _ap_health_payload(), {}),
            TIMELINE_ROUTE: (200, _ap_timeline_payload(), {}),
            LAN_TRAFFIC_ROUTE: (200, _ap_lan_traffic_payload(), {}),
            WIFI_NEIGHBORS_ROUTE: (200, _ap_wifi_neighbors_payload(), {}),
            SPEED_TEST_ROUTE: (200, _ap_speed_test_payload(), {}),
            WIRED_DOWNLINK_ROUTE: (200, _ap_wired_downlink_payload(), {}),
            WIRED_UPLINK_ROUTE: (200, _ap_wired_uplink_payload(), {}),
            PORTS_ROUTE: (200, _ap_ports_payload(), {}),
            LLDP_CONFIG_ROUTE: (200, _ap_lldp_config_payload(), {}),
            PORT_VLANS_ROUTE: (200, _ap_port_vlans_payload(), {}),
            WLAN_OVERRIDES_ROUTE: (200, _ap_wlan_overrides_payload(), {}),
        }
        for path in SITE_ROUTES:
            _FakeConnector.responses[path] = (200, site_payloads[path], {})

    def run_cli(self, *extra: str) -> subprocess.CompletedProcess[str]:
        script = os.path.join(os.path.dirname(__file__), "..", "tools", "wifi_diagnose.py")
        return subprocess.run(
            [sys.executable, script, "--site-ref", SITE_REF, "--ap-ref", AP_REF,
             "--token-file", self.token_file, "--base-url", self.base_url, *extra],
            capture_output=True, text=True, timeout=12, check=False,
        )

    def test_selected_ap_gets_bound_radio_rf_and_lan_facts_with_max_fourteen_gets(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIn(report["status"], {"ok", "partial"})
        self.assertEqual(report["ap"]["capability_status"], "unknown")
        self.assertEqual(report["ap"]["radio_config"]["capability_status"], "unknown")
        self.assertEqual(report["ap"]["rf_scan"]["capability_status"], "unknown")
        self.assertEqual(report["ap"]["lan_traffic"]["capability_status"], "unknown")
        self.assertFalse(report["ap"]["radio_config"]["partial"])
        self.assertFalse(report["ap"]["rf_scan"]["partial"])
        self.assertFalse(report["ap"]["lan_traffic"]["partial"])
        self.assertEqual(report["ap"]["lan_traffic"]["data"]["rxPkts"], 101)
        self.assertEqual(report["ap"]["radio_config"]["data"]["bands"]["2g"], {
            "channel": 6, "channelWidth": 20, "freq": 2437, "txPower": 17,
            "txPowerLevel": 2, "radioEnable": True,
        })
        self.assertEqual(report["ap"]["rf_scan"]["data"]["bands"]["2g"][0]["channel"], 6)
        paths = [path for method, path, _ in _FakeConnector.requests if method == "GET"]
        self.assertEqual(paths, [TOKEN_PATH, DEVICE_ROUTE, *SITE_ROUTES,
                                 HEALTH_ROUTE, TIMELINE_ROUTE, RADIO_ROUTE, RF_SCAN_ROUTE,
                                 LAN_TRAFFIC_ROUTE, WIFI_NEIGHBORS_ROUTE, SPEED_TEST_ROUTE,
                                 WIRED_DOWNLINK_ROUTE, WIRED_UPLINK_ROUTE, PORTS_ROUTE,
                                 LLDP_CONFIG_ROUTE, PORT_VLANS_ROUTE,
                                 WLAN_OVERRIDES_ROUTE])
        self.assertLessEqual(len(_FakeConnector.requests), 21)
        self.assertTrue(all(method == "GET" for method, _, _ in _FakeConnector.requests))
        for _, _, headers in _FakeConnector.requests:
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")
        rendered = result.stdout + result.stderr
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_MAC, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, rendered)

    def test_site_device_binding_and_malformed_or_missing_values_fail_partial(self) -> None:
        for route, payload in (
            (RADIO_ROUTE, _radio_config_payload(device_ref=OTHER_AP_REF)),
            (RADIO_ROUTE, _radio_config_payload(site_ref=OTHER_SITE_REF)),
            (RF_SCAN_ROUTE, _rf_scan_payload(site_ref=OTHER_SITE_REF)),
            (RF_SCAN_ROUTE, _rf_scan_payload(device_ref=OTHER_AP_REF)),
        ):
            with self.subTest(route=route, payload=payload):
                self.set_responses()
                _FakeConnector.responses[route] = (200, payload, {})
                result = self.run_cli()
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                key = "radio_config" if route == RADIO_ROUTE else "rf_scan"
                self.assertEqual(report["ap"][key]["status"], "error")
                self.assertEqual(report["ap"]["capability_status"], "unknown")
                self.assertNotIn(OTHER_AP_REF, result.stdout + result.stderr)
                self.assertNotIn(OTHER_SITE_REF, result.stdout + result.stderr)

        self.set_responses()
        radio = _radio_config_payload()
        radio["data"].pop("radioSetting2g")
        _FakeConnector.responses[RADIO_ROUTE] = (200, radio, {})
        rf = _rf_scan_payload()
        rf["partial"] = True
        rf["missing_bands"] = ["6g"]
        rf["data"].pop("6g")
        _FakeConnector.responses[RF_SCAN_ROUTE] = (200, rf, {})
        result = self.run_cli()
        report = json.loads(result.stdout)
        self.assertEqual(report["ap"]["status"], "partial")
        self.assertTrue(report["ap"]["radio_config"]["partial"])
        self.assertTrue(report["ap"]["rf_scan"]["partial"])
        self.assertNotIn("2g", report["ap"]["radio_config"]["data"]["bands"])

    def test_unknown_and_hostile_fields_are_omitted_and_marked_partial(self) -> None:
        self.set_responses()
        radio = _radio_config_payload()
        radio["data"]["radioSetting2g"]["ssid"] = PRIVATE_NAME
        radio["data"]["radioSetting2g"]["mac"] = PRIVATE_MAC
        radio["data"]["radioSetting2g"]["ip"] = PRIVATE_IP
        radio["data"]["radioSetting2g"]["comment"] = PRIVATE_MARKER
        _FakeConnector.responses[RADIO_ROUTE] = (200, radio, {})
        rf = _rf_scan_payload()
        rf["data"]["2g"][0].update({"ssid": PRIVATE_NAME, "bssid": PRIVATE_MAC,
                                     "ip": PRIVATE_IP, "description": PRIVATE_MARKER})
        _FakeConnector.responses[RF_SCAN_ROUTE] = (200, rf, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ap"]["radio_config"]["partial"])
        self.assertTrue(report["ap"]["rf_scan"]["partial"])
        rendered = result.stdout + result.stderr
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_MAC, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, rendered)

    def test_invalid_numeric_radio_and_rf_values_are_dropped_and_mark_partial(self) -> None:
        self.set_responses()
        radio = _radio_config_payload()
        radio["data"]["radioSetting2g"]["channel"] = "channel-6"
        _FakeConnector.responses[RADIO_ROUTE] = (200, radio, {})
        rf = _rf_scan_payload()
        rf["data"]["2g"][0]["utilization_percent"] = 101
        _FakeConnector.responses[RF_SCAN_ROUTE] = (200, rf, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ap"]["radio_config"]["partial"])
        self.assertNotIn("channel", report["ap"]["radio_config"]["data"]["bands"]["2g"])
        self.assertTrue(report["ap"]["rf_scan"]["partial"])
        self.assertEqual(report["ap"]["rf_scan"]["data"]["bands"]["2g"], [])

    def test_route_error_and_response_limit_are_sanitized(self) -> None:
        self.set_responses()
        _FakeConnector.responses[RADIO_ROUTE] = (502, {"error": PRIVATE_MARKER}, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["ap"]["radio_config"]["status"], "error")
        self.assertEqual(report["ap"]["radio_config"]["capability_status"], "unknown")
        self.assertEqual(report["ap"]["status"], "partial")
        self.assertNotIn(PRIVATE_MARKER, result.stdout + result.stderr)

        self.set_responses()
        _FakeConnector.responses[RF_SCAN_ROUTE] = (
            200, {"status": "ok", "resource": "ap_rf_scan", "site_ref": SITE_REF,
                  "device_ref": AP_REF, "data": {}, "private": PRIVATE_MARKER + "x" * (300 * 1024)}, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["ap"]["rf_scan"]["status"], "error")
        self.assertNotIn(PRIVATE_MARKER, result.stdout + result.stderr)
        self.assertLessEqual(len(_FakeConnector.requests), 21)

    def test_rf_scan_type_is_not_reported_as_a_confirmed_cause(self) -> None:
        self.set_responses()
        rf = _rf_scan_payload()
        rf["data"]["2g"][0]["interference"] = [{
            "level_dbm": -78, "type": "wlan",
            "histogram": [{"signal_dbm": -65, "count": 3}],
        }]
        _FakeConnector.responses[RF_SCAN_ROUTE] = (200, rf, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        rf_result = report["ap"]["rf_scan"]
        self.assertTrue(rf_result["partial"])
        self.assertEqual(rf_result["data"]["bands"]["2g"][0]["interference"][0], {
            "level_dbm": -78, "histogram": [{"signal_dbm": -65, "count": 3}],
        })
        self.assertNotIn('"type"', result.stdout)
        self.assertNotIn('"type":', json.dumps(rf_result))


if __name__ == "__main__":
    unittest.main()
