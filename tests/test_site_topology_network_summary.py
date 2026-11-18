from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_topology_network_summary import (
    TopologyNetworkSummaryError, project_topology_network_summary,
)


class TopologyNetworkSummaryProjectionTests(unittest.TestCase):
    def test_projects_counts_and_omits_identity_and_vlan_values(self) -> None:
        projected = project_topology_network_summary({
            "splitNetworks": [{"id": "secret-network-id", "name": "Private LAN",
                "vlanId": 123, "defaultNetwork": True, "configuring": False}],
            "ssids": [{"id": "secret-ssid-id", "name": "Private WLAN",
                "wlanName": "Private WLAN", "vlanEnable": True, "vlanIds": [123, 124],
                "configuring": False, "clientNum": 7}],
        })
        self.assertEqual(projected, {
            "unknown_field_count": 0, "split_network_count": 1,
            "default_network_count": 1, "configuring_network_count": 0,
            "unknown_network_field_count": 0, "ssid_count": 1,
            "ssid_vlan_enabled_count": 1, "ssid_configuring_count": 0,
            "ssid_client_count_sum": 7, "ssid_vlan_id_count": 2,
            "unknown_ssid_field_count": 0, "partial": False,
        })
        for private_value in ("secret-network-id", "Private LAN", "secret-ssid-id",
                              "Private WLAN", "123", "124"):
            self.assertNotIn(private_value, str(projected))

    def test_missing_and_unknown_fields_mark_partial_and_invalid_values_fail(self) -> None:
        partial = project_topology_network_summary({
            "splitNetworks": [{"name": "hidden", "newField": "secret"}],
            "ssids": [{"name": "hidden", "future": "secret"}],
            "newTopLevel": "secret",
        })
        self.assertTrue(partial["partial"])
        self.assertEqual(partial["unknown_field_count"], 1)
        self.assertEqual(partial["unknown_network_field_count"], 1)
        self.assertEqual(partial["unknown_ssid_field_count"], 1)
        self.assertIsNone(partial["default_network_count"])
        self.assertIsNone(partial["configuring_network_count"])
        self.assertIsNone(partial["ssid_vlan_enabled_count"])
        self.assertIsNone(partial["ssid_configuring_count"])
        self.assertIsNone(partial["ssid_client_count_sum"])
        self.assertIsNone(partial["ssid_vlan_id_count"])
        self.assertNotIn("secret", str(partial))
        for source in (
            {"splitNetworks": [{"vlanId": True}]},
            {"splitNetworks": [{"defaultNetwork": 1}]},
            {"ssids": [{"clientNum": -1}]},
            {"ssids": [{"vlanIds": [2**31]}]},
            {"ssids": [{"clientNum": 2**31 - 1}, {"clientNum": 1}]},
            {"splitNetworks": [{}] * 257},
            {"ssids": [{}] * 257},
        ):
            with self.subTest(source=source):
                with self.assertRaises(TopologyNetworkSummaryError):
                    project_topology_network_summary(source)


class TopologyNetworkSummaryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_uses_fixed_route_and_redacts_upstream_response(self) -> None:
        calls = []
        def request(method, path, **kwargs):
            calls.append((method, path))
            return {"result": {"splitNetworks": [{"id": "hidden", "name": "Hidden LAN",
                "vlanId": 12, "defaultNetwork": True, "configuring": False}], "ssids": []}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_site_topology_network_summary(self.site_ref)
        self.assertEqual(calls, [("GET", "/openapi/v2/ctrl/sites/site_1/topology/available-network")])
        self.assertEqual(result["data"]["default_network_count"], 1)
        self.assertNotIn("hidden", str(result))
        self.assertNotIn("Hidden LAN", str(result))
        self.assertNotIn("12", str(result))

    def test_unknown_site_and_non_fixed_path_are_rejected(self) -> None:
        request = Mock()
        with patch.object(self.client, "_request_json", request):
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_topology_network_summary("b" * 24)
            request.assert_not_called()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", "/openapi/v2/other/sites/site_1/topology/available-network")


if __name__ == "__main__":
    unittest.main()
