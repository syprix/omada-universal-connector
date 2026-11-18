import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class NetworkDhcpServerInfoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[{"id": "network_1"}]):
            self.network_ref = self.client.list_networks(self.site_ref)["items"][0]["network_ref"]

    def test_reads_exact_inventory_bound_route_and_redacts_pool_addresses(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "ranges": [{"startIp": "192.0.2.10", "endIp": "192.0.2.20",
                                "availableIpNum": 5}]}}) as request:
            result = self.client.read_network_dhcp_server_info(self.site_ref, self.network_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/networks/network_1/dhcp-server-info",
            token="token")
        self.assertEqual(result["resource"], "network_dhcp_server_info")
        self.assertEqual(result["data"]["available_ip_count"], 5)
        self.assertFalse(result["partial"])
        self.assertNotIn("192.0.2.10", str(result))
        self.assertNotIn("192.0.2.20", str(result))
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "network_dhcp_server_info")["runtime_evidence"][0]
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")

    def test_rejects_network_reference_from_another_site_or_raw_controller_id(self):
        self.client._site_ids_by_ref["b" * 24] = "site_2"
        with self.assertRaisesRegex(OpenApiError, "network_ref_unknown"):
            self.client.read_network_dhcp_server_info("b" * 24, self.network_ref)
        with self.assertRaisesRegex(OpenApiError, "network_ref_invalid"):
            self.client.read_network_dhcp_server_info(self.site_ref, "network_1")

    def test_invalid_response_and_controller_path_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"ranges": "bad"}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_network_dhcp_server_info(self.site_ref, self.network_ref)
        good = "/openapi/v1/ctrl/sites/site_1/networks/network_1/dhcp-server-info"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
