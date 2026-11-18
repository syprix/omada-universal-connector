from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_dhcp_snooping_status import (
    SiteDhcpSnoopingStatusError, project_site_dhcp_snooping_status)


class SiteDhcpSnoopingStatusProjectionTests(unittest.TestCase):
    def test_projects_only_documented_enable_flag(self):
        self.assertEqual(project_site_dhcp_snooping_status({"dhcpSnoopEnable": True}), {
            "data": {"dhcp_snooping_enabled": True}, "missing_field_count": 0,
            "invalid_field_count": 0, "unknown_field_count": 0, "partial": False})

    def test_missing_invalid_unknown_and_oversized_values(self):
        missing = project_site_dhcp_snooping_status({})
        self.assertIsNone(missing["data"]["dhcp_snooping_enabled"])
        self.assertTrue(missing["partial"])
        invalid = project_site_dhcp_snooping_status({"dhcpSnoopEnable": 1})
        self.assertGreater(invalid["invalid_field_count"], 0)
        unknown = project_site_dhcp_snooping_status({"dhcpSnoopEnable": False,
                                                      "privateName": "secret"})
        self.assertGreater(unknown["unknown_field_count"], 0)
        self.assertNotIn("secret", repr(unknown))
        with self.assertRaises(SiteDhcpSnoopingStatusError):
            project_site_dhcp_snooping_status({str(i): i for i in range(17)})


class SiteDhcpSnoopingStatusClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_status_path(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json",
                             return_value={"result": {"dhcpSnoopEnable": True}}) as request:
            result = self.client.read_site_dhcp_snooping_status(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/dhcpSnoops/status", token="token")
        self.assertTrue(result["data"]["dhcp_snooping_enabled"])

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/site_internal/dhcpSnoops/status"
        self.assertTrue(self.client._site_dhcp_snoop_status_request_valid(path))
        self.assertFalse(self.client._site_dhcp_snoop_status_request_valid(
            path.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_dhcp_snoop_status_request_valid(path + "?page=1"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_dhcp_snooping_status("7" * 24)


if __name__ == "__main__":
    unittest.main()
