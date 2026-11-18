from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wireless_group_capacity import (
    SiteWirelessGroupCapacityError, project_site_wireless_group_capacity,
)


class SiteWirelessGroupCapacityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site_ref = "a" * 24
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_projects_both_documented_count_field_variants(self) -> None:
        wlan = project_site_wireless_group_capacity(
            {"wlanGroupNum": 12, "exceeded": False}, "wlanGroupNum")
        ap = project_site_wireless_group_capacity(
            {"apGroupNum": 13, "exceeded": True}, "apGroupNum")
        self.assertEqual(wlan["data"]["group_count"], 12)
        self.assertFalse(wlan["data"]["limit_exceeded"])
        self.assertEqual(ap["data"]["group_count"], 13)
        self.assertTrue(ap["data"]["limit_exceeded"])
        self.assertFalse(wlan["partial"])
        self.assertFalse(ap["partial"])

    def test_invalid_and_unknown_values_are_counted_without_echoing(self) -> None:
        result = project_site_wireless_group_capacity({
            "wlanGroupNum": True, "exceeded": 1, "privateName": "not returned",
        }, "wlanGroupNum")
        self.assertEqual(result["data"]["invalid_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("not returned", repr(result))
        self.assertTrue(result["partial"])
        with self.assertRaises(SiteWirelessGroupCapacityError):
            project_site_wireless_group_capacity({}, "other")

    def test_reads_exact_site_bound_routes(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"result": {"wlanGroupNum": 2, "exceeded": False}},
                    {"result": {"apGroupNum": 3, "exceeded": True}},
                ]) as request:
            wlan = self.client.read_site_wlan_group_capacity(self.site_ref)
            ap = self.client.read_site_ap_group_capacity(self.site_ref)
        self.assertEqual(request.call_args_list[0].args[:2], (
            "GET", "/openapi/v1/ctrl/sites/site_1/wireless-network/cmd/countWlans"))
        self.assertEqual(request.call_args_list[1].args[:2], (
            "GET", "/openapi/v1/ctrl/sites/site_1/count-ap-groups"))
        self.assertEqual(wlan["resource"], "site_wlan_group_capacity")
        self.assertEqual(ap["resource"], "site_ap_group_capacity")
        with self.assertRaisesRegex(OpenApiError, "site_ref_invalid"):
            self.client.read_site_wlan_group_capacity("bad")
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_ap_group_capacity("b" * 24)

    def test_rejects_unlisted_upstream_routes(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/sites/site_1/count-ap-groups", token="token")
        path = "/openapi/v1/ctrl/sites/site_1/count-ap-groups"
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path, token="token")


if __name__ == "__main__":
    unittest.main()
