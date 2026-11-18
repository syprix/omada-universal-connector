from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_vlan_v1 import ApVlanV1Error, summarize_ap_vlan_v1
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ApVlanV1ProjectionTests(unittest.TestCase):
    def test_projects_mode_and_presence_without_network_identifier(self):
        result = summarize_ap_vlan_v1({
            "mode": 1, "lanNetworkId": "private-network", "bridgeVlan": 4094,
        })
        self.assertEqual(result["mode_code"], 1)
        self.assertTrue(result["bridge_vlan_present"])
        self.assertTrue(result["network_binding_present"])
        self.assertEqual(result["redacted_field_count"], 1)
        self.assertNotIn("private-network", repr(result))
        self.assertFalse(result["partial"])

    def test_default_mode_accepts_omitted_optional_fields(self):
        result = summarize_ap_vlan_v1({"mode": 0})
        self.assertFalse(result["partial"])
        self.assertFalse(result["bridge_vlan_present"])
        self.assertFalse(result["network_binding_present"])

    def test_required_mode_and_invalid_fields_mark_partial(self):
        missing = summarize_ap_vlan_v1({"bridgeVlan": 1})
        self.assertEqual(missing["missing_field_count"], 1)
        invalid = summarize_ap_vlan_v1({"mode": True, "bridgeVlan": "1", "lanNetworkId": 7})
        self.assertEqual(invalid["invalid_field_count"], 3)
        self.assertTrue(invalid["partial"])

    def test_unknown_fields_are_counted_without_values(self):
        result = summarize_ap_vlan_v1({"mode": 0, "futureSecret": "private-value"})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private-value", repr(result))
        self.assertTrue(result["partial"])

    def test_rejects_wrong_root_and_unbounded_fields(self):
        for raw in (None, [], {str(i): i for i in range(9)}):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(ApVlanV1Error):
                summarize_ap_vlan_v1(raw)


class ApVlanV1ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"
        self.client._device_macs_by_site_ref[self.site_ref] = {
            self.ap_ref: "AA-BB-CC-DD-EE-FF"}

    def test_reads_distinct_fixed_v1_route_for_inventoried_ap(self):
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/vlan"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": {"mode": 1, "lanNetworkId": "private"}}) as request:
            result = self.client.read_ap_vlan_v1(self.site_ref, self.ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_vlan_v1")
        self.assertNotIn("private", repr(result))

    def test_rejects_query_modification_and_controller_error(self):
        with patch.object(self.client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/vlan?extra=1")
        connection.assert_not_called()
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": 1}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ap_vlan_v1(self.site_ref, self.ap_ref)


if __name__ == "__main__":
    unittest.main()
