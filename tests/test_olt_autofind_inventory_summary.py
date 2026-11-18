from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_autofind_inventory_summary import (
    OltAutofindInventoryError, project_olt_autofind_inventory_page,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operation_registry import REGISTRY


class OltAutofindInventoryProjectionTests(unittest.TestCase):
    def test_counts_discoveries_and_redacts_credentials_and_identity(self):
        page = [{"key": "private-key", "portId": "private-port",
                 "serialNumber": "private-serial", "macAddress": "private-mac",
                 "passwordType": "ASCII", "password": "private-password",
                 "loid": "private-loid", "loidPassword": "private-loid-password",
                 "hardwareVersion": "private-hw", "softwareVersion": "private-sw",
                 "vendorId": "private-vendor", "equipmentId": "private-equip"}]
        result = project_olt_autofind_inventory_page(page, page_number=2, page_size=10)
        self.assertEqual(result["data"], {
            "discovered_onu_count": 1, "page_number": 2, "page_size": 10,
            "page_may_be_truncated": False,
        })
        self.assertEqual(result["redacted_field_count"], 12)
        for secret in ("private-key", "private-port", "private-serial", "private-mac",
                       "private-password", "private-loid-password", "private-hw"):
            self.assertNotIn(secret, repr(result))

    def test_full_page_warns_that_more_results_may_exist(self):
        result = project_olt_autofind_inventory_page([{}], page_number=0, page_size=1)
        self.assertTrue(result["data"]["page_may_be_truncated"])
        self.assertTrue(result["partial"])

    def test_rejects_malformed_and_oversized_responses(self):
        for value in (None, {}, [{} for _ in range(101)]):
            with self.subTest(value=type(value).__name__), self.assertRaises(OltAutofindInventoryError):
                project_olt_autofind_inventory_page(value, page_number=0, page_size=100)


class OltAutofindInventoryAdapterTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_serializes_required_pon_selector_and_page_to_fixed_contract(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
             patch.object(self.client, "_request_json", return_value={"result": [{"password": "secret"}]}) as request:
            result = self.client.read_olt_onu_autofind_inventory_summary(
                self.site_ref, self.device_ref, "GPON 1/1/1", 0, 10)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
            "pon/onu-register/autofinds/list?ponPort=GPON+1%2F1%2F1&number=0&size=10",
            token="token")
        self.assertEqual(result["data"]["discovered_onu_count"], 1)
        self.assertNotIn("secret", repr(result))

    def test_rejects_bad_query_and_allowlists_only_contract_arguments(self):
        base = "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/pon/onu-register/autofinds/list"
        good = base + "?ponPort=GPON+1%2F1%2F1&number=0&size=10"
        self.assertTrue(self.client._olt_onu_autofind_list_request_valid(good))
        self.assertFalse(self.client._olt_onu_autofind_list_request_valid(good + "&searchKey=x"))
        self.assertFalse(self.client._olt_onu_autofind_list_request_valid(base + "?ponPort=x&number=-1&size=10"))
        with patch.object(self.client, "_request_json") as request, \
             self.assertRaises(OpenApiError):
            self.client.read_olt_onu_autofind_inventory_summary(
                self.site_ref, self.device_ref, "GPON 1/1/1", 0, 101)
        request.assert_not_called()

    def test_registry_exposes_query_arguments_for_http_and_mcp(self):
        operation = REGISTRY.get("olt_onu_autofind_inventory_summary")
        self.assertEqual(operation.extra_arguments, ("pon_port", "page_number", "page_size"))
        self.assertEqual(operation.upstream_method, "GET")
        self.assertEqual(operation.public_method, "GET")


if __name__ == "__main__":
    unittest.main()
