from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_isolated_preconfig_summary import (
    IsolatedPreconfigError, summarize_isolated_preconfig,
)


class IsolatedPreconfigSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_separates_documented_categories_and_redacts_device_values(self):
        result = summarize_isolated_preconfig({
            "total": 2,
            "isolated": [{"type": "switch", "mac": "private", "name": "private",
                          "healthScore": 86, "ippt": False}],
            "preconfig": [{"type": "ap", "model": "private", "ippt": True}],
        })
        self.assertEqual(result["categories"]["isolated"]["reported_count"], 1)
        self.assertEqual(result["categories"]["preconfigured"]["reported_count"], 1)
        self.assertFalse(result["partial"])
        for secret in ("private", "switch", "ap", "healthScore"):
            self.assertNotIn(secret, repr(result))

    def test_reports_total_mismatch_unknown_fields_and_partial_lists(self):
        result = summarize_isolated_preconfig({
            "total": 3, "isolated": [{"future": True}], "preconfig": []
        })
        self.assertTrue(result["partial"])
        self.assertTrue(result["total_mismatch"])
        self.assertEqual(result["unknown_field_count"], 1)
        with self.assertRaises(IsolatedPreconfigError):
            summarize_isolated_preconfig({"total": 0, "isolated": [], "preconfig": {}})

    def test_uses_fixed_site_bound_read(self):
        payload = {"result": {"total": 0, "isolated": [], "preconfig": []}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_isolated_preconfig_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v2/ctrl/sites/site_internal/topology/isolated-and-pre-config",
            token="token")
        self.assertEqual(result["reported_total"], 0)
        self.assertTrue(self.client._site_isolated_preconfig_request_valid(
            "/openapi/v2/ctrl/sites/site_internal/topology/isolated-and-pre-config"))
        self.assertFalse(self.client._site_isolated_preconfig_request_valid(
            "/openapi/v2/other/sites/site_internal/topology/isolated-and-pre-config"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_isolated_preconfig_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
