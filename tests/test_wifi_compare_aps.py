from __future__ import annotations

import unittest

from tests.test_wifi_diagnose_ap import (
    AP_REF, OTHER_AP_REF, SITE_REF, _ap_health_payload, _ap_lan_traffic_payload,
    _ap_radio_config_payload, _ap_rf_scan_payload, _ap_wifi_neighbors_payload, _device,
)
from tools.wifi_diagnose import CliError, compare_aps


class WifiCompareApsTests(unittest.TestCase):
    def setUp(self) -> None:
        second_health = _ap_health_payload(device_ref=OTHER_AP_REF)
        second_health["data"]["score"] = 74
        self.calls: list[str] = []
        self.responses: dict[str, object] = {
            "/v1/sites": {"status": "ok", "resource": "sites", "items": [
                {"site_ref": SITE_REF}], "count": 1},
            f"/v1/sites/{SITE_REF}/devices": {
                "status": "ok", "resource": "devices", "count": 2,
                "items": [_device(AP_REF), _device(OTHER_AP_REF)]},
        }
        for ap_ref, health in ((AP_REF, _ap_health_payload()),
                               (OTHER_AP_REF, second_health)):
            base = f"/v1/sites/{SITE_REF}/aps/{ap_ref}"
            self.responses[base + "/health"] = health
            self.responses[base + "/radio-config"] = {
                **_ap_radio_config_payload(), "site_ref": SITE_REF,
                "device_ref": ap_ref}
            self.responses[base + "/rf-scan"] = {
                **_ap_rf_scan_payload(), "site_ref": SITE_REF,
                "device_ref": ap_ref}
            self.responses[base + "/wifi-neighbors"] = _ap_wifi_neighbors_payload(
                site_ref=SITE_REF, device_ref=ap_ref)
            self.responses[base + "/lan-traffic"] = _ap_lan_traffic_payload(
                site_ref=SITE_REF, device_ref=ap_ref)

    def request(self, path: str) -> object:
        self.calls.append(path)
        return self.responses[path]

    def test_comparison_uses_bounded_reads_and_returns_compact_side_by_side_values(self) -> None:
        result = compare_aps(SITE_REF, [AP_REF, OTHER_AP_REF], requester=self.request)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["count"], 2)
        self.assertEqual([item["ap_ref"] for item in result["items"]], [AP_REF, OTHER_AP_REF])
        first, second = result["items"]
        self.assertEqual(first["health"]["data"]["score"], 82)
        self.assertEqual(second["health"]["data"]["score"], 74)
        self.assertNotIn("values", repr(result))
        self.assertEqual(first["radio"]["data"]["bands"]["2g"], {
            "channel": 6, "channelWidth": 20, "txPower": 17, "radioEnable": True})
        self.assertEqual(first["rf_scan"]["data"]["bands"]["2g"], {
            "channel_count": 0, "max_utilization_percent": None})
        self.assertEqual(first["wifi_neighbors"]["data"]["by_band"]["5g"], {
            "count": 1, "channels": {"44": 1}, "strongest_signal_dbm": -62})
        self.assertNotIn("neighbor_ref", repr(result))
        self.assertEqual(len(self.calls), 12)
        self.assertEqual(self.calls[:2], ["/v1/sites", f"/v1/sites/{SITE_REF}/devices"])

    def test_rejects_invalid_or_duplicate_ap_references(self) -> None:
        for refs in ([AP_REF], [AP_REF, AP_REF], [AP_REF, "../bad"], "bad"):
            with self.subTest(refs=refs), self.assertRaises(CliError):
                compare_aps(SITE_REF, refs, requester=self.request)

    def test_rejects_ap_outside_the_selected_site(self) -> None:
        with self.assertRaisesRegex(CliError, "ap_ref_unknown"):
            compare_aps(SITE_REF, [AP_REF, "d" * 24], requester=self.request)

    def test_neighbor_failure_is_isolated_from_other_ap_measurements(self) -> None:
        self.responses[f"/v1/sites/{SITE_REF}/aps/{AP_REF}/wifi-neighbors"] = {
            "status": "error", "resource": "ap_wifi_neighbors",
            "error": "connector_http_error"}
        result = compare_aps(SITE_REF, [AP_REF, OTHER_AP_REF], requester=self.request)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["items"][0]["wifi_neighbors"]["status"], "error")
        self.assertEqual(result["items"][0]["lan_traffic"]["status"], "ok")
        self.assertEqual(result["items"][1]["wifi_neighbors"]["status"], "ok")

    def test_neighbor_upstream_error_keeps_only_numeric_diagnostics(self) -> None:
        def request(path: str) -> object:
            if path == f"/v1/sites/{SITE_REF}/aps/{AP_REF}/wifi-neighbors":
                raise CliError("openapi_rejected", upstream_http_status=200,
                               upstream_error_code=-39386)
            return self.request(path)

        result = compare_aps(SITE_REF, [AP_REF, OTHER_AP_REF], requester=request)
        error = result["items"][0]["wifi_neighbors"]
        self.assertEqual(error, {
            "status": "error", "error": "openapi_rejected",
            "capability_status": "unknown", "upstream_http_status": 200,
            "upstream_error_code": -39386,
        })
        self.assertEqual(result["items"][0]["lan_traffic"]["status"], "ok")
        self.assertEqual(result["items"][1]["wifi_neighbors"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
