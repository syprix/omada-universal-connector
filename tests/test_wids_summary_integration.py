import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class WidsSummaryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_reads_one_bounded_page_from_exact_documented_route(self) -> None:
        page = {"totalRows": 1002, "currentPage": 1, "currentSize": 1000,
                "data": [{"stationMac": "private", "level": 0, "type": 22,
                          "band": 2, "channel": 149}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": page}) as request:
            result = self.client.read_site_wids_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/insight/wids?page=1&pageSize=1000",
            token="token")
        self.assertEqual(result["resource"], "site_wids_summary")
        self.assertEqual(result["total_rows"], 1002)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_rejects_unknown_site_malformed_page_and_unapproved_query(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_wids_summary("b" * 24)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"data": []}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_wids_summary(self.site_ref)
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json(
                    "GET", "/openapi/v1/ctrl/sites/site_1/insight/wids?page=1&pageSize=1000",
                    token="token")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/ctrl/sites/site_1/insight/wids?page=2&pageSize=1000",
                token="token")

    def test_blacklist_read_uses_fixed_page_and_redacts_identity_and_timestamp(self) -> None:
        page = {"totalRows": 2, "currentPage": 1, "currentSize": 1000,
                "data": [{"stationMac": "station-private", "detectMac": "ap-private",
                          "timeStamp": 1800000000000}]}
        path = ("/openapi/v1/ctrl/sites/site_1/insight/wids/blacklist"
                "?page=1&pageSize=1000")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": page}) as request:
            result = self.client.read_site_wids_blacklist_summary(self.site_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "site_wids_blacklist_summary")
        self.assertNotIn("station-private", repr(result))
        self.assertNotIn("ap-private", repr(result))
        self.assertNotIn("1800000000000", repr(result))
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", path.replace("page=1", "page=2"), token="token")


if __name__ == "__main__":
    unittest.main()
