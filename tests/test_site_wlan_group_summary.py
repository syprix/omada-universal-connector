from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wlan_group_summary import SiteWlanGroupSummaryError, project_site_wlan_groups


class SiteWlanGroupProjectionTests(unittest.TestCase):
    def test_counts_flags_and_resource_codes_without_group_identities(self):
        result = project_site_wlan_groups([
            {"id": "private-id-1", "wlanId": "legacy-id", "name": "private-name",
             "site": "private-site", "primary": True, "clone": False, "resource": 0},
            {"id": "private-id-2", "name": "another-private-name",
             "primary": False, "clone": True, "resource": 2},
        ])
        data = result["data"]
        self.assertEqual(data["reported_group_count"], 2)
        self.assertEqual(data["primary_group_flag_counts"], {
            "enabled_count": 1, "disabled_count": 1, "unreported_count": 0})
        self.assertEqual(data["clone_flag_counts"], {
            "enabled_count": 1, "disabled_count": 1, "unreported_count": 0})
        self.assertEqual(data["resource_code_counts"], {"0": 1, "1": 0, "2": 1})
        self.assertNotIn("private", repr(result))
        self.assertFalse(result["partial"])

    def test_optional_fields_unknown_values_and_truncation(self):
        result = project_site_wlan_groups([
            {"primary": "yes", "clone": False, "resource": 9, "unknown": "private"},
            {},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["primary_group_flag_counts"]["unreported_count"], 2)
        self.assertEqual(result["data"]["unknown_resource_code_count"], 1)
        truncated = project_site_wlan_groups([{}] * 501)
        self.assertTrue(truncated["data"]["truncated"])
        self.assertEqual(truncated["data"]["valid_group_record_count"], 500)
        with self.assertRaises(SiteWlanGroupSummaryError):
            project_site_wlan_groups({})


class SiteWlanGroupClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "c" * 24
        self.client._site_ids_by_ref[self.site_ref] = "internal_site"

    def test_reads_site_bound_wlan_group_list(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json",
                             return_value={"result": [{"primary": True, "clone": False,
                                                       "resource": 1}]}) as request:
            result = self.client.read_site_wlan_group_summary(self.site_ref)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v1/ctrl/sites/internal_site/wireless-network/wlans")
        self.assertEqual(result["data"]["reported_group_count"], 1)

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/internal_site/wireless-network/wlans"
        self.assertTrue(self.client._site_wlan_group_request_valid(path))
        self.assertFalse(self.client._site_wlan_group_request_valid(
            path.replace("/ctrl/", "/other/")))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_wlan_group_summary("d" * 24)


if __name__ == "__main__":
    unittest.main()
