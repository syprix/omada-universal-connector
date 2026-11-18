from __future__ import annotations

import unittest
from unittest.mock import patch

from app.device_tag_summary import DeviceTagSummaryError, summarize_device_tags
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class DeviceTagSummaryProjectionTests(unittest.TestCase):
    def test_counts_tag_presence_without_returning_names_or_ids(self) -> None:
        result = summarize_device_tags([
            {"tagId": "private-id", "name": "private-name"},
            {"tagId": "another-id", "name": "another-name"},
        ])
        self.assertEqual(result["data"], {
            "tag_count": 2, "tag_id_present_count": 2, "tag_name_present_count": 2,
            "missing_count": 0, "invalid_count": 0, "unknown_field_count": 0,
        })
        self.assertFalse(result["partial"])
        for private in ("private-id", "private-name", "another-id", "another-name"):
            self.assertNotIn(private, repr(result))

    def test_invalid_missing_unknown_and_oversized_rows_are_reported_safely(self) -> None:
        result = summarize_device_tags([
            {"tagId": 3, "name": None, "future": "private"}, None,
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["invalid_count"], 2)
        self.assertEqual(result["data"]["missing_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        with self.assertRaises(DeviceTagSummaryError):
            summarize_device_tags([{}] * 257)
        with self.assertRaises(DeviceTagSummaryError):
            summarize_device_tags({"result": []})


class DeviceTagSummaryClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"

    def test_reads_fixed_site_route_and_returns_only_the_summary(self) -> None:
        response = {"errorCode": 0, "result": [
            {"tagId": "private-id", "name": "private-name"}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_site_device_tag_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/devices/tag", token="token")
        self.assertEqual(result["resource"], "site_device_tag_summary")
        self.assertEqual(result["data"]["tag_count"], 1)
        for private in ("private-id", "private-name"):
            self.assertNotIn(private, repr(result))

    def test_unknown_site_and_wrong_controller_are_rejected_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_device_tag_summary("b" * 24)
        request.assert_not_called()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/sites/site-1/devices/tag")


if __name__ == "__main__":
    unittest.main()
