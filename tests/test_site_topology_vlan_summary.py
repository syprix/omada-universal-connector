from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_topology_vlan_summary import (
    TopologyVlanSummaryError, project_topology_vlan_summary,
)


class TopologyVlanSummaryProjectionTests(unittest.TestCase):
    def test_projects_bounded_counts_without_vlan_values_or_network_identity(self) -> None:
        result = project_topology_vlan_summary({"splitNetworks": [
            {"id": "private-id", "name": "Office LAN", "vlanId": 20,
             "defaultNetwork": True, "configuring": False},
            {"id": "other-id", "name": "Guest LAN", "vlanId": 20,
             "defaultNetwork": False, "configuring": True},
            {"name": "No VLAN", "defaultNetwork": False, "configuring": False},
        ]})
        self.assertEqual(result, {
            "network_count": 3, "distinct_vlan_count": None,
            "default_network_count": 1, "configuring_network_count": 1,
            "missing_vlan_id_count": 1, "unknown_network_field_count": 0,
            "unknown_field_count": 0, "partial": True,
        })
        for private_value in ("private-id", "other-id", "Office LAN", "Guest LAN", "20"):
            self.assertNotIn(private_value, str(result))

    def test_missing_and_unknown_fields_are_partial_and_malformed_values_fail(self) -> None:
        result = project_topology_vlan_summary({
            "splitNetworks": [{"vlanId": 0, "defaultNetwork": False,
                               "configuring": False, "future": "private"}],
            "newField": "private",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["unknown_network_field_count"], 1)
        self.assertNotIn("private", str(result))
        missing_optionals = project_topology_vlan_summary({
            "splitNetworks": [{"vlanId": 0}, {}],
        })
        self.assertEqual(missing_optionals["missing_vlan_id_count"], 1)
        self.assertIsNone(missing_optionals["distinct_vlan_count"])
        self.assertIsNone(missing_optionals["default_network_count"])
        self.assertIsNone(missing_optionals["configuring_network_count"])
        for source in (
            None, {"splitNetworks": "bad"}, {"splitNetworks": [{}] * 257},
            {"splitNetworks": [{"vlanId": True}]},
            {"splitNetworks": [{"vlanId": -1}]},
            {"splitNetworks": [{"vlanId": 2**31}]},
            {"splitNetworks": [{"defaultNetwork": 1}]},
        ):
            with self.subTest(source=source), self.assertRaises(TopologyVlanSummaryError):
                project_topology_vlan_summary(source)
        missing = project_topology_vlan_summary({})
        self.assertTrue(missing["partial"])
        self.assertIsNone(missing["network_count"])


class TopologyVlanSummaryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_uses_fixed_route_and_projects_response(self) -> None:
        calls = []
        def request(method, path, **kwargs):
            calls.append((method, path))
            return {"result": {"splitNetworks": [{"id": "secret", "name": "Hidden",
                "vlanId": 23, "defaultNetwork": True, "configuring": False}]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_site_topology_vlan_summary(self.site_ref)
        self.assertEqual(calls, [("GET", "/openapi/v2/ctrl/sites/site_1/topology/available-vlans")])
        self.assertEqual(result["data"]["distinct_vlan_count"], 1)
        self.assertNotIn("Hidden", str(result))
        self.assertNotIn("23", str(result))

    def test_unknown_site_and_nonfixed_path_are_rejected(self) -> None:
        request = Mock()
        with patch.object(self.client, "_request_json", request):
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_topology_vlan_summary("b" * 24)
            request.assert_not_called()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v2/other/sites/site_1/topology/available-vlans")


if __name__ == "__main__":
    unittest.main()
