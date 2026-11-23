from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_lan_client_inventory_summary import (
    LanClientInventoryError, summarize_lan_client_pages,
)


class LanClientInventorySummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_summary_redacts_names_and_mac_and_reports_pagination(self):
        page = {"totalRows": 2, "currentPage": 1, "currentSize": 2,
                "data": [{"mac": "aa:bb", "name": "private", "type": "pc"},
                         {"mac": "cc:dd", "name": "private2", "type": "tv"}]}
        result = summarize_lan_client_pages([page])
        self.assertEqual(result["inventory_total_count"], 2)
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["type_field_counts"]["reported"], 2)
        for secret in ("aa:bb", "private", "pc", "tv"):
            self.assertNotIn(secret, repr(result))

    def test_partial_on_unknown_missing_and_truncated_rows(self):
        result = summarize_lan_client_pages([{
            "totalRows": 2, "currentPage": 1, "currentSize": 1,
            "data": [{"mac": "private", "newField": "private"}],
        }])
        self.assertTrue(result["partial"])
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["type_field_counts"]["unreported"], 1)
        with self.assertRaises(LanClientInventoryError):
            summarize_lan_client_pages([{"data": []}])

    def test_reads_bounded_pages_with_site_binding(self):
        payload = {"result": {"totalRows": 2, "currentPage": 1,
                              "currentSize": 2, "data": [
                                  {"mac": "private", "name": "private", "type": "pc"},
                                  {"mac": "private2", "name": "private2", "type": "tv"}]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_lan_client_inventory_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/networks/client?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["inventory_total_count"], 2)
        self.assertNotIn("private", repr(result))
        self.assertTrue(self.client._site_lan_client_inventory_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/networks/client?page=1&pageSize=100"))
        self.assertFalse(self.client._site_lan_client_inventory_request_valid(
            "/openapi/v1/other/sites/site_internal/networks/client?page=1&pageSize=100"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_lan_client_inventory_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
