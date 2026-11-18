from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wlan_group_detail_summary import (
    SiteWlanGroupDetailError, project_site_wlan_group_detail,
)


class SiteWlanGroupDetailProjectionTests(unittest.TestCase):
    def test_preserves_name_and_documented_flags_but_omits_identifiers(self) -> None:
        result = project_site_wlan_group_detail({
            "id": "private-id", "wlanId": "legacy-id", "name": "Office",
            "primary": True, "clone": False, "cloneWlanId": "clone-id",
            "site": "site-id", "resource": 2,
        })
        self.assertEqual(result["data"], {
            "name": "Office", "primary": True, "clone": False, "resource": 2})
        self.assertFalse(result["partial"])
        for value in ("private-id", "legacy-id", "clone-id", "site-id"):
            self.assertNotIn(value, repr(result))

    def test_invalid_types_ranges_and_unknown_fields_mark_partial(self) -> None:
        result = project_site_wlan_group_detail({
            "name": "bad\nname", "primary": 1, "resource": 3,
            "site": 4, "future": "private",
        })
        self.assertEqual(result["invalid_field_count"], 4)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(17)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteWlanGroupDetailError):
                project_site_wlan_group_detail(value)


class SiteWlanGroupDetailClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "5" * 24
        self.group_ref = "6" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"
        self.client._wlan_group_ids_by_site_ref[self.site_ref] = {
            self.group_ref: "private_wlan_id"}

    def test_uses_fixed_v2_path_and_current_opaque_group_reference(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "id": "private_wlan_id", "name": "Office", "primary": True,
                    "resource": 0}}) as request:
            result = self.client.read_site_wlan_group_detail_summary(
                self.site_ref, self.group_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v2/ctrl/sites/site_internal/wireless-network/wlans/private_wlan_id",
            token="token")
        self.assertEqual(result["data"]["name"], "Office")
        self.assertNotIn("private_wlan_id", repr(result))

    def test_rejects_unknown_group_ref_and_binds_controller(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "wlan_group_ref_unknown"):
            self.client.read_site_wlan_group_detail_summary(self.site_ref, "7" * 24)
        self.assertTrue(self.client._site_wlan_group_detail_request_valid(
            "/openapi/v2/ctrl/sites/site_internal/wireless-network/wlans/wlan-id"))
        self.assertFalse(self.client._site_wlan_group_detail_request_valid(
            "/openapi/v2/other/sites/site_internal/wireless-network/wlans/wlan-id"))


if __name__ == "__main__":
    unittest.main()
