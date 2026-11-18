from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SwitchStatisticsIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "client-id", "client-secret",
            tls_trust="system_ca",
        ))
        self.client._site_ids_by_ref["a" * 24] = "site_1"
        self.client._switch_macs_by_site_ref["a" * 24] = {"b" * 24: "AA:BB:CC:DD:EE:FF"}

    def test_reads_exact_statistics_route_and_redacts_switch_identity(self) -> None:
        raw = {"name": "private-name", "status": 14, "statusCategory": 1,
               "portNum": 0, "ports": [], "uplink": {}, "supportPoe": True,
               "supportStack": False, "supportSTP": True, "speeds": [],
               "mlagMsg": {"role": 0, "dadLinkPort": [], "peerLinkPort": []}}
        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_switch_statistics("a" * 24, "b" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller_1/sites/site_1/stat/switches/AA:BB:CC:DD:EE:FF",
            token="fixture-token")
        self.assertEqual(result["data"]["port_count"], 0)
        self.assertNotIn("private-name", repr(result))


if __name__ == "__main__":
    unittest.main()
