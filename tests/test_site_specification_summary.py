from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_specification_summary import (
    SiteSpecificationSummaryError,
    project_site_specification_summary,
)


class SiteSpecificationProjectionTests(unittest.TestCase):
    def test_projects_the_three_documented_supported_counts(self) -> None:
        result = project_site_specification_summary({
            "interfaceNum": 16, "urlFilteringNum": 40,
            "macGroupAddressNum": 128,
        })
        self.assertEqual(result["data"], {
            "supported_interface_count": 16,
            "supported_url_filtering_count": 40,
            "supported_mac_group_address_count": 128,
        })
        self.assertFalse(result["partial"])

    def test_counts_missing_invalid_unknown_without_echoing_fields(self) -> None:
        result = project_site_specification_summary({
            "interfaceNum": True, "privateField": "sensitive-value",
        })
        self.assertEqual(result["missing_field_count"], 2)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("sensitive-value", repr(result))

    def test_rejects_wrong_or_oversized_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(13)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteSpecificationSummaryError):
                project_site_specification_summary(value)
        invalid = project_site_specification_summary({"interfaceNum": -1})
        self.assertEqual(invalid["data"]["supported_interface_count"], None)
        self.assertEqual(invalid["invalid_field_count"], 1)


class SiteSpecificationClientTests(unittest.TestCase):
    def test_reads_fixed_site_path_and_returns_only_projected_fields(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "d" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "interfaceNum": 4, "urlFilteringNum": 12,
                    "macGroupAddressNum": 80, "private": "do-not-return",
                }}) as request:
            result = client.read_site_specification_summary(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/specification",
            token="test-token")
        self.assertEqual(result["resource"], "site_specification_summary")
        self.assertEqual(result["data"]["supported_interface_count"], 4)
        self.assertNotIn("do-not-return", repr(result))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            client.read_site_specification_summary("e" * 24)

    def test_path_guard_requires_the_configured_controller(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.assertTrue(client._site_specification_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/specification"))
        self.assertFalse(client._site_specification_request_valid(
            "/openapi/v1/other/sites/site_internal/specification"))


if __name__ == "__main__":
    unittest.main()
