from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.channel_dashboard import project_site_dashboard_channels
from app.client_signal_distribution import project_client_signal_distribution
from app.wifi_health import project_wifi_health
from app.wifi_subhealth import project_wifi_subhealth
from app.rogue_ap_results import summarize_rogue_ap_results
from app.wids_summary import summarize_wids_results, summarize_wids_blacklist


SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
CALLER_TOKEN = "wifi-diagnose-caller-token-do-not-print-0123456789"
PRIVATE_NAME = "private-office-name-do-not-print"
PRIVATE_IP = "192.0.2.73"
PRIVATE_MARKER = "untrusted-response-private-marker"
FIXED_DIAGNOSTIC_ROUTES = (
    f"/v1/sites/{SITE_REF}/wifi/health/timeline",
    f"/v1/sites/{SITE_REF}/wifi/health/details",
    f"/v1/sites/{SITE_REF}/wifi/channels",
    f"/v1/sites/{SITE_REF}/wifi/client-signal-distribution",
    f"/v1/sites/{SITE_REF}/wifi/6ghz-ap-presence",
    f"/v1/sites/{SITE_REF}/wifi/rogue-ap-results",
    f"/v1/sites/{SITE_REF}/wifi/wids-summary",
    f"/v1/sites/{SITE_REF}/wifi/wids-blacklist-summary",
    f"/v1/sites/{SITE_REF}/wifi/band-steering",
    f"/v1/sites/{SITE_REF}/wifi/optimization",
    f"/v1/sites/{SITE_REF}/wifi/roaming",
    f"/v1/sites/{SITE_REF}/topology/network-summary",
)
RESULT_KEYS = (
    "wifi_health_timeline", "wifi_health_details", "wifi_channels",
    "client_signal_distribution",
    "site_6ghz_ap_presence",
    "site_rogue_ap_results",
    "site_wids_summary",
    "site_wids_blacklist_summary",
    "band_steering", "rrm_settings", "roaming_settings",
    "site_topology_network_summary",
)
START_MS = 1
END_MS = START_MS + 86_400_000


def _raw_subhealth() -> dict[str, object]:
    common = {
        "summaryScore": 71,
        "support": True,
        "scores": [{"time": END_MS, "score": 71}],
    }
    return {
        "wifiHealthScore": 71,
        "accessTimeScoreDetail": dict(common),
        "channelUtilScoreDetail": dict(common),
        "accessCapacityScoreDetail": dict(common),
        "rssiScoreDetail": dict(common),
        "channelInterUtilDetail": {
            **common, "averageInterf2g": 1, "averageInterf5g": 2,
            "averageInterf6g": 3, "averageNoiseFloor": -90,
        },
        "wirelessClientQualityDetail": {
            "summaryScore": 71, "support": True,
            "assocTime": [{"time": END_MS, "pastNum": 1}],
            "authTime": [{"time": END_MS, "pastNum": 1}],
            "dhcpTime": [{"time": END_MS, "pastNum": 1}],
            "dnsTime": [{"time": END_MS, "pastNum": 1}],
            "averageAssocTime": 1, "averageAuthTime": 1,
            "averageDhcpTime": 1, "averageDnsTime": 1,
        },
    }


def _complete_payloads(site_ref: str = SITE_REF) -> dict[str, object]:
    timeline = project_wifi_health({"scores": [{"time": END_MS, "score": 71}]}, START_MS, END_MS)
    timeline_payload = {
        "status": "ok", "resource": "wifi_health", "site_ref": site_ref,
        "data": timeline, "query_time_unit": "milliseconds_documented_not_live_verified",
    }
    details = project_wifi_subhealth(_raw_subhealth(), START_MS, END_MS)
    details["site_ref"] = site_ref
    channels = project_site_dashboard_channels({
        "2g channel stat": [{"channel": 6, "apNum": 2, "clientNum": 3, "channelUtilization": 20}],
        "5g channel stat": [{"channel": 36, "apNum": 2, "clientNum": 3, "channelUtilization": 10}],
        "6g channel stat": [{"channel": 5, "apNum": 1, "clientNum": 2, "channelUtilization": None}],
    })
    channels["site_ref"] = site_ref
    signal = project_client_signal_distribution({
        category: {"totalClients": 1, "clientsPercent": 20, "clients2g": 1,
                   "clients5g": 1, "clients6g": 1}
        for category in ("poorSignal", "weakSignal", "averageSignal", "stableSignal", "strongSignal")
    })
    signal["site_ref"] = site_ref
    return {
        "/v1/sites": {"status": "ok", "items": [{"site_ref": site_ref}]},
        FIXED_DIAGNOSTIC_ROUTES[0]: timeline_payload,
        FIXED_DIAGNOSTIC_ROUTES[1]: details,
        FIXED_DIAGNOSTIC_ROUTES[2]: channels,
        FIXED_DIAGNOSTIC_ROUTES[4]: {
            "status": "ok", "resource": "site_6ghz_ap_presence", "site_ref": site_ref,
            "data": {"has_6ghz_ap": True},
        },
        FIXED_DIAGNOSTIC_ROUTES[3]: signal,
        FIXED_DIAGNOSTIC_ROUTES[5]: {
            **summarize_rogue_ap_results([]), "site_ref": site_ref,
        },
        FIXED_DIAGNOSTIC_ROUTES[6]: {
            **summarize_wids_results([], 0), "site_ref": site_ref,
        },
        FIXED_DIAGNOSTIC_ROUTES[7]: {
            **summarize_wids_blacklist([], 0), "site_ref": site_ref,
        },
        FIXED_DIAGNOSTIC_ROUTES[8]: {
            "status": "ok", "resource": "band_steering", "site_ref": site_ref,
            "data": {"mode": 1},
        },
        FIXED_DIAGNOSTIC_ROUTES[9]: {
            "status": "ok", "resource": "rrm_settings", "site_ref": site_ref,
            "data": {"mode": 1, "timeRangeEnable": False, "resource": 0,
                     "timeRangeAction": 1}, "partial": False, "omitted_field_count": 0,
        },
        FIXED_DIAGNOSTIC_ROUTES[10]: {
            "status": "ok", "resource": "roaming_settings", "site_ref": site_ref,
            "data": {"fastRoamingEnable": True, "aiRoamingEnable": False,
                     "dualBand11kReportEnable": True, "forceDisassociationEnable": False,
                     "nonStickRoamingEnable": True}, "partial": False,
            "omitted_field_count": 0,
        },
        FIXED_DIAGNOSTIC_ROUTES[11]: {
            "status": "ok", "resource": "site_topology_network_summary",
            "site_ref": site_ref,
            "data": {"unknown_field_count": 0, "split_network_count": 2,
                     "default_network_count": 1, "configuring_network_count": 0,
                     "unknown_network_field_count": 0, "ssid_count": 3,
                     "ssid_vlan_enabled_count": 1, "ssid_configuring_count": 0,
                     "ssid_client_count_sum": 6, "ssid_vlan_id_count": 2,
                     "unknown_ssid_field_count": 0, "partial": False},
            "partial": False,
        },
    }


class _FakeConnector(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict[str, str]]] = []
    responses: dict[str, tuple[int, object, dict[str, str]]] = {}
    delay_paths: set[str] = set()

    def do_GET(self) -> None:  # noqa: N802
        self.__class__.requests.append(("GET", self.path, dict(self.headers.items())))
        if self.path in self.__class__.delay_paths:
            time.sleep(2.5)
        status, payload, headers = self.__class__.responses.get(
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
        self.__class__.requests.append(("POST", self.path, dict(self.headers.items())))
        self.send_error(405)

    def do_PUT(self) -> None:  # noqa: N802
        self.__class__.requests.append(("PUT", self.path, dict(self.headers.items())))
        self.send_error(405)

    def do_PATCH(self) -> None:  # noqa: N802
        self.__class__.requests.append(("PATCH", self.path, dict(self.headers.items())))
        self.send_error(405)

    def log_message(self, *_args: object) -> None:
        return


class WifiDiagnoseCliTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeConnector.requests = []
        _FakeConnector.delay_paths = set()
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(CALLER_TOKEN + "\n")
        os.chmod(self.token_file, 0o600)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeConnector)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.set_complete_responses()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temp.cleanup()

    def set_complete_responses(self, site_ref: str = SITE_REF) -> None:
        routes = tuple(path.replace(SITE_REF, site_ref) for path in FIXED_DIAGNOSTIC_ROUTES)
        payloads = _complete_payloads(site_ref)
        timeline = payloads[FIXED_DIAGNOSTIC_ROUTES[0]]
        assert isinstance(timeline, dict)
        timeline.update({"name": PRIVATE_NAME, "ip": PRIVATE_IP})
        details = payloads[FIXED_DIAGNOSTIC_ROUTES[1]]
        assert isinstance(details, dict)
        detail_data = details.get("data")
        assert isinstance(detail_data, dict)
        rssi = detail_data.get("rssiScoreDetail")
        assert isinstance(rssi, dict)
        rssi["incidents"] = [{"id": PRIVATE_MARKER, "content": PRIVATE_NAME,
                              "clientIp": PRIVATE_IP}]
        _FakeConnector.responses = {"/v1/sites": (200, payloads["/v1/sites"], {})}
        _FakeConnector.responses.update({
            route: (200, payloads[fixture_route], {})
            for route, fixture_route in zip(routes, FIXED_DIAGNOSTIC_ROUTES, strict=True)
        })

    def run_cli(self, *extra: str, token_file: str | None = None) -> subprocess.CompletedProcess[str]:
        script = os.path.join(os.path.dirname(__file__), "..", "tools", "wifi_diagnose.py")
        return subprocess.run(
            [sys.executable, script, "--site-ref", SITE_REF,
             "--token-file", token_file or self.token_file,
             "--base-url", self.base_url, *extra],
            capture_output=True, text=True, timeout=10, check=False,
        )

    def test_uses_site_inventory_then_fixed_authenticated_gets(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            [(method, path) for method, path, _headers in _FakeConnector.requests],
            [("GET", "/v1/sites"), *(('GET', path) for path in FIXED_DIAGNOSTIC_ROUTES)],
        )
        for method, _path, headers in _FakeConnector.requests:
            self.assertEqual(method, "GET")
            self.assertEqual(headers.get("Authorization"), f"Bearer {CALLER_TOKEN}")
        report = json.loads(result.stdout)
        self.assertEqual(report["site_ref"], SITE_REF)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(set(report["results"]), set(RESULT_KEYS))
        for route_result in report["results"].values():
            self.assertEqual(route_result["status"], "ok")
            self.assertFalse(route_result["partial"])
            self.assertEqual(route_result["capability_status"], "unknown")
        rendered = result.stdout + result.stderr
        for private in (CALLER_TOKEN, PRIVATE_NAME, PRIVATE_IP, PRIVATE_MARKER):
            self.assertNotIn(private, rendered)

    def test_unknown_site_ref_stops_before_diagnostics(self) -> None:
        self.set_complete_responses(site_ref=OTHER_SITE_REF)
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            [(method, path) for method, path, _ in _FakeConnector.requests],
            [("GET", "/v1/sites")],
        )
        self.assertNotIn(OTHER_SITE_REF, result.stdout + result.stderr)
        self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

    def test_response_site_ref_mismatch_fails_only_that_diagnostic_and_marks_report_partial(self) -> None:
        payload = _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[0]][1]
        assert isinstance(payload, dict)
        payload["site_ref"] = OTHER_SITE_REF
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[0]] = (200, payload, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "partial")
        route_result = report["results"][RESULT_KEYS[0]]
        self.assertEqual(route_result["status"], "error")
        self.assertIn(route_result["error"], {"response_invalid", "response_site_mismatch"})
        self.assertEqual(route_result["capability_status"], "unknown")
        self.assertNotIn(OTHER_SITE_REF, result.stdout + result.stderr)

    def test_subhealth_missing_series_value_is_partial_instead_of_losing_the_section(self) -> None:
        from tools import wifi_diagnose

        payload = _complete_payloads()[FIXED_DIAGNOSTIC_ROUTES[1]]
        quality = payload["data"]["wirelessClientQualityDetail"]
        del quality["assocTime"][0]["pastNum"]
        payload["missing_fields"].append("wirelessClientQualityDetail.assocTime[].pastNum")
        payload["partial"] = True
        result = wifi_diagnose._route_projection("wifi_health_details", payload, SITE_REF)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["partial"])
        self.assertEqual(
            result["data"]["data"]["wirelessClientQualityDetail"]["assocTime"][0],
            {"time_ms": END_MS},
        )

    def test_invalid_site_ref_and_non_loopback_or_non_origin_urls_fail_pre_request(self) -> None:
        invalid = (
            ("--site-ref", "A" * 24),
            ("--base-url", "http://example.com"),
            ("--base-url", self.base_url + "/prefix"),
            ("--base-url", self.base_url + "?redirect=1"),
        )
        for option, value in invalid:
            with self.subTest(option=option, value=value):
                args = [sys.executable,
                        os.path.join(os.path.dirname(__file__), "..", "tools", "wifi_diagnose.py"),
                        "--site-ref", SITE_REF, "--token-file", self.token_file,
                        "--base-url", self.base_url]
                if option == "--site-ref":
                    args[args.index("--site-ref") + 1] = value
                else:
                    args[args.index("--base-url") + 1] = value
                result = subprocess.run(args, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(_FakeConnector.requests, [])
                self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

    def test_token_file_requires_private_regular_single_link_file_and_rejects_special_files(self) -> None:
        symlink_path = os.path.join(self.temp.name, "token-symlink")
        os.symlink(self.token_file, symlink_path)
        hardlink_path = os.path.join(self.temp.name, "token-hardlink")
        os.link(self.token_file, hardlink_path)
        fifo_path = os.path.join(self.temp.name, "token-fifo")
        os.mkfifo(fifo_path, 0o600)

        for candidate in (symlink_path, hardlink_path, fifo_path):
            with self.subTest(candidate=os.path.basename(candidate)):
                result = self.run_cli(token_file=candidate)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(_FakeConnector.requests, [])
                self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

        os.unlink(hardlink_path)
        os.chmod(self.token_file, 0o644)
        try:
            result = self.run_cli()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_FakeConnector.requests, [])
            self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)
        finally:
            os.chmod(self.token_file, 0o600)

    def test_redirect_is_not_followed_or_sent_caller_token_to_location(self) -> None:
        redirect_target = "/redirect-target"
        _FakeConnector.responses["/v1/sites"] = (
            302, {"error": "redirect"}, {"Location": redirect_target})
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([path for _method, path, _ in _FakeConnector.requests], ["/v1/sites"])
        self.assertNotIn(redirect_target, result.stdout + result.stderr)
        self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

    def test_site_workflow_includes_redacted_wlan_policy_context(self) -> None:
        report = self.run_cli()
        self.assertEqual(report.returncode, 0, report.stderr)
        decoded = json.loads(report.stdout)
        self.assertEqual(decoded["results"]["band_steering"]["data"]["mode"], 1)
        self.assertEqual(decoded["results"]["rrm_settings"]["data"]["resource"], 0)
        self.assertEqual(decoded["results"]["roaming_settings"]["data"]["fastRoamingEnable"], True)
        self.assertEqual([path for _method, path, _ in _FakeConnector.requests][-3:],
                         list(FIXED_DIAGNOSTIC_ROUTES[-3:]))

    def test_site_policy_failure_and_secret_bearing_malformed_data_are_isolated(self) -> None:
        route = FIXED_DIAGNOSTIC_ROUTES[9]
        _FakeConnector.responses[route] = (200, {
            "status": "ok", "resource": "rrm_settings", "site_ref": SITE_REF,
            "data": {"mode": 1, "timeRangeId": PRIVATE_MARKER}, "partial": False,
        }, {})
        report = self.run_cli()
        self.assertEqual(report.returncode, 0, report.stderr)
        decoded = json.loads(report.stdout)
        self.assertEqual(decoded["results"]["rrm_settings"]["status"], "ok")
        self.assertTrue(decoded["results"]["rrm_settings"]["partial"])
        self.assertEqual(decoded["status"], "partial")
        self.assertNotIn(PRIVATE_MARKER, report.stdout + report.stderr)
        self.assertEqual(decoded["results"]["roaming_settings"]["status"], "ok")

    def test_partial_endpoint_failure_does_not_hide_other_results_or_echo_body(self) -> None:
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[1]] = (
            502, {"error": "upstream_failure", "message": PRIVATE_MARKER}, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report["results"]), set(RESULT_KEYS))
        failed = report["results"][RESULT_KEYS[1]]
        self.assertEqual(failed.get("status"), "error")
        self.assertIsInstance(failed.get("error"), str)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(failed["capability_status"], "unknown")
        self.assertNotIn(PRIVATE_MARKER, result.stdout + result.stderr)
        self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

    def test_all_four_route_failures_return_nonzero_and_overall_error(self) -> None:
        for path in FIXED_DIAGNOSTIC_ROUTES:
            _FakeConnector.responses[path] = (502, {"message": PRIVATE_MARKER}, {})
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "error")
        self.assertEqual(set(report["results"]), set(RESULT_KEYS))
        for route_result in report["results"].values():
            self.assertEqual(route_result["status"], "error")
            self.assertEqual(route_result["capability_status"], "unknown")
        self.assertNotIn(PRIVATE_MARKER, result.stdout + result.stderr)
        self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

    def test_partial_subhealth_metadata_and_incidents_are_counted_without_private_content(self) -> None:
        raw = _raw_subhealth()
        del raw["rssiScoreDetail"]["scores"]
        raw["wirelessClientQualityDetail"]["averageDnsTime"] = "invalid-private-value"
        partial = project_wifi_subhealth(raw, START_MS, END_MS)
        partial["site_ref"] = SITE_REF
        partial["missing_fields"].append(PRIVATE_MARKER)
        partial["invalid_fields"].append(PRIVATE_NAME)
        partial["data"]["rssiScoreDetail"]["incidents"] = [{"id": PRIVATE_MARKER,
            "content": PRIVATE_NAME, "ip": PRIVATE_IP}]
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[1]] = (200, partial, {})
        result = self.run_cli()
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "partial")
        route_result = report["results"][RESULT_KEYS[1]]
        self.assertTrue(route_result["partial"])
        self.assertEqual(route_result["capability_status"], "unknown")
        metadata = route_result["data"]
        self.assertEqual(metadata["missing_field_count"], 2)
        self.assertEqual(metadata["invalid_field_count"], 2)
        self.assertIsInstance(metadata["unknown_field_count"], int)
        self.assertIsInstance(metadata["omitted_count"], int)
        rendered = result.stdout + result.stderr
        for private in (PRIVATE_MARKER, PRIVATE_NAME, PRIVATE_IP, "invalid-private-value"):
            self.assertNotIn(private, rendered)

    def test_sparse_channels_and_signal_categories_cannot_claim_complete(self) -> None:
        channels = project_site_dashboard_channels({"2g channel stat": []})
        channels.update({"site_ref": SITE_REF, "partial": False})
        signal = project_client_signal_distribution({
            "poorSignal": {"totalClients": 1},
        })
        signal.update({"site_ref": SITE_REF, "partial": False})
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[2]] = (200, channels, {})
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[3]] = (200, signal, {})
        result = self.run_cli()
        report = json.loads(result.stdout)
        for key in (RESULT_KEYS[2], RESULT_KEYS[3]):
            route_result = report["results"][key]
            self.assertTrue(route_result["partial"] or route_result["status"] == "error")
            self.assertEqual(route_result["capability_status"], "unknown")

    def test_missing_signal_metric_in_known_category_cannot_claim_complete(self) -> None:
        payload = _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[3]][1]
        assert isinstance(payload, dict)
        signal_data = payload["data"]
        assert isinstance(signal_data, dict)
        poor_signal = signal_data["poorSignal"]
        assert isinstance(poor_signal, dict)
        del poor_signal["clients5g"]
        payload["partial"] = False
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[3]] = (200, payload, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        route_result = report["results"][RESULT_KEYS[3]]
        self.assertTrue(route_result["partial"] or route_result["status"] == "error")
        self.assertEqual(route_result["capability_status"], "unknown")

    def test_health_counts_can_exceed_examined_point_cap_but_returned_count_must_match(self) -> None:
        payload = _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[0]][1]
        assert isinstance(payload, dict)
        data = payload["data"]
        assert isinstance(data, dict)
        data["counts"] = {
            "received_points": 15000, "examined_points": 10000,
            "unexamined_points": 5000, "outside_window_points": 0,
            "duplicate_timestamp_points": 0, "truncated_points": 0,
            "returned_points": 1,
            "unknown_fields": 0,
        }
        data["partial"] = True
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[0]] = (200, payload, {})
        result = self.run_cli()
        report = json.loads(result.stdout)
        route_result = report["results"][RESULT_KEYS[0]]
        self.assertEqual(route_result["status"], "ok")
        self.assertTrue(route_result["partial"])

        data["counts"]["returned_points"] = 2
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[0]] = (200, payload, {})
        mismatch = self.run_cli()
        mismatch_report = json.loads(mismatch.stdout)
        mismatch_route = mismatch_report["results"][RESULT_KEYS[0]]
        self.assertEqual(mismatch_route["status"], "error")
        self.assertEqual(mismatch_route["error"], "response_invalid")

    def test_health_partial_flag_must_match_omitted_point_counts(self) -> None:
        payload = _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[0]][1]
        assert isinstance(payload, dict)
        data = payload["data"]
        assert isinstance(data, dict)
        data["counts"].update({
            "received_points": 2, "examined_points": 2,
            "unexamined_points": 0, "outside_window_points": 1,
            "duplicate_timestamp_points": 0, "truncated_points": 0,
            "returned_points": 1, "unknown_fields": 0,
        })
        data["partial"] = False
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[0]] = (200, payload, {})
        result = self.run_cli()
        report = json.loads(result.stdout)
        route_result = report["results"][RESULT_KEYS[0]]
        self.assertTrue(route_result["partial"] or route_result["status"] == "error")

    def test_response_size_is_bounded_and_oversize_private_body_is_not_echoed(self) -> None:
        _FakeConnector.responses[FIXED_DIAGNOSTIC_ROUTES[0]] = (
            200, {"status": "ok", "blob": PRIVATE_MARKER + ("x" * (300 * 1024))}, {})
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        first = report["results"][RESULT_KEYS[0]]
        self.assertEqual(first.get("status"), "error")
        self.assertIsInstance(first.get("error"), str)
        self.assertNotIn(PRIVATE_MARKER, result.stdout + result.stderr)
        self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)

    def test_request_timeout_is_bounded_and_other_routes_still_run(self) -> None:
        _FakeConnector.delay_paths = {FIXED_DIAGNOSTIC_ROUTES[0]}
        started = time.monotonic()
        result = self.run_cli()
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 5.0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(_FakeConnector.requests), 13)
        self.assertNotIn(CALLER_TOKEN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
