from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

from app.site_interference_scan_eligible_summary import (
    SiteInterferenceScanEligibleError,
    summarize_site_interference_scan_eligible_aps,
)


class SiteInterferenceScanEligibleSummaryTests(unittest.TestCase):
    def test_aggregates_scan_state_without_returning_identity(self):
        result = summarize_site_interference_scan_eligible_aps([
            {"mac": "AA:BB:CC:DD:EE:FF", "name": "Office AP", "model": "EAP650",
             "statusCategory": 1, "scanStatus": 0, "wirelessLinked": True,
             "powerModeList": [0, 1]},
            {"mac": "11:22:33:44:55:66", "name": "Warehouse AP", "model": "EAP650",
             "statusCategory": 0, "scanStatus": 2, "wirelessLinked": False,
             "powerModeList": [2]},
        ])
        self.assertEqual(result["data"], {
            "returned_ap_count": 2, "valid_ap_count": 2,
            "connected_ap_count": 1, "wireless_linked_ap_count": 1,
            "scan_status_counts": {"0": 1, "2": 1},
            "power_mode_counts": {"0": 1, "1": 1, "2": 1},
            "page": 1, "page_size": 500, "total_count": None,
            "total_count_known": False, "coverage_scope": "first_page_only",
            "coverage_unknown": True, "truncated": False,
        })
        self.assertNotIn("mac", str(result).lower())
        self.assertNotIn("office", str(result).lower())
        self.assertTrue(result["partial"])

    def test_unknown_missing_invalid_and_overflow_are_partial(self):
        rows = [{"scanStatus": 99, "powerModeList": [9], "future": True}]
        rows.extend({"scanStatus": 0} for _ in range(500))
        result = summarize_site_interference_scan_eligible_aps(rows)
        self.assertTrue(result["partial"])
        self.assertTrue(result["data"]["truncated"])
        self.assertEqual(result["data"]["returned_ap_count"], 501)
        self.assertEqual(result["unknown_field_count"], 3)
        missing = summarize_site_interference_scan_eligible_aps([{}])
        self.assertEqual(missing["missing_field_count"], 1)
        invalid = summarize_site_interference_scan_eligible_aps([{"scanStatus": True}])
        self.assertEqual(invalid["invalid_field_count"], 1)

    def test_full_page_keeps_unknown_coverage_separate_from_truncation(self):
        result = summarize_site_interference_scan_eligible_aps(
            [{"scanStatus": 0} for _ in range(500)])
        self.assertFalse(result["data"]["truncated"])
        self.assertTrue(result["data"]["coverage_unknown"])
        self.assertIsNone(result["data"]["total_count"])
        self.assertEqual(result["data"]["returned_ap_count"], 500)
        self.assertTrue(result["partial"])

    def test_non_list_response_is_rejected(self):
        with self.assertRaises(SiteInterferenceScanEligibleError):
            summarize_site_interference_scan_eligible_aps({"rows": []})


class SiteInterferenceScanEligibleClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "9" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_paginated_path_and_returns_aggregate(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"mac": "00-11-22-33-44-55", "name": "Private AP", "scanStatus": 0}
                ]}) as request:
            result = self.client.read_site_interference_scan_eligible_summary(
                self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/grid/full-channel-detect/ap-list"
            "?page=1&pageSize=500", token="token")
        self.assertEqual(result["data"]["scan_status_counts"], {"0": 1})
        self.assertNotIn("00-11-22-33-44-55", repr(result))
        self.assertNotIn("Private AP", repr(result))

    def test_rejects_bad_result_and_guards_fixed_path(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_interference_scan_eligible_summary(self.site_ref)
        expected = ("/openapi/v1/ctrl/sites/site_internal/grid/full-channel-detect"
                    "/ap-list?page=1&pageSize=500")
        self.assertTrue(self.client._site_interference_scan_eligible_request_valid(expected))
        self.assertFalse(self.client._site_interference_scan_eligible_request_valid(
            expected.replace("pageSize=500", "pageSize=1000")))
        self.assertFalse(self.client._site_interference_scan_eligible_request_valid(
            expected.replace("/ctrl/", "/other/")))


if __name__ == "__main__":
    unittest.main()
