from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class MspOltReadTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_msp_device_reads_use_site_bound_olt_and_redacted_projections(self):
        detail = {"type": "olt", "model": "OLT-Model", "status": 14,
                  "cpuUtil": 20, "memUtil": 30, "uptimeLong": 1000,
                  "onuCount": 12, "down": 100, "up": 200,
                  "downlinkList": [], "name": "private-name", "ip": "192.0.2.8"}
        cases = (
            (self.client.read_msp_olt_detail_summary,
             "/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/olts/00-11-22-33-44-55",
             detail, "msp_olt_detail_summary"),
            (self.client.read_msp_olt_eth_config_summary,
             "/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/olts/00-11-22-33-44-55/l2-feature/eth-port/port/unit1/list",
             [], "msp_olt_eth_config_summary"),
            (self.client.read_msp_olt_pon_port_config_summary,
             "/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/olts/00-11-22-33-44-55/pon/pon-port/configs/list",
             [], "msp_olt_pon_port_config_summary"),
        )
        for method, path, result_payload, resource in cases:
            with self.subTest(resource=resource), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": result_payload}) as request:
                result = method("msp-1", "customer-2", self.site_ref, self.device_ref)
            request.assert_called_once_with("GET", path, token="token")
            self.assertEqual(result["resource"], resource)
            self.assertEqual(result["device_ref"], self.device_ref)
            self.assertNotIn("msp-1", repr(result))
            self.assertNotIn("customer-2", repr(result))
            self.assertNotIn("private-name", repr(result))
            self.assertNotIn("192.0.2.8", repr(result))

    def test_msp_site_port_read_uses_the_site_scope_without_device_mac(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "ethUnit1PortDTOList": [], "ponPortDTOList": []}}) as request:
            result = self.client.read_msp_olt_site_ports_summary(
                "msp-1", "customer-2", self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/eth-port/and/pon-port/list",
            token="token")
        self.assertEqual(result["resource"], "msp_olt_site_ports_summary")
        self.assertNotIn("msp-1", repr(result))
        self.assertNotIn("customer-2", repr(result))

    def test_fixed_route_allowlist_and_reference_binding(self):
        paths = (
            "/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/olts/00-11-22-33-44-55",
            "/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/olts/00-11-22-33-44-55/l2-feature/eth-port/port/unit1/list",
            "/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/olts/00-11-22-33-44-55/pon/pon-port/configs/list",
        )
        for path in paths:
            self.assertTrue(self.client._msp_olt_device_request_valid(path))
            self.assertFalse(self.client._msp_olt_device_request_valid(path + "?extra=x"))
        site_path = "/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/eth-port/and/pon-port/list"
        self.assertTrue(self.client._msp_olt_site_ports_request_valid(site_path))
        self.assertFalse(self.client._msp_olt_site_ports_request_valid(site_path + "/extra"))
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaises(OpenApiError):
            self.client.read_msp_olt_detail_summary("../bad", "customer-2", self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
