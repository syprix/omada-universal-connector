from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class RfInterferenceReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._device_macs_by_site_ref[self.site_ref] = {self.ap_ref: "00:11:22:33:44:55"}

    def test_existing_rf_scan_results_sanitize_channel_interference(self) -> None:
        payload = {"errorCode": 0, "result": {"channel2g": [{"chan": 6, "chanWidth": 2, "util": 42,
            "inter": [{"inf": -70, "infType": 3,
                       "infData": {"str": [-91, -89], "cnt": [2, 3]},
                       "ssid": "private", "bssid": "00:11:22:33:44:66"}]}],
            "channel5g": [], "channel5g2": [], "channel6g": [], "status2g": 0,
            "time": 1800000000000, "currentChan2g": "6", "name": "private"}}
        paths = []
        def request(method, path, **kwargs):
            paths.append((method, path))
            return payload
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_ap_rf_scan(self.site_ref, self.ap_ref)
        self.assertEqual(paths, [("GET", "/openapi/v1/ctrl/sites/site_1/aps/00:11:22:33:44:55/rf-scan-result")])
        self.assertEqual(result["data"]["2g"][0]["channel"], 6)
        self.assertEqual(result["data"]["2g"][0]["utilization_percent"], 42)
        self.assertEqual(result["data"]["2g"][0]["interference"][0]["type"], "wlan")
        for forbidden in ("private", "00:11:22:33:44:55", "00:11:22:33:44:66", "currentChan", "1800000000000"):
            self.assertNotIn(forbidden, str(result))
        self.assertEqual(next(x for x in self.client.capabilities()["items"]
                              if x["operation"] == "ap_rf_scan")["runtime_evidence"][0]["result"],
                         "success")

    def test_v2_result_route_has_a_separate_fixed_reader(self) -> None:
        payload = {"errorCode": 0, "result": {"channel2g": [], "channel5g": [],
            "channel5g2": [], "channel6g": []}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_ap_rf_scan_v2(self.site_ref, self.ap_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v2/ctrl/sites/site_1/aps/00:11:22:33:44:55/rf-scan-result",
            token="token")
        self.assertEqual(result["resource"], "ap_rf_scan_v2")
        self.assertFalse(result.get("partial", False))

    def test_paged_wifi_neighbor_results_are_opaque_and_redacted(self) -> None:
        rows = [{"id": "private-id", "bssid": "00:11:22:33:44:66", "ssid": "private-ssid",
                 "radioId": 1, "channel": 44, "mode": 5, "security": 3,
                 "signal": -62, "lastSeen": 1800000000000, "bandWidth": 80}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as read:
            result = self.client.read_ap_wifi_neighbors(self.site_ref, self.ap_ref)
        read.assert_called_once_with("/openapi/v1/ctrl/sites/site_1/aps/00:11:22:33:44:55/full-channel-detect/wlan-interference", "token")
        row = result["items"][0]
        self.assertEqual((row["band"], row["channel"], row["signal_dbm"], row["bandwidth"]),
                         ("5g", 44, -62, 80))
        self.assertEqual(len(row["neighbor_ref"]), 24)
        for forbidden in ("private-id", "00:11:22:33:44:55", "00:11:22:33:44:66", "private-ssid"):
            self.assertNotIn(forbidden, str(result))
        self.assertEqual(next(x for x in self.client.capabilities()["items"]
                              if x["operation"] == "ap_wifi_interference")["runtime_evidence"][0]["result"],
                         "success")

    def test_unknown_ap_and_malformed_signal_fail_closed(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_ap_rf_scan(self.site_ref, "c" * 24)
        rows = [{"id": "id", "bssid": "00:11:22:33:44:66", "radioId": 0,
                 "channel": 1, "signal": 1, "lastSeen": 1, "bandWidth": 20}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ap_wifi_neighbors(self.site_ref, self.ap_ref)

    def test_only_fixed_existing_result_get_paths_are_allowed(self) -> None:
        paths = ["/openapi/v1/ctrl/sites/site_1/aps/00-11-22-33-44-55/rf-scan-result",
                 "/openapi/v2/ctrl/sites/site_1/aps/00-11-22-33-44-55/rf-scan-result",
                 "/openapi/v1/ctrl/sites/site_1/aps/00-11-22-33-44-55/full-channel-detect/wlan-interference?page=1&pageSize=100"]
        for path in paths:
            with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
                with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("POST", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", paths[1] + "&filter=private")


if __name__ == "__main__":
    unittest.main()
