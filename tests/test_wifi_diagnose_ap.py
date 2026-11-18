from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.ap_health import project_ap_health_detail
from app.ap_health_timeline import project_ap_health_timeline
from app.ap_lan_traffic import project_ap_lan_traffic
from app.openapi import OmadaOpenApiClient
from tests.test_wifi_diagnose import (
    CALLER_TOKEN,
    PRIVATE_IP,
    PRIVATE_MARKER,
    PRIVATE_NAME,
    SITE_REF,
    _complete_payloads,
)
from tools.wifi_diagnose import (
    CliError, _ap_health_response, _ap_wifi_neighbors_response,
    _ap_ports_response, _ap_wired_uplink_response, _ap_port_vlans_response,
    _ap_wlan_overrides_response,
)


AP_REF = "b" * 24
OTHER_AP_REF = "c" * 24
OTHER_SITE_REF = "d" * 24
PRIVATE_MAC = "AA-BB-CC-DD-EE-FF"
SITE_ROUTES = (
    f"/v1/sites/{SITE_REF}/wifi/health/timeline",
    f"/v1/sites/{SITE_REF}/wifi/health/details",
    f"/v1/sites/{SITE_REF}/wifi/channels",
    f"/v1/sites/{SITE_REF}/wifi/client-signal-distribution",
    f"/v1/sites/{SITE_REF}/wifi/6ghz-ap-presence",
    f"/v1/sites/{SITE_REF}/wifi/rogue-ap-results",
)
DEVICE_ROUTE = f"/v1/sites/{SITE_REF}/devices"
HEALTH_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health"
TIMELINE_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/health/timeline"
RADIO_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/radio-config"
RF_SCAN_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/rf-scan"
LAN_TRAFFIC_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/lan-traffic"
WIFI_NEIGHBORS_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/wifi-neighbors"
SPEED_TEST_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/speed-test-results"
WIRED_DOWNLINK_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/wired-downlink"
WIRED_UPLINK_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/wired-uplink"
PORTS_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/ports"
LLDP_CONFIG_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/lldp-config"
PORT_VLANS_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/port-vlans"
WLAN_OVERRIDES_ROUTE = f"/v1/sites/{SITE_REF}/aps/{AP_REF}/wlan-overrides"
TOKEN_PATH = "/v1/sites"
WINDOW_START_MS = 1_700_000_000_000
WINDOW_END_MS = WINDOW_START_MS + 86_400_000


def _device(device_ref: str = AP_REF, device_type: str | None = "AP") -> dict[str, object]:
    item: dict[str, object] = {"device_ref": device_ref, "state": 1}
    if device_type is not None:
        item["device_type"] = device_type
    return item


def _ap_wlan_overrides_payload(device_ref: str = AP_REF) -> dict[str, object]:
    return {
        "status": "ok", "resource": "ap_wlan_overrides",
        "site_ref": SITE_REF, "device_ref": device_ref,
        "entry_count": 0, "included_entry_count": 0, "truncated_entry_count": 0,
        "enabled_count": 0, "disabled_count": 0,
        "unknown_enabled_state_count": 0, "vlan_enabled_count": 0,
        "vlan_disabled_count": 0, "unknown_vlan_state_count": 0,
        "password_present_count": 0, "vlan_id_present_count": 0,
        "vlan_pool_present_count": 0, "by_band_code": {},
        "by_security_code": {}, "ap_group_assigned": False,
        "redacted_field_count": 0, "invalid_row_count": 0,
        "unknown_field_count": 0, "invalid_field_count": 0,
        "missing_field_count": 0, "partial": False,
    }


def _ap_health_payload(site_ref: str = SITE_REF, device_ref: str = AP_REF) -> dict[str, object]:
    raw = {
        "score": 82,
        "cpu": {"summaryScore": 80, "support": True, "averageNum": 3,
                "pastNums": [{"time": WINDOW_END_MS, "pastNum": 2}]},
        "channelUtil": {"summaryScore": 77, "support": True,
                         "averageNum2g": 10, "averageNum5g": 20,
                         "pastNums2g": [{"time": WINDOW_END_MS, "pastNum": 9}]},
    }
    return {
        "status": "ok", "resource": "ap_health", "site_ref": site_ref,
        "device_ref": device_ref, "window_start_ms": WINDOW_START_MS,
        "window_end_ms": WINDOW_END_MS,
        "data": project_ap_health_detail(raw, WINDOW_START_MS, WINDOW_END_MS),
    }


def _ap_timeline_payload(site_ref: str = SITE_REF,
                         device_ref: str = AP_REF) -> dict[str, object]:
    projected = project_ap_health_timeline({
        "scores": [{"time": WINDOW_START_MS + 1, "score": 81},
                   {"time": WINDOW_END_MS, "score": 82}],
    }, WINDOW_START_MS, WINDOW_END_MS)
    return {
        **projected, "site_ref": site_ref, "device_ref": device_ref,
        "window_start_ms": WINDOW_START_MS, "window_end_ms": WINDOW_END_MS,
    }


def _ap_radio_config_payload() -> dict[str, object]:
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
    }
    return {"status": "ok", "resource": "radio_config", "device_ref": AP_REF,
            "data": OmadaOpenApiClient._sanitize_ap_entity("radio_config", raw)}


def _ap_rf_scan_payload() -> dict[str, object]:
    return {"status": "ok", "resource": "ap_rf_scan", "device_ref": AP_REF,
            "data": {"2g": [], "5g": [], "5g2": [], "6g": [],
                     "2g_scan_status": 1, "5g_scan_status": 1,
                     "5g2_scan_status": 1, "6g_scan_status": 1}}


def _ap_lan_traffic_payload(site_ref: str = SITE_REF,
                            device_ref: str = AP_REF) -> dict[str, object]:
    raw = {"rxPkts": 101, "txPkts": 202, "rx": 3030, "tx": 4040,
           "rxDropPkts": 5, "txDropPkts": 6, "rxErrPkts": 7, "txErrPkts": 8}
    return {**project_ap_lan_traffic(raw), "site_ref": site_ref, "device_ref": device_ref}


def _ap_wifi_neighbors_payload(site_ref: str = SITE_REF,
                               device_ref: str = AP_REF) -> dict[str, object]:
    return {"status": "ok", "resource": "ap_wifi_neighbors", "site_ref": site_ref,
            "device_ref": device_ref, "count": 1,
            "items": [{"neighbor_ref": "c" * 24, "band": "5g", "channel": 44,
                       "signal_dbm": -62, "bandwidth": 80,
                       "last_seen_ms": 1_800_000_000_000}]}


def _ap_speed_test_payload(site_ref: str = SITE_REF,
                           device_ref: str = AP_REF) -> dict[str, object]:
    return {"status": "ok", "resource": "ap_speed_test_results",
            "site_ref": site_ref, "device_ref": device_ref, "partial": False,
            "data": {"main_testing": False,
                     "results": [{"role": 0, "down_rate": 100.5, "up_rate": 20.25,
                                  "time_ms": 1_800_000_000_000, "status": 1}],
                     "source_ap_ref": device_ref, "target_ap_ref": "c" * 24}}


def _ap_wired_downlink_payload(site_ref: str = SITE_REF,
                               device_ref: str = AP_REF) -> dict[str, object]:
    return {"status": "ok", "resource": "ap_wired_downlink", "site_ref": site_ref,
            "device_ref": device_ref, "count": 1, "source_count": 1,
            "items": [{"device_ref": "c" * 24, "port": "eth1", "speed": 1000,
                       "rx": 1234, "tx": 2345}], "partial": False,
            "omitted_count": 0, "unknown_field_count": 0, "redacted_field_count": 4}


def _ap_wired_uplink_payload(site_ref: str = SITE_REF,
                             device_ref: str = AP_REF) -> dict[str, object]:
    return {"status": "ok", "resource": "ap_wired_uplink", "site_ref": site_ref,
            "device_ref": device_ref,
            "data": {"wiredUplink": {
                "duplex": 2, "portType": 1, "upBytes": 1000, "downBytes": 2000,
                "upPackets": 10, "downPackets": 20, "upDropPackets": 0,
                "downDropPackets": 0, "upErrorsPackets": 0, "downErrorsPackets": 0,
                "activity": 30, "linkStatus": 1, "linkSpeed": 1000, "rate_mbps": 1000,
            }}, "partial": False, "missing_fields": [], "invalid_fields": [],
            "unknown_field_count": 0, "redacted_field_count": 9}


def _ap_ports_payload(site_ref: str = SITE_REF, device_ref: str = AP_REF) -> dict[str, object]:
    return {"status": "ok", "resource": "ap_ports", "site_ref": site_ref,
            "device_ref": device_ref, "count": 1,
            "summary": {"by_link_status_code": {"1": 1}, "by_link_speed_code": {"3": 1},
                        "by_port_type_code": {}, "duplex_code_counts": {},
                        "poe_supported_ports": 0, "poe_output_enabled_ports": 0,
                        "uplink_ports": 1, "logical_uplink_ports": 0,
                        "vlan_supported_ports": 1, "local_vlan_enabled_ports": 0,
                        "poe_state_code_counts": {}, "poe_input_mode_code_counts": {},
                        "unknown_row_count": 0, "invalid_field_count": 0,
                        "unknown_field_count": 0}, "partial": False}


def _ap_lldp_config_payload(site_ref: str = SITE_REF,
                            device_ref: str = AP_REF) -> dict[str, object]:
    return {"status": "ok", "resource": "ap_lldp_config", "site_ref": site_ref,
            "device_ref": device_ref,
            "data": {"setting_code": 2, "setting": "site_default", "supported": True},
            "partial": False, "missing_field_count": 0, "invalid_field_count": 0,
            "unknown_field_count": 0}


def _ap_port_vlans_payload(site_ref: str = SITE_REF,
                           device_ref: str = AP_REF) -> dict[str, object]:
    return {"status": "ok", "resource": "ap_port_vlans", "site_ref": site_ref,
            "device_ref": device_ref, "count": 1, "total_rows": 1,
            "vlan_id_counts": {"10": 1},
            "port_counts": {"nativePort": 1, "tagPort": 0, "untagPort": 0},
            "redacted_field_count": 2, "unknown_field_count": 0,
            "invalid_row_or_field_count": 0, "partial": False}


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


class WifiDiagnoseApTests(unittest.TestCase):
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

    def set_responses(self, devices: list[dict[str, object]] | None = None) -> None:
        _FakeConnector.requests = []
        site_payloads = _complete_payloads(SITE_REF)
        _FakeConnector.responses = {
            TOKEN_PATH: (200, {"status": "ok", "items": [{"site_ref": SITE_REF}]}, {}),
            DEVICE_ROUTE: (200, {
                "status": "ok", "resource": "devices",
                "count": len(devices if devices is not None else [_device()]),
                "items": devices if devices is not None else [_device()],
            }, {}),
        }
        for path in SITE_ROUTES:
            _FakeConnector.responses[path] = (200, site_payloads[path], {})
        _FakeConnector.responses[HEALTH_ROUTE] = (200, _ap_health_payload(), {})
        _FakeConnector.responses[TIMELINE_ROUTE] = (200, _ap_timeline_payload(), {})
        _FakeConnector.responses[RADIO_ROUTE] = (200, _ap_radio_config_payload(), {})
        _FakeConnector.responses[RF_SCAN_ROUTE] = (200, _ap_rf_scan_payload(), {})
        _FakeConnector.responses[LAN_TRAFFIC_ROUTE] = (200, _ap_lan_traffic_payload(), {})
        _FakeConnector.responses[WIFI_NEIGHBORS_ROUTE] = (200, _ap_wifi_neighbors_payload(), {})
        _FakeConnector.responses[SPEED_TEST_ROUTE] = (200, _ap_speed_test_payload(), {})
        _FakeConnector.responses[WIRED_DOWNLINK_ROUTE] = (200, _ap_wired_downlink_payload(), {})
        _FakeConnector.responses[WIRED_UPLINK_ROUTE] = (200, _ap_wired_uplink_payload(), {})
        _FakeConnector.responses[PORTS_ROUTE] = (200, _ap_ports_payload(), {})
        _FakeConnector.responses[LLDP_CONFIG_ROUTE] = (200, _ap_lldp_config_payload(), {})
        _FakeConnector.responses[PORT_VLANS_ROUTE] = (200, _ap_port_vlans_payload(), {})
        _FakeConnector.responses[WLAN_OVERRIDES_ROUTE] = (200, {
            "status": "ok", "resource": "ap_wlan_overrides",
            "site_ref": SITE_REF, "device_ref": AP_REF,
            "entry_count": 2, "included_entry_count": 2, "truncated_entry_count": 0,
            "enabled_count": 1, "disabled_count": 1,
            "unknown_enabled_state_count": 0, "vlan_enabled_count": 1,
            "vlan_disabled_count": 1, "unknown_vlan_state_count": 0,
            "password_present_count": 1, "vlan_id_present_count": 1,
            "vlan_pool_present_count": 0, "by_band_code": {1: 2},
            "by_security_code": {3: 2}, "ap_group_assigned": True,
            "redacted_field_count": 8, "invalid_row_count": 0,
            "unknown_field_count": 0, "invalid_field_count": 0,
            "missing_field_count": 0, "partial": False,
        }, {})

    def run_cli(self, *extra: str) -> subprocess.CompletedProcess[str]:
        script = os.path.join(os.path.dirname(__file__), "..", "tools", "wifi_diagnose.py")
        return subprocess.run(
            [sys.executable, script, "--site-ref", SITE_REF, "--ap-ref", AP_REF,
             "--token-file", self.token_file, "--base-url", self.base_url, *extra],
            capture_output=True, text=True, timeout=12, check=False,
        )

    def test_ap_drilldown_uses_inventory_site_summary_and_thirteen_fixed_ap_gets(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["site_ref"], SITE_REF)
        self.assertIn("ap", report)
        ap = report["ap"]
        self.assertEqual(ap["capability_status"], "unknown")
        self.assertEqual(ap["status"], "ok")
        self.assertEqual(ap["lan_traffic"]["status"], "ok")
        self.assertFalse(ap["lan_traffic"]["partial"])
        self.assertEqual(ap["lan_traffic"]["capability_status"], "unknown")
        self.assertEqual(ap["lan_traffic"]["data"]["rx"], 3030)
        self.assertEqual(ap["lan_traffic"]["data"]["txErrPkts"], 8)
        self.assertEqual(ap["wifi_neighbors"]["data"], {
            "count": 1, "rows": [{"band": "5g", "channel": 44,
                                    "signal_dbm": -62, "bandwidth": 80}],
            "omitted_count": 0,
        })
        for key in ("health", "timeline"):
            self.assertEqual(ap[key]["status"], "ok")
            self.assertFalse(ap[key]["partial"])
            self.assertEqual(ap[key]["capability_status"], "unknown")
            self.assertEqual(ap[key]["window"], {
                "start_ms": WINDOW_START_MS, "end_ms": WINDOW_END_MS,
            })
        self.assertEqual(ap["timeline"]["data"]["scores"], [
            {"time_ms": WINDOW_START_MS + 1, "score": 81},
            {"time_ms": WINDOW_END_MS, "score": 82},
        ])
        self.assertEqual(
            [(method, path) for method, path, _headers in _FakeConnector.requests],
            [("GET", TOKEN_PATH), ("GET", DEVICE_ROUTE),
             *(("GET", path) for path in SITE_ROUTES),
             ("GET", HEALTH_ROUTE), ("GET", TIMELINE_ROUTE),
             ("GET", RADIO_ROUTE), ("GET", RF_SCAN_ROUTE), ("GET", LAN_TRAFFIC_ROUTE),
             ("GET", WIFI_NEIGHBORS_ROUTE), ("GET", SPEED_TEST_ROUTE),
             ("GET", WIRED_DOWNLINK_ROUTE), ("GET", WIRED_UPLINK_ROUTE),
             ("GET", PORTS_ROUTE), ("GET", LLDP_CONFIG_ROUTE),
             ("GET", PORT_VLANS_ROUTE), ("GET", WLAN_OVERRIDES_ROUTE)],
        )
        self.assertLessEqual(len(_FakeConnector.requests), 21)
        self.assertEqual(ap["wired_uplink"]["data"]["wiredUplink"]["linkSpeed"], 1000)
        self.assertEqual(ap["ports"]["summary"]["uplink_ports"], 1)
        self.assertEqual(ap["lldp_config"]["data"]["setting"], "site_default")
        self.assertEqual(ap["port_vlans"]["vlan_id_counts"], {"10": 1})
        self.assertEqual(ap["wlan_overrides"]["data"]["entry_count"], 2)
        self.assertEqual(ap["wlan_overrides"]["data"]["enabled_count"], 1)
        for method, _path, headers in _FakeConnector.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")
        rendered = result.stdout + result.stderr
        for private in (CALLER_TOKEN, PRIVATE_MAC, PRIVATE_IP, PRIVATE_NAME, PRIVATE_MARKER):
            self.assertNotIn(private, rendered)

    def test_neighbor_projection_caps_rows_and_rejects_malformed_values(self) -> None:
        payload = _ap_wifi_neighbors_payload()
        row = payload["items"][0]
        many = {**payload, "count": 65, "items": [row] * 65}
        projected = _ap_wifi_neighbors_response(many, SITE_REF, AP_REF)
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["data"]["count"], 65)
        self.assertEqual(len(projected["data"]["rows"]), 64)
        self.assertEqual(projected["data"]["omitted_count"], 1)
        self.assertNotIn("neighbor_ref", repr(projected))
        malformed = {**payload, "items": [{**row, "band": []}]}
        malformed_projection = _ap_wifi_neighbors_response(malformed, SITE_REF, AP_REF)
        self.assertTrue(malformed_projection["partial"])
        self.assertEqual(malformed_projection["data"]["rows"], [])

    def test_wired_uplink_projection_keeps_only_bounded_measurements(self) -> None:
        payload = _ap_wired_uplink_payload()
        payload["data"]["wiredUplink"]["controller_secret"] = PRIVATE_MARKER
        projected = _ap_wired_uplink_response(payload, SITE_REF, AP_REF)
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["data"]["wiredUplink"]["linkSpeed"], 1000)
        self.assertNotIn("controller_secret", repr(projected))
        self.assertNotIn(PRIVATE_MARKER, repr(projected))
        with self.assertRaises(CliError):
            _ap_wired_uplink_response(_ap_wired_uplink_payload(device_ref=OTHER_AP_REF),
                                      SITE_REF, AP_REF)

    def test_ap_ports_projection_is_site_and_device_bound(self) -> None:
        projected = _ap_ports_response(_ap_ports_payload(), SITE_REF, AP_REF)
        self.assertEqual(projected["summary"]["by_link_status_code"], {"1": 1})
        self.assertFalse(projected["partial"])
        with self.assertRaises(CliError):
            _ap_ports_response(_ap_ports_payload(device_ref=OTHER_AP_REF), SITE_REF, AP_REF)

    def test_ap_port_vlans_projection_is_site_and_device_bound(self) -> None:
        projected = _ap_port_vlans_response(_ap_port_vlans_payload(), SITE_REF, AP_REF)
        self.assertEqual(projected["vlan_id_counts"], {"10": 1})
        self.assertFalse(projected["partial"])
        with self.assertRaises(CliError):
            _ap_port_vlans_response(_ap_port_vlans_payload(device_ref=OTHER_AP_REF),
                                    SITE_REF, AP_REF)

    def test_wlan_overrides_projection_keeps_only_bounded_counts(self) -> None:
        payload = _FakeConnector.responses[WLAN_OVERRIDES_ROUTE][1]
        projected = _ap_wlan_overrides_response(payload, SITE_REF, AP_REF)
        self.assertFalse(projected["partial"])
        self.assertEqual(projected["data"]["entry_count"], 2)
        self.assertEqual(projected["data"]["by_band_code"], {"1": 2})
        malformed = {**payload, "ssidName": "private-name"}
        projected_malformed = _ap_wlan_overrides_response(malformed, SITE_REF, AP_REF)
        self.assertTrue(projected_malformed["partial"])
        self.assertNotIn("private-name", repr(projected_malformed))
        with self.assertRaises(CliError):
            _ap_wlan_overrides_response({**payload, "device_ref": OTHER_AP_REF},
                                        SITE_REF, AP_REF)

    def test_missing_or_wrong_site_inventory_ref_stops_before_devices(self) -> None:
        _FakeConnector.responses[TOKEN_PATH] = (
            200, {"status": "ok", "items": [{"site_ref": OTHER_SITE_REF}]}, {})
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([path for _method, path, _ in _FakeConnector.requests], [TOKEN_PATH])
        self.assertNotIn(OTHER_SITE_REF, result.stdout + result.stderr)

    def test_unknown_missing_ambiguous_and_non_ap_device_refs_never_call_ap_routes(self) -> None:
        scenarios = (
            ("unknown", [_device(OTHER_AP_REF)], "not present"),
            ("missing type", [_device(AP_REF, None)], "not explicitly AP"),
            ("wrong type", [_device(AP_REF, "switch")], "not explicitly AP"),
            ("unknown type", [_device(AP_REF, "EAP-650")], "not explicitly AP"),
            ("ambiguous ref", [_device(), _device()], "duplicate"),
        )
        for label, devices, _reason in scenarios:
            with self.subTest(label=label):
                self.set_responses(devices)
                result = self.run_cli()
                paths = [path for method, path, _ in _FakeConnector.requests if method == "GET"]
                self.assertNotIn(HEALTH_ROUTE, paths)
                self.assertNotIn(TIMELINE_ROUTE, paths)
                self.assertNotIn(RADIO_ROUTE, paths)
                self.assertNotIn(RF_SCAN_ROUTE, paths)
                self.assertEqual(paths, [TOKEN_PATH, DEVICE_ROUTE])
                self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

    def test_device_inventory_count_ref_and_bounds_fail_closed(self) -> None:
        invalid = [
            (200, {"status": "ok", "resource": "devices", "count": 2, "items": [_device()]}),
            (200, {"status": "ok", "resource": "devices", "count": 1,
                  "items": [_device("NOT-AN-OPAQUE-REF")]}),
            (200, {"status": "ok", "resource": "devices", "count": 4001,
                  "items": [_device()]}),
        ]
        for status, payload in invalid:
            with self.subTest(payload=payload):
                self.set_responses()
                _FakeConnector.responses[DEVICE_ROUTE] = (status, payload, {})
                result = self.run_cli()
                paths = [path for method, path, _ in _FakeConnector.requests if method == "GET"]
                self.assertNotIn(HEALTH_ROUTE, paths)
                self.assertNotIn(TIMELINE_ROUTE, paths)
                self.assertNotIn(RADIO_ROUTE, paths)
                self.assertNotIn(RF_SCAN_ROUTE, paths)
                self.assertEqual(paths, [TOKEN_PATH, DEVICE_ROUTE])
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

    def test_ap_responses_are_bound_to_requested_site_and_device(self) -> None:
        for route, payload in (
            (HEALTH_ROUTE, _ap_health_payload(site_ref=OTHER_SITE_REF)),
            (TIMELINE_ROUTE, _ap_timeline_payload(device_ref=OTHER_AP_REF)),
        ):
            with self.subTest(route=route):
                self.set_responses()
                _FakeConnector.responses[route] = (200, payload, {})
                result = self.run_cli()
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertIn("ap", report)
                route_result = (report["ap"]["health"] if route == HEALTH_ROUTE
                                else report["ap"]["timeline"])
                self.assertEqual(route_result["status"], "error")
                self.assertEqual(report["ap"]["status"], "partial")
                self.assertEqual(report["ap"]["capability_status"], "unknown")
                self.assertNotIn(OTHER_SITE_REF, result.stdout + result.stderr)
                self.assertNotIn(OTHER_AP_REF, result.stdout + result.stderr)

    def test_partial_ap_health_and_timeline_keep_safe_numbers_only(self) -> None:
        health = _ap_health_payload()
        health["data"]["ssid"] = PRIVATE_NAME
        health["data"]["ip"] = PRIVATE_IP
        health["data"]["mac"] = PRIVATE_MAC
        timeline = _ap_timeline_payload()
        timeline["partial"] = True
        timeline["data"]["scores"] = []
        timeline["missing_fields"] = [PRIVATE_MARKER]
        timeline["omitted_fields"] = [PRIVATE_NAME]
        _FakeConnector.responses[HEALTH_ROUTE] = (200, health, {})
        _FakeConnector.responses[TIMELINE_ROUTE] = (200, timeline, {})
        result = self.run_cli()
        report = json.loads(result.stdout)
        self.assertEqual(report["ap"]["status"], "partial")
        self.assertTrue(report["ap"]["timeline"]["partial"])
        rendered = result.stdout + result.stderr
        for private in (PRIVATE_MAC, PRIVATE_IP, PRIVATE_NAME, PRIVATE_MARKER):
            self.assertNotIn(private, rendered)

    def test_ap_health_cli_preserves_api_partial_and_accepts_legacy_payload(self) -> None:
        payload = _ap_health_payload()
        projected = _ap_health_response(payload, SITE_REF, AP_REF)
        self.assertFalse(projected["partial"])
        payload["partial"] = True
        self.assertTrue(_ap_health_response(payload, SITE_REF, AP_REF)["partial"])
        payload["partial"] = "true"
        with self.assertRaises(CliError):
            _ap_health_response(payload, SITE_REF, AP_REF)

    def test_negative_ap_health_count_fields_are_omitted_and_mark_partial(self) -> None:
        health = _ap_health_payload()
        data = health["data"]
        data["incident"] = {"incident_count": -1}
        data["cpu"]["incidents_count"] = -2
        data["cpu"]["discarded_out_of_window_points"] = -3
        _FakeConnector.responses[HEALTH_ROUTE] = (200, health, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        ap_health = report["ap"]["health"]
        self.assertTrue(ap_health["partial"])
        self.assertNotIn("incident_count", ap_health["data"]["incident"])
        self.assertNotIn("incidents_count", ap_health["data"]["cpu"])
        self.assertNotIn("discarded_out_of_window_points", ap_health["data"]["cpu"])
        self.assertEqual(ap_health["capability_status"], "unknown")

    def test_oversized_ap_inventory_fails_without_silent_truncation_or_ap_reads(self) -> None:
        payload = {
            "status": "ok", "resource": "devices", "count": 1,
            "items": [_device()], "private": PRIVATE_MARKER + ("x" * (300 * 1024)),
        }
        _FakeConnector.responses[DEVICE_ROUTE] = (200, payload, {})
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        paths = [path for method, path, _ in _FakeConnector.requests if method == "GET"]
        self.assertEqual(paths, [TOKEN_PATH, DEVICE_ROUTE])
        self.assertNotIn(PRIVATE_MARKER, result.stdout + result.stderr)
        self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
