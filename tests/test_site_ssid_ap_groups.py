from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_ssid_ap_groups import SsidApGroupsError, project_ssid_ap_groups


class SsidApGroupsProjectionTests(unittest.TestCase):
    def test_projects_group_and_radio_capacity_counts_without_identity_fields(self) -> None:
        projected = project_ssid_ap_groups({
            "apGroups": [{"id": "private-group-id", "name": "Private AP Group",
                          "apNum": 3, "remainingBinding": {"2g": 2, "5g": 1}}],
            "maxSsids2G": 8, "maxSsids5G": 16, "maxSsids6G": 8, "maxSsidsMlo": 4,
        })
        self.assertEqual(projected, {
            "unknown_field_count": 0, "group_count": 1, "access_point_count": 3,
            "remaining_binding_count": 3, "unknown_row_field_count": 0,
            "max_ssids_2g": 8, "max_ssids_5g": 16,
            "max_ssids_6g": 8, "max_ssids_mlo": 4, "partial": False,
        })
        self.assertNotIn("private-group-id", str(projected))
        self.assertNotIn("Private AP Group", str(projected))

    def test_missing_values_are_partial_and_invalid_or_unbounded_values_fail(self) -> None:
        partial = project_ssid_ap_groups({"apGroups": [{"id": "hidden", "newField": "secret"}]})
        self.assertTrue(partial["partial"])
        self.assertEqual(partial["unknown_row_field_count"], 1)
        self.assertNotIn("secret", str(partial))
        invalid = (
            {"apGroups": [{"apNum": True}]},
            {"apGroups": [{"apNum": -1}]},
            {"apGroups": [{"remainingBinding": {"2g": -1}}]},
            {"apGroups": [{}] * 129},
            {"maxSsids5G": "16"},
        )
        for source in invalid:
            with self.subTest(source=source):
                with self.assertRaises(SsidApGroupsError):
                    project_ssid_ap_groups(source)


class SsidApGroupsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.ssid_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._ssid_ids_by_site_ref[self.site_ref] = {self.ssid_ref: "ssid_1"}

    def test_uses_inventory_bound_ssid_and_redacts_response(self) -> None:
        paths = []
        def request(method, path, **kwargs):
            paths.append((method, path))
            return {"result": {"apGroups": [{"id": "hidden-id", "name": "Hidden Group",
                "apNum": 2, "remainingBinding": {"2g": 4}}],
                "maxSsids2G": 8, "maxSsids5G": 16, "maxSsids6G": 8, "maxSsidsMlo": 4}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_ssid_ap_groups(self.site_ref, self.ssid_ref)
        self.assertEqual(paths, [("GET", "/openapi/v1/ctrl/sites/site_1/wireless-network/ssids/ssid_1/ap-groups")])
        self.assertEqual(result["data"]["group_count"], 1)
        self.assertNotIn("hidden-id", str(result))
        self.assertNotIn("Hidden Group", str(result))
        self.assertNotIn("ssid_1", str(result))

    def test_unknown_site_or_ssid_is_rejected_before_upstream(self) -> None:
        request = Mock()
        with patch.object(self.client, "_request_json", request):
            for site, ssid, code in (("c" * 24, self.ssid_ref, "site_ref_unknown"),
                                     (self.site_ref, "d" * 24, "ssid_ref_unknown")):
                with self.subTest(site=site, ssid=ssid):
                    with self.assertRaisesRegex(OpenApiError, code):
                        self.client.read_ssid_ap_groups(site, ssid)
            request.assert_not_called()

    def test_allowlist_accepts_only_fixed_get(self) -> None:
        path = "/openapi/v1/ctrl/sites/site_1/wireless-network/ssids/ssid_1/ap-groups"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("DELETE", path)


if __name__ == "__main__":
    unittest.main()
