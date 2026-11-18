from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SwitchVlanInterfaceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "client-id", "client-secret",
            tls_trust="system_ca",
        ))
        self.client._site_ids_by_ref["a" * 24] = "site_1"
        self.client._switch_macs_by_site_ref["a" * 24] = {"b" * 24: "AA:BB:CC:DD:EE:FF"}

    def test_reads_exact_switch_route_and_returns_redacted_aggregate(self) -> None:
        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"vlanInterfaceId": "private-id", "vlanInterfaceName": "private-name",
                     "vlanId": 20},
                ]}) as request:
            result = self.client.list_switch_vlan_interfaces("a" * 24, "b" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller_1/sites/site_1/vlan-interface/switches/"
            "AA:BB:CC:DD:EE:FF", token="fixture-token")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["summary"]["unique_vlan_count"], 1)
        self.assertNotIn("private-id", repr(result))
        self.assertNotIn("private-name", repr(result))


if __name__ == "__main__":
    unittest.main()
