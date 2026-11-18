import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class MspDeviceLinkTopologyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"
        self.mac = "AA-BB-CC-DD-EE-FF"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {self.device_ref: self.mac}

    def test_fixed_v2_msp_path_uses_inventory_and_redacted_projection(self):
        result = [{"name": "private-device", "mac": self.mac, "ip": "192.0.2.10",
                   "clientCount": 2, "ipcCount": 0, "disconnected": False,
                   "clientHealth": {"good": 2, "fair": 0, "poor": 0, "noData": 0},
                   "successors": []}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": result}) as request:
            response = self.client.read_msp_device_link_topology(
                "msp-1", "customer-1", self.site_ref, self.device_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v2/msp/msp-1/customers/customer-1/sites/site-1/"
            f"devices/{self.mac}/device-link-topology", token="token")
        self.assertEqual(response["resource"], "msp_device_link_topology")
        self.assertEqual(response["data"]["node_count"], 1)
        for private in (self.mac, "private-device", "192.0.2.10", "msp-1", "customer-1"):
            self.assertNotIn(private, str(response))

    def test_rejects_bad_references_unknown_inventory_and_invalid_payload(self):
        with self.assertRaisesRegex(OpenApiError, "msp_reference_invalid"):
            self.client.read_msp_device_link_topology("../msp", "customer-1",
                                                      self.site_ref, self.device_ref)
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_msp_device_link_topology("msp-1", "customer-1",
                                                      self.site_ref, "c" * 24)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_msp_device_link_topology(
                    "msp-1", "customer-1", self.site_ref, self.device_ref)


if __name__ == "__main__":
    unittest.main()
