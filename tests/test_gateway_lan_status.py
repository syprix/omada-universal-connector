from __future__ import annotations

import unittest
from unittest.mock import patch

from app.gateway_lan_status import GatewayLanStatusError, project_gateway_lan_status
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF, GATEWAY_REF = "a" * 24, "d" * 24
GATEWAY_MAC = "00:11:22:33:44:77"


class GatewayLanStatusProjectionTests(unittest.TestCase):
    def test_projects_counters_and_redacts_lan_identity_and_ip_configuration(self) -> None:
        result = project_gateway_lan_status([{
            "vlan": 20, "lanName": "private-lan", "ip": "192.0.2.1", "rx": 1000,
            "tx": 2000, "clientNum": 3,
            "lanPortIpv6Config": {"addr": "2001:db8::1", "priDns": "2001:db8::2"},
        }])
        self.assertFalse(result["partial"])
        self.assertEqual(result["items"], [{"vlan": 20, "rx": 1000, "tx": 2000,
                                             "clientNum": 3}])
        for private in ("private-lan", "192.0.2.1", "2001:db8::1", "2001:db8::2"):
            self.assertNotIn(private, repr(result))

    def test_bad_values_unknown_fields_and_bounds_are_partial_or_fail_closed(self) -> None:
        result = project_gateway_lan_status([{"vlan": True, "rx": -1, "private": "x"}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["items"], [])
        self.assertEqual(result["omitted_count"], 1)
        self.assertFalse(project_gateway_lan_status([])["partial"])
        for raw in (None, {}, [{}] * 65):
            with self.subTest(raw=raw), self.assertRaises(GatewayLanStatusError):
                project_gateway_lan_status(raw)


class GatewayLanStatusClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._gateway_macs_by_site_ref[SITE_REF] = {GATEWAY_REF: GATEWAY_MAC}

    def test_reads_fixed_route_and_returns_redacted_site_bound_result(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": [{"vlan": 20, "ip": "192.0.2.1", "rx": 12,
                                "tx": 34, "clientNum": 2}]}) as request:
            result = self.client.read_gateway_lan_status(SITE_REF, GATEWAY_REF)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/lan-status",
            token="token")
        self.assertEqual(result["items"], [{"vlan": 20, "rx": 12, "tx": 34,
                                             "clientNum": 2}])
        self.assertNotIn("192.0.2.1", repr(result))

    def test_rejects_unlisted_path_and_unknown_gateway(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json(
                    "GET", f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/lan-status-evil",
                    token="token")
            with self.assertRaisesRegex(OpenApiError, "gateway_ref_unknown"):
                self.client.read_gateway_lan_status(SITE_REF, "e" * 24)


if __name__ == "__main__":
    unittest.main()
