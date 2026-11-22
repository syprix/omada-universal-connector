import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_vlan_affected_ports_summary import (
    VlanAffectedPortsError, project_site_vlan_affected_ports,
)


class SiteVlanAffectedPortsSummaryTests(unittest.TestCase):
    def test_counts_documented_memberships_and_device_classes_redacted(self):
        result = project_site_vlan_affected_ports({
            "totalRows": 12, "currentPage": 2, "currentSize": 1,
            "hasGateway": False,
            "data": [{"type": "switch", "mac": "private-mac", "name": "private-name",
                      "switchInfo": {"affectedPorts": {
                          "nativePorts": [1, 2], "tagStPorts": ["1/0/4"],
                          "untagLags": [3], "vlan": 52}, "clients": [{"mac": "client"}]}}],
        }, 1, 10)
        self.assertEqual(result["reported_affected_device_count"], 12)
        self.assertEqual(result["sampled_device_count"], 1)
        self.assertEqual(result["device_type_counts"]["switch"], 1)
        self.assertEqual(result["numeric_port_memberships"], 2)
        self.assertEqual(result["standard_port_memberships"], 1)
        self.assertEqual(result["lag_memberships"], 1)
        self.assertTrue(result["has_more"])
        self.assertTrue(result["partial"])
        for private in ("private-mac", "private-name", "1/0/4", "client"):
            self.assertNotIn(private, repr(result))

    def test_rejects_wrong_page_and_malformed_details(self):
        with self.assertRaises(VlanAffectedPortsError):
            project_site_vlan_affected_ports({
                "totalRows": 1, "currentPage": 1, "currentSize": 1, "data": []}, 1, 10)

    def test_client_binds_network_vlans_and_source_page(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        client._network_ids_by_site_ref = {"a" * 24: {"b" * 24: "network_1"}}
        with patch.object(client, "list_networks", return_value={"items": [
                    {"network_ref": "b" * 24, "purpose": 0, "vlan": 52}]}), \
                patch.object(client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "totalRows": 0, "currentPage": 2, "currentSize": 0, "data": [],
                    "hasGateway": False}}) as request:
            response = client.read_site_vlan_affected_ports_summary(
                "a" * 24, "b" * 24, 52, 1, 10)
        self.assertEqual(response["reported_affected_device_count"], 0)
        self.assertTrue(client._site_vlan_affected_ports_request_valid(request.call_args.args[1]))
        self.assertIn("/networks/network_1/vlan/52/ports?page=2&pageSize=10",
                      request.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
