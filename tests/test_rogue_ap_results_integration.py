from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class RogueApResultsIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64, page_size=10, max_pages=2))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_reads_stored_results_from_exact_route_and_redacts_identity(self) -> None:
        rows = [{"id": "secret-id", "ssid": "secret-ssid", "bssid": "secret-bssid",
                 "radioId": 0, "channel": 6, "security": 3, "mode": 1,
                 "signal": -54, "nearestApMac": "secret-ap", "nearestAp": "secret-name",
                 "lastSeen": 123456789}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as request:
            result = self.client.read_site_rogue_ap_results(self.site_ref)
        request.assert_called_once_with(
            "/openapi/v1/ctrl/sites/site_1/insight/rogueaps", "token")
        self.assertEqual(result["resource"], "site_rogue_ap_results")
        self.assertEqual(result["data_age"], "unknown_stored_scan")
        self.assertNotIn("secret", repr(result))

    def test_rejects_unknown_site_and_wrong_controller_path(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_rogue_ap_results("b" * 24)
        good = "/openapi/v1/ctrl/sites/site_1/insight/rogueaps?page=1&pageSize=10"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good, token="token")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"), token="token")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good + "&extra=1", token="token")

    def test_rejects_malformed_paged_result(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"data": []}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_rogue_ap_results(self.site_ref)


if __name__ == "__main__":
    unittest.main()
