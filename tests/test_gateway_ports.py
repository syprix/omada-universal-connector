from __future__ import annotations

import unittest
from unittest.mock import patch

from app.gateway_ports import GatewayPortsError, project_gateway_ports
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF, GATEWAY_REF = "a" * 24, "d" * 24
GATEWAY_MAC = "00:11:22:33:44:77"


class GatewayPortsProjectionTests(unittest.TestCase):
    def test_projects_integer_port_codes_and_removes_port_names(self) -> None:
        result = project_gateway_ports({"osgPortInfos": [
            {"port": 1, "name": "private-label", "type": 2,
             "physicalType": 1, "mode": 0},
        ]})
        self.assertFalse(result["partial"])
        self.assertEqual(result["items"], [{"port": 1, "type": 2,
                                             "physicalType": 1, "mode": 0}])
        self.assertNotIn("private-label", repr(result))

    def test_invalid_fields_become_partial_and_limits_fail_closed(self) -> None:
        result = project_gateway_ports({"osgPortInfos": [
            {"port": True, "type": -1, "unknown": "private"},
        ]})
        self.assertTrue(result["partial"])
        self.assertEqual(result["items"], [])
        self.assertEqual(result["omitted_count"], 1)
        self.assertFalse(project_gateway_ports({"osgPortInfos": []})["partial"])
        for raw in (None, {}, {"osgPortInfos": None}, {"osgPortInfos": [{}] * 65}):
            with self.subTest(raw=raw), self.assertRaises(GatewayPortsError):
                project_gateway_ports(raw)

    def test_projects_direct_hardware_controller_list_response(self) -> None:
        result = project_gateway_ports([{
            "port": 1, "name": "private-label", "type": 2,
            "physicalType": 1, "mode": 0,
        }])
        self.assertFalse(result["partial"])
        self.assertEqual(result["items"], [{"port": 1, "type": 2,
                                             "physicalType": 1, "mode": 0}])
        self.assertNotIn("private-label", repr(result))


class GatewayPortsClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._gateway_macs_by_site_ref[SITE_REF] = {GATEWAY_REF: GATEWAY_MAC}

    def test_reads_fixed_upstream_route_for_inventory_gateway(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"osgPortInfos": [{"port": 1, "name": "private-label",
                                                 "type": 2, "physicalType": 1, "mode": 0}]}}) as request:
            result = self.client.read_gateway_ports(SITE_REF, GATEWAY_REF)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site_1/gateways/{GATEWAY_MAC}/ports",
            token="token")
        self.assertEqual(result["items"], [{"port": 1, "type": 2,
                                             "physicalType": 1, "mode": 0}])
        self.assertNotIn("private-label", repr(result))

    def test_unknown_gateway_is_rejected_before_request(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "gateway_ref_unknown"):
                self.client.read_gateway_ports(SITE_REF, "e" * 24)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
