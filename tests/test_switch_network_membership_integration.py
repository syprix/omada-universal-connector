import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SwitchNetworkMembershipIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=10, max_pages=2,
        ))
        self.client._site_ids_by_ref["a" * 24] = "site-id"
        self.client._switch_macs_by_site_ref["a" * 24] = {"b" * 24: "aa:bb:cc:dd:ee:ff"}

    def test_vlan_read_includes_redacted_membership_summary(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
             patch.object(self.client, "_read_pages", return_value=[{
                 "id": "network_1", "name": "hidden", "vlan": 30, "isolation": False,
                 "portLagNetworkInfo": {
                     "vlan": 30,
                     "nativePorts": [1], "nativeStPorts": [], "nativeLags": [],
                     "tagPorts": [2], "tagStPorts": [], "tagLags": [],
                     "untagPorts": [], "untagStPorts": [], "untagLags": [],
                 },
             }]) as read_pages:
            result = self.client.read_switch_vlans("a" * 24, "b" * 24)
        read_pages.assert_called_once_with(
            "/openapi/v1/ctrl/sites/site-id/switches/aa:bb:cc:dd:ee:ff/networks-detail",
            "token",
        )
        self.assertEqual(result["resource"], "switch_vlans")
        self.assertEqual(result["switch_ref"], "b" * 24)
        self.assertEqual(result["membership_summary"]["memberships"]["native"]["ports"], 1)
        self.assertEqual(result["membership_summary"]["memberships"]["tagged"]["ports"], 1)
        self.assertNotIn("hidden", repr(result))

    def test_rejects_bad_projected_response(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
             patch.object(self.client, "_read_pages", return_value={}):
            with self.assertRaises(OpenApiError):
                self.client.read_switch_vlans("a" * 24, "b" * 24)


if __name__ == "__main__":
    unittest.main()
