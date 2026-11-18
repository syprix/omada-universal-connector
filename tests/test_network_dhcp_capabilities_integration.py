from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.network_dhcp_capabilities import FIELDS


class NetworkDhcpCapabilitiesIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def inventory_network_ref(self) -> str:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[{"id": "network_1"}]):
            inventory = self.client.list_networks(self.site_ref)
        return inventory["items"][0]["network_ref"]

    def test_reads_exact_route_for_network_ref_from_site_inventory(self) -> None:
        network_ref = self.inventory_network_ref()
        raw = {field: (field == "supportGetDhcpClientTable") for field in FIELDS}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_network_dhcp_server_capabilities(self.site_ref, network_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/networks/network_1/dhcp-server/capabilities",
            token="token")
        self.assertEqual(result["resource"], "network_dhcp_server_capabilities")
        self.assertEqual(result["data"]["capabilities"], {
            "get_dhcp_client_table": True, "get_dhcp_server_info": False})
        self.assertFalse(result["partial"])
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "network_dhcp_server_capabilities")["runtime_evidence"][0]
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")

    def test_network_reference_is_site_bound_and_required_from_inventory(self) -> None:
        network_ref = self.inventory_network_ref()
        self.client._site_ids_by_ref["b" * 24] = "site_2"
        with self.assertRaisesRegex(OpenApiError, "network_ref_unknown"):
            self.client.read_network_dhcp_server_capabilities("b" * 24, network_ref)
        with self.assertRaisesRegex(OpenApiError, "network_ref_invalid"):
            self.client.read_network_dhcp_server_capabilities(self.site_ref, "network_1")
        with self.assertRaisesRegex(OpenApiError, "network_ref_unknown"):
            self.client.read_network_dhcp_server_capabilities(self.site_ref, "c" * 24)

    def test_rejects_other_controller_path(self) -> None:
        good = "/openapi/v1/ctrl/sites/site_1/networks/network_1/dhcp-server/capabilities"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
