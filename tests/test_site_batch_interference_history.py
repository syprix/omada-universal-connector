from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_batch_interference_history import (
    PAGE_SIZE, SiteBatchInterferenceHistoryError,
    project_site_batch_interference_history,
)


SITE = "a" * 24


def _history_result() -> dict[str, object]:
    return {
        "totalRows": 2,
        "currentPage": 1,
        "currentSize": 100,
        "data": [
            {
                "historyId": "private-history-id-1",
                "lastSeen": 1_800_000_000_000,
                "scanApNum": 4,
                "status": 1,
                "enableInterference": True,
                "deviceInfoList": [{"name": "private-ap", "mac": "00:11:22:33:44:55"}],
            },
            {
                "historyId": "private-history-id-2",
                "lastSeen": 1_800_000_000_100,
                "scanApNum": 3,
                "status": 0,
                "enableInterference": False,
                "deviceInfoList": [],
            },
        ],
    }


class SiteBatchInterferenceHistoryTests(unittest.TestCase):
    def test_projects_documented_status_and_counts_without_history_or_ap_identity(self) -> None:
        projected = project_site_batch_interference_history(_history_result())
        data = projected["data"]
        self.assertEqual(data["history_count"], 2)
        self.assertEqual(data["reported_total_rows"], 2)
        self.assertEqual(data["scanning_count"], 1)
        self.assertEqual(data["finished_count"], 1)
        self.assertEqual(data["unknown_status_count"], 0)
        self.assertEqual(data["interference_enabled_count"], 1)
        self.assertEqual(data["interference_disabled_count"], 1)
        self.assertEqual(data["scanned_ap_count_total"], 7)
        self.assertFalse(data["partial"])
        for private in ("private-history-id", "private-ap", "00:11:22:33:44:55", "lastSeen"):
            self.assertNotIn(private, repr(projected))

    def test_marks_missing_or_unknown_documented_fields_partial(self) -> None:
        projected = project_site_batch_interference_history({
            "totalRows": 1, "currentPage": 1, "currentSize": PAGE_SIZE,
            "data": [{"historyId": "opaque", "status": 7, "extraField": "discard"}],
        })["data"]
        self.assertEqual(projected["unknown_status_count"], 1)
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertGreater(projected["missing_count"], 0)
        self.assertTrue(projected["partial"])
        self.assertNotIn("discard", repr(projected))

    def test_rejects_wrong_envelope_fields_page_overflow_and_bad_scalars(self) -> None:
        with self.assertRaises(SiteBatchInterferenceHistoryError):
            project_site_batch_interference_history([])
        unknown = project_site_batch_interference_history(
            {"data": [], "controllerId": "private"})["data"]
        self.assertEqual(unknown["unknown_field_count"], 1)
        self.assertTrue(unknown["partial"])
        empty = project_site_batch_interference_history(None)["data"]
        self.assertEqual(empty["history_count"], 0)
        self.assertTrue(empty["partial"])
        with self.assertRaises(SiteBatchInterferenceHistoryError):
            project_site_batch_interference_history({"data": [{} for _ in range(PAGE_SIZE + 1)]})
        with self.assertRaises(SiteBatchInterferenceHistoryError):
            project_site_batch_interference_history({
                "totalRows": True, "currentPage": 1, "currentSize": 100, "data": [],
            })

    def test_client_uses_only_the_fixed_first_page_and_selected_site(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        response = {"errorCode": 0, "result": _history_result()}
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_site_batch_interference_history(SITE)
        self.assertEqual(result["resource"], "site_batch_interference_history")
        request.assert_called_once_with(
            "GET",
            "/openapi/v1/controller/sites/site-id/full-channel-detect/grid/scan-history"
            "?page=1&pageSize=100",
            token="fixture",
        )
        self.assertTrue(client._site_batch_interference_history_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/grid/scan-history"
            "?page=1&pageSize=100"))
        self.assertFalse(client._site_batch_interference_history_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/grid/scan-history"
            "?page=2&pageSize=100"))

    def test_issues_scoped_history_refs_and_reads_one_history_ap_summary(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={"result": _history_result()}):
            history = client.read_site_batch_interference_history(SITE)
        refs = history["data"]["history_refs"]
        self.assertEqual(len(refs), 2)
        self.assertTrue(all(len(ref) == 24 for ref in refs))
        self.assertNotIn("private-history-id-1", repr(history))
        self.assertNotIn("private-history-id-2", repr(history))

        ap_result = {"scanApNum": 1, "deviceInfoList": [{
            "mac": "00:11:22:33:44:55", "name": "private-ap", "hasResult": True,
            "support2g": True, "support5g": False, "supportWifiInterf": True,
        }]}
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={"result": ap_result}) as request:
            result = client.read_site_batch_interference_ap_summary(SITE, refs[0])
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller/sites/site-id/full-channel-detect/"
            "private-history-id-1/ap-list", token="fixture")
        self.assertEqual(result["data"]["reported_scan_ap_count"], 1)
        self.assertNotIn("private-history-id-1", repr(result))
        self.assertNotIn("00:11:22:33:44:55", repr(result))
        self.assertNotIn("private-ap", repr(result))
        device_refs = result["data"]["device_refs"]
        self.assertEqual(len(device_refs), 1)
        self.assertRegex(device_refs[0], r"^[0-9a-f]{24}$")

        channel_result = [{"channelLoads2g": [{"channel": 1, "load": 8}],
                           "channelLoads5g": [], "channelLoads6g": []}]
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={
                    "result": channel_result}) as channel_request:
            loads = client.read_site_batch_channel_load_summary(
                SITE, refs[0], device_refs[0])
        channel_request.assert_called_once()
        self.assertEqual(loads["data"]["bands"]["2g"]["average_load"], 8.0)
        for secret in ("00:11:22:33:44:55", "private-ap"):
            self.assertNotIn(secret, repr(loads))

    def test_history_ap_read_requires_a_ref_from_the_same_site(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "history_ref_unknown"):
                client.read_site_batch_interference_ap_summary(SITE, "b" * 24)
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_batch_interference_ap_summary("c" * 24, "b" * 24)
        request.assert_not_called()

    def test_wifi_interference_read_uses_fixed_all_device_filter_and_history_ref(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={"result": _history_result()}):
            history = client.read_site_batch_interference_history(SITE)
        history_ref = history["data"]["history_refs"][0]
        page = {"totalRows": 1, "currentPage": 1, "currentSize": 100,
                "data": [{"ssid": "private-network", "bssid": "00:11:22:33:44:55",
                          "radioId": 0, "channel": 6, "security": 3, "signal": -60}]}
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={"result": page}) as request:
            result = client.read_site_batch_wifi_interference_summary(SITE, history_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller/sites/site-id/full-channel-detect/"
            "private-history-id-1/grid/wifi-interference"
            "?page=1&pageSize=100&filters.type=0", token="fixture")
        self.assertFalse(result["partial"])
        self.assertNotIn("private-network", repr(result))
        self.assertNotIn("00:11:22:33:44:55", repr(result))
        self.assertTrue(client._site_batch_wifi_interference_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/private-history-id-1/"
            "grid/wifi-interference?page=1&pageSize=100&filters.type=0"))
        self.assertFalse(client._site_batch_wifi_interference_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/private-history-id-1/"
            "grid/wifi-interference?page=2&pageSize=100&filters.type=0"))

    def test_channel_load_read_resolves_opaque_ap_ref_and_returns_aggregate_only(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        client._batch_interference_history_ids_by_site_ref[SITE] = {"b" * 24: "history/one"}
        client._batch_interference_device_macs_by_site_history_ref[SITE] = {
            "b" * 24: {"c" * 24: "00:11:22:33:44:55"}}
        payload = [{"channelLoads2g": [{"channel": 1, "load": 8}],
                    "channelLoads5g": [], "channelLoads6g": []}]
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as request:
            result = client.read_site_batch_channel_load_summary(
                SITE, "b" * 24, "c" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller/sites/site-id/full-channel-detect/history%2Fone/"
            "channel-load?mac=00%3A11%3A22%3A33%3A44%3A55", token="fixture")
        self.assertEqual(result["data"]["bands"]["2g"]["average_load"], 8.0)
        self.assertNotIn("00:11:22:33:44:55", repr(result))
        with patch.object(client, "_request_json") as denied:
            with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                client.read_site_batch_channel_load_summary(SITE, "b" * 24, "d" * 24)
        denied.assert_not_called()
        self.assertTrue(client._site_batch_channel_load_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/history%2Fone/"
            "channel-load?mac=00%3A11%3A22%3A33%3A44%3A55"))
        self.assertFalse(client._site_batch_channel_load_request_valid(
            "/openapi/v1/other/sites/site-id/full-channel-detect/history/channel-load?mac=00-11-22-33-44-55"))

    def test_interference_result_read_uses_site_history_ref_and_fixed_first_page(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        client._batch_interference_history_ids_by_site_ref[SITE] = {"b" * 24: "history/one"}
        payload = [{"interferences2g": [{}], "interferences5g": [], "interferences6g": []}]
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as request:
            result = client.read_site_batch_interference_result_summary(SITE, "b" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller/sites/site-id/full-channel-detect/history%2Fone/"
            "grid/interference?page=1&pageSize=100", token="fixture")
        self.assertEqual(result["data"]["band_entry_counts"]["2g"], 1)
        self.assertTrue(result["partial"])
        self.assertTrue(client._site_batch_interference_result_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/history%2Fone/"
            "grid/interference?page=1&pageSize=100"))
        self.assertFalse(client._site_batch_interference_result_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/history/"
            "grid/interference?page=2&pageSize=100"))

    def test_interference_status_posts_only_selected_history_id(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        client._batch_interference_history_ids_by_site_ref[SITE] = {"b" * 24: "history-id-1"}
        payload = [{"historyId": "history-id-1", "status": 0}]
        body = b'{"idList":["history-id-1"]}'
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as request:
            result = client.read_site_batch_interference_status_summary(SITE, "b" * 24)
        request.assert_called_once_with(
            "POST", "/openapi/v1/controller/sites/site-id/full-channel-detect/status",
            body=body, token="fixture")
        self.assertEqual(result["data"]["items"], [{"status": "finished"}])
        self.assertNotIn("history-id-1", repr(result))
        self.assertTrue(client._site_batch_interference_status_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/status", body))
        self.assertFalse(client._site_batch_interference_status_request_valid(
            "/openapi/v1/other/sites/site-id/full-channel-detect/status", body))
        self.assertFalse(client._site_batch_interference_status_request_valid(
            "/openapi/v1/controller/sites/site-id/full-channel-detect/status",
            b'{"idList":["one","two"]}'))

    def test_ap_full_channel_detect_status_uses_inventory_ref_and_fixed_route(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        client._device_macs_by_site_ref[SITE] = {"c" * 24: "00:11:22:33:44:55"}
        payload = {"status": 3, "wifiInterfStatus": 1, "interfStatus": 0,
                   "channelLoadStatus": 0, "lastSeen": 123456, "fromGlobal": False}
        with patch.object(client, "_access_token", return_value="fixture"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as request:
            result = client.read_ap_full_channel_detect_status(SITE, "c" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller/sites/site-id/aps/00:11:22:33:44:55/"
            "full-channel-detect/status", token="fixture")
        self.assertEqual(result["data"]["statuses"]["full_channel_detection"], "scanning")
        self.assertNotIn("00:11:22:33:44:55", repr(result))
        with patch.object(client, "_request_json") as denied:
            with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                client.read_ap_full_channel_detect_status(SITE, "d" * 24)
        denied.assert_not_called()

    def test_bad_or_unknown_site_is_rejected_before_controller_call(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "client", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_invalid"):
                client.read_site_batch_interference_history("../site")
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_batch_interference_history(SITE)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
