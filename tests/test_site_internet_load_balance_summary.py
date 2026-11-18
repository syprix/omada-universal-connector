from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_internet_load_balance_summary import (
    SiteInternetLoadBalanceSummaryError, project_site_internet_load_balance,
)


class SiteInternetLoadBalanceProjectionTests(unittest.TestCase):
    def test_projects_common_flags_and_counts_without_ids_or_values(self):
        value = {
            "weights": [1, 5], "appOptRouting": True, "linkBackup": False,
            "method": "private-method", "primaryWans": ["primary-id"],
            "backupWan": "backup-id", "backupMode": 1, "mode": 2,
            "timeRangeId": "private-range", "virtualWanWeights": [
                {"virtualWanId": "virtual-id", "weight": 4,
                 "name": "private-name", "physicalWanId": "physical-id"}],
        }
        result = project_site_internet_load_balance(value)
        self.assertTrue(result["data"]["application_optimized_routing_enabled"])
        self.assertFalse(result["data"]["link_backup_enabled"])
        self.assertEqual(result["data"]["weight_count"], 2)
        self.assertEqual(result["data"]["primary_wan_count"], 1)
        self.assertEqual(result["data"]["valid_virtual_wan_count"], 1)
        self.assertEqual(result["data"]["documented_mode_code_counts"]["mode"],
                         {"0": 0, "1": 0, "2": 1})
        self.assertNotIn("private", repr(result))
        self.assertFalse(result["partial"])

    def test_reports_missing_invalid_unknown_and_bounded_arrays(self):
        result = project_site_internet_load_balance({
            "weights": [1, 0, True], "appOptRouting": "yes", "linkBackup": False,
            "mode": 9, "unexpected": "private",
            "virtualWanWeights": [{"name": "private-without-required-id"}],
        })
        self.assertTrue(result["partial"])
        self.assertGreater(result["missing_field_count"], 0)
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertGreater(result["unknown_field_count"], 0)
        too_many = project_site_internet_load_balance({
            "weights": [1] * 257, "appOptRouting": True, "linkBackup": True,
        })
        self.assertTrue(too_many["data"]["truncated"])
        self.assertTrue(too_many["partial"])
        with self.assertRaises(SiteInternetLoadBalanceSummaryError):
            project_site_internet_load_balance([])


class SiteInternetLoadBalanceClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "9" * 24
        self.client._site_ids_by_ref[self.site_ref] = "internal_site"

    def test_reads_site_bound_fixed_route_and_projects(self):
        response = {"result": {"weights": [1, 2], "appOptRouting": True,
                               "linkBackup": False}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_site_internet_load_balance_summary(self.site_ref)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v1/ctrl/sites/internal_site/internet/load-balance")
        self.assertEqual(result["data"]["weight_count"], 2)

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/internal_site/internet/load-balance"
        self.assertTrue(self.client._site_internet_load_balance_request_valid(path))
        self.assertFalse(self.client._site_internet_load_balance_request_valid(
            path.replace("/ctrl/", "/other/")))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_internet_load_balance_summary("8" * 24)


if __name__ == "__main__":
    unittest.main()
