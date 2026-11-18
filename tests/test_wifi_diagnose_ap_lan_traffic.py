from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app.ap_lan_traffic import project_ap_lan_traffic
from tests.test_wifi_diagnose import CALLER_TOKEN, PRIVATE_IP, PRIVATE_MARKER, PRIVATE_NAME, SITE_REF, _complete_payloads
from tests.test_wifi_diagnose_ap import (
    AP_REF, DEVICE_ROUTE, HEALTH_ROUTE, LAN_TRAFFIC_ROUTE, RADIO_ROUTE, WIFI_NEIGHBORS_ROUTE,
    RF_SCAN_ROUTE, SITE_ROUTES, TIMELINE_ROUTE, TOKEN_PATH, WIRED_UPLINK_ROUTE,
    PORTS_ROUTE, _ap_ports_payload, LLDP_CONFIG_ROUTE, _ap_lldp_config_payload,
    PORT_VLANS_ROUTE, _ap_port_vlans_payload,
    _ap_health_payload,
    _ap_radio_config_payload, _ap_rf_scan_payload, _ap_timeline_payload,
    _ap_wifi_neighbors_payload, _ap_wired_downlink_payload, WIRED_DOWNLINK_ROUTE,
    _ap_wired_uplink_payload, _device, WLAN_OVERRIDES_ROUTE,
    _ap_wlan_overrides_payload,
)
from tools import wifi_diagnose


OTHER_SITE_REF = "d" * 24
OTHER_DEVICE_REF = "e" * 24
PRIVATE_AP_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_SITE_ID = "private-site-id"
PRIVATE_TRAFFIC_NOTE = "private-traffic-marker"
SPEED_TEST_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/speed-test-results"


def _lan_traffic_payload(*, site_ref: str = SITE_REF,
                         device_ref: str = AP_REF,
                         raw: dict[str, object] | None = None) -> dict[str, object]:
    raw_values = raw if raw is not None else {
        "rxPkts": 101, "txPkts": 202, "rx": 3030, "tx": 4040,
        "rxDropPkts": 5, "txDropPkts": 6, "rxErrPkts": 7, "txErrPkts": 8,
    }
    projected = project_ap_lan_traffic(raw_values)
    return {**projected, "site_ref": site_ref, "device_ref": device_ref}


class _FakeHttpHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict[str, str]]] = []
    responses: dict[str, tuple[int, object]] = {}

    def _respond(self, method: str) -> None:
        type(self).requests.append((method, self.path, dict(self.headers.items())))
        status, payload = type(self).responses.get(self.path, (404, {"error": PRIVATE_MARKER}))
        if method != "GET":
            status, payload = 405, {"error": "method_not_allowed"}
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

    def do_DELETE(self) -> None:  # noqa: N802
        self._respond("DELETE")

    def log_message(self, *_args: object) -> None:
        return


class WifiDiagnoseApLanTrafficTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(CALLER_TOKEN + "\n")
        os.chmod(self.token_file, 0o600)
        _FakeHttpHandler.requests = []
        payloads = _complete_payloads(SITE_REF)
        _FakeHttpHandler.responses = {
            TOKEN_PATH: (200, {"status": "ok", "items": [{"site_ref": SITE_REF}]}),
            DEVICE_ROUTE: (200, {"status": "ok", "resource": "devices", "count": 1,
                                 "items": [_device()]}),
            HEALTH_ROUTE: (200, _ap_health_payload()),
            TIMELINE_ROUTE: (200, _ap_timeline_payload()),
            RADIO_ROUTE: (200, _ap_radio_config_payload()),
            RF_SCAN_ROUTE: (200, _ap_rf_scan_payload()),
            LAN_TRAFFIC_ROUTE: (200, _lan_traffic_payload()),
            WIFI_NEIGHBORS_ROUTE: (200, _ap_wifi_neighbors_payload()),
            SPEED_TEST_ROUTE: (200, {
                "status": "ok", "resource": "ap_speed_test_results",
                "site_ref": SITE_REF, "device_ref": AP_REF, "partial": False,
                "data": {"main_testing": False,
                         "results": [{"role": 0, "down_rate": 210.5, "up_rate": 32.0,
                                      "time_ms": 1_800_000_000_000, "status": 1}],
                         "source_ap_ref": AP_REF, "target_ap_ref": "c" * 24},
            }),
            WIRED_DOWNLINK_ROUTE: (200, _ap_wired_downlink_payload()),
            WIRED_UPLINK_ROUTE: (200, _ap_wired_uplink_payload()),
            PORTS_ROUTE: (200, _ap_ports_payload()),
            LLDP_CONFIG_ROUTE: (200, _ap_lldp_config_payload()),
            PORT_VLANS_ROUTE: (200, _ap_port_vlans_payload()),
            WLAN_OVERRIDES_ROUTE: (200, _ap_wlan_overrides_payload()),
        }
        for route in SITE_ROUTES:
            _FakeHttpHandler.responses[route] = (200, payloads[route])
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeHttpHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temp.cleanup()

    def invoke(self, *extra: str) -> tuple[int, str, str]:
        stdout, stderr = __import__("io").StringIO(), __import__("io").StringIO()
        with patch.object(wifi_diagnose, "_open_tty", side_effect=AssertionError("unexpected tty")), \
             patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = wifi_diagnose.main([
                "--site-ref", SITE_REF, "--ap-ref", AP_REF,
                "--token-file", self.token_file, "--base-url", self.base_url, *extra,
            ])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_ap_report_uses_bound_response_and_eighteen_gets(self) -> None:
        code, stdout, stderr = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertEqual(report["ap"]["lan_traffic"]["status"], "ok")
        self.assertFalse(report["ap"]["lan_traffic"]["partial"])
        self.assertEqual(report["ap"]["lan_traffic"]["capability_status"], "unknown")
        self.assertEqual(report["ap"]["lan_traffic"]["data"], {
            "rxPkts": 101, "txPkts": 202, "rx": 3030, "tx": 4040,
            "rxDropPkts": 5, "txDropPkts": 6, "rxErrPkts": 7, "txErrPkts": 8,
        })
        self.assertEqual(report["ap"]["speed_test_results"]["data"]["results"], [
            {"role": 0, "down_rate": 210.5, "up_rate": 32.0,
             "time_ms": 1_800_000_000_000, "status": 1},
        ])
        expected = [TOKEN_PATH, DEVICE_ROUTE, *SITE_ROUTES, HEALTH_ROUTE,
                    TIMELINE_ROUTE, RADIO_ROUTE, RF_SCAN_ROUTE, LAN_TRAFFIC_ROUTE,
                    WIFI_NEIGHBORS_ROUTE, SPEED_TEST_ROUTE, WIRED_DOWNLINK_ROUTE,
                    WIRED_UPLINK_ROUTE, PORTS_ROUTE, LLDP_CONFIG_ROUTE, PORT_VLANS_ROUTE,
                    WLAN_OVERRIDES_ROUTE]
        self.assertEqual([path for method, path, _headers in _FakeHttpHandler.requests
                          if method == "GET"], expected)
        self.assertEqual(report["ap"]["wired_downlink"]["data"]["count"], 1)
        self.assertEqual(len(_FakeHttpHandler.requests), 21)
        for method, path, headers in _FakeHttpHandler.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")
        self.assertEqual(report["ap"]["wired_uplink"]["data"]["wiredUplink"]["linkSpeed"], 1000)
        self.assertIn(f"/aps/{AP_REF}/lan-traffic", _FakeHttpHandler.requests[-9][1])
        self.assertIn(f"/aps/{AP_REF}/wifi-neighbors", _FakeHttpHandler.requests[-8][1])
        self.assertIn(f"/aps/{AP_REF}/speed-test-results", _FakeHttpHandler.requests[-7][1])
        self.assertIn(f"/aps/{AP_REF}/wired-downlink", _FakeHttpHandler.requests[-6][1])
        self.assertIn(f"/aps/{AP_REF}/wired-uplink", _FakeHttpHandler.requests[-5][1])
        self.assertIn(f"/aps/{AP_REF}/ports", _FakeHttpHandler.requests[-4][1])
        self.assertIn(f"/aps/{AP_REF}/lldp-config", _FakeHttpHandler.requests[-3][1])
        for private in (CALLER_TOKEN, PRIVATE_AP_MAC, PRIVATE_SITE_ID, PRIVATE_NAME,
                        PRIVATE_IP, PRIVATE_MARKER, PRIVATE_TRAFFIC_NOTE, AP_REF):
            self.assertNotIn(private, stdout + stderr)

    def test_text_mode_shows_only_safe_lan_traffic_status(self) -> None:
        code, stdout, stderr = self.invoke("--format", "text")
        self.assertEqual(code, 0, stdout + stderr)
        self.assertIn("AP-LAN-Verkehrszähler", stdout)
        self.assertIn("Weitere Details: erneut mit --format json ausführen.", stdout)
        self.assertNotIn("101", stdout)
        self.assertNotIn("3030", stdout)
        self.assertNotIn("rxPkts", stdout)
        self.assertNotIn("txDropPkts", stdout)
        for private in (CALLER_TOKEN, PRIVATE_AP_MAC, PRIVATE_SITE_ID, PRIVATE_NAME,
                        PRIVATE_IP, PRIVATE_MARKER, PRIVATE_TRAFFIC_NOTE, AP_REF):
            self.assertNotIn(private, stdout + stderr)
        self.assertEqual(len(_FakeHttpHandler.requests), 21)
        self.assertTrue(all(method == "GET" for method, _, _ in _FakeHttpHandler.requests))

    def test_missing_invalid_and_unknown_counter_projections_remain_partial(self) -> None:
        cases = (
            _lan_traffic_payload(raw={k: v for k, v in {
                "rxPkts": 101, "txPkts": 202, "rx": 3030, "tx": 4040,
                "rxDropPkts": 5, "txDropPkts": 6, "rxErrPkts": 7, "txErrPkts": 8,
            }.items() if k != "rxPkts"}),
            _lan_traffic_payload(raw={
                "rxPkts": True, "txPkts": 202, "rx": 3030, "tx": 4040,
                "rxDropPkts": 5, "txDropPkts": 6, "rxErrPkts": 7, "txErrPkts": 8,
            }),
            _lan_traffic_payload(raw={
                "rxPkts": 101, "txPkts": 202, "rx": 3030, "tx": 4040,
                "rxDropPkts": 5, "txDropPkts": 6, "rxErrPkts": 7, "txErrPkts": 8,
                "privateCounter": PRIVATE_TRAFFIC_NOTE,
            }),
        )
        for payload in cases:
            with self.subTest(payload=payload):
                _FakeHttpHandler.responses[LAN_TRAFFIC_ROUTE] = (200, payload)
                code, stdout, stderr = self.invoke()
                self.assertEqual(code, 0, stdout + stderr)
                traffic = json.loads(stdout)["ap"]["lan_traffic"]
                self.assertEqual(traffic["status"], "ok")
                self.assertTrue(traffic["partial"])
                self.assertEqual(traffic["capability_status"], "unknown")
                for private in (PRIVATE_TRAFFIC_NOTE, "privateCounter", PRIVATE_AP_MAC,
                                PRIVATE_NAME, PRIVATE_IP):
                    self.assertNotIn(private, stdout + stderr)

    def test_wrong_site_or_device_binding_is_isolated_from_other_ap_sources(self) -> None:
        for wrong in (_lan_traffic_payload(site_ref=OTHER_SITE_REF),
                      _lan_traffic_payload(device_ref=OTHER_DEVICE_REF)):
            _FakeHttpHandler.responses[LAN_TRAFFIC_ROUTE] = (200, wrong)
            code, stdout, stderr = self.invoke()
            self.assertEqual(code, 0, stdout + stderr)
            ap = json.loads(stdout)["ap"]
            self.assertEqual(ap["lan_traffic"]["status"], "error")
            self.assertEqual(ap["lan_traffic"]["capability_status"], "unknown")
            self.assertEqual(ap["health"]["status"], "ok")
            self.assertEqual(ap["radio_config"]["status"], "ok")
            self.assertNotIn(OTHER_SITE_REF, stdout + stderr)
            self.assertNotIn(OTHER_DEVICE_REF, stdout + stderr)

    def test_unknown_wrapper_field_is_partial_and_redacted(self) -> None:
        payload = _lan_traffic_payload()
        payload["privateWrapperField"] = PRIVATE_TRAFFIC_NOTE
        _FakeHttpHandler.responses[LAN_TRAFFIC_ROUTE] = (200, payload)
        code, stdout, stderr = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        traffic = json.loads(stdout)["ap"]["lan_traffic"]
        self.assertEqual(traffic["status"], "ok")
        self.assertTrue(traffic["partial"])
        self.assertNotIn("privateWrapperField", json.dumps(traffic))
        self.assertNotIn(PRIVATE_TRAFFIC_NOTE, stdout + stderr)

    def test_transport_error_is_sanitized_and_does_not_hide_other_ap_reads(self) -> None:
        _FakeHttpHandler.responses[LAN_TRAFFIC_ROUTE] = (
            502, {"error": PRIVATE_TRAFFIC_NOTE, "message": PRIVATE_NAME})
        code, stdout, stderr = self.invoke()
        self.assertEqual(code, 0, stdout + stderr)
        ap = json.loads(stdout)["ap"]
        self.assertEqual(ap["status"], "partial")
        self.assertEqual(ap["lan_traffic"]["status"], "error")
        self.assertEqual(ap["health"]["status"], "ok")
        self.assertEqual(ap["rf_scan"]["status"], "ok")
        self.assertNotIn(PRIVATE_TRAFFIC_NOTE, stdout + stderr)
        self.assertNotIn(PRIVATE_NAME, stdout + stderr)
        self.assertTrue(all(method == "GET" for method, _, _ in _FakeHttpHandler.requests))


if __name__ == "__main__":
    unittest.main()
