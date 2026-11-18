from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_p2p_info import ApP2pInfoError, summarize_ap_p2p_info


class ApP2pInfoProjectionTests(unittest.TestCase):
    def test_returns_group_counts_and_redacts_device_identities(self):
        result = summarize_ap_p2p_info({
            "mainAp": {"deviceMac": "AA:BB:CC:DD:EE:FF", "deviceName": "private main"},
            "childAps": [{"deviceMac": "00:11:22:33:44:55", "deviceName": "private child"}],
        })
        self.assertTrue(result["main_ap_present"])
        self.assertEqual(result["child_ap_count"], 1)
        self.assertEqual(result["redacted_identity_field_count"], 4)
        self.assertFalse(result["partial"])
        for private in ("AA:BB:CC:DD:EE:FF", "private main",
                        "00:11:22:33:44:55", "private child"):
            self.assertNotIn(private, repr(result))

    def test_no_group_and_empty_children_are_distinct(self):
        result = summarize_ap_p2p_info({"mainAp": None, "childAps": []})
        self.assertFalse(result["main_ap_present"])
        self.assertEqual(result["child_ap_count"], 0)
        self.assertFalse(result["partial"])

    def test_invalid_and_unknown_fields_are_counted_without_echo(self):
        result = summarize_ap_p2p_info({
            "mainAp": {"deviceMac": 7, "vendorField": "private"},
            "childAps": [{"deviceName": None}],
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_and_oversized_root_shapes(self):
        for value in (None, [], {f"extra{index}": True for index in range(9)}):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ApP2pInfoError):
                    summarize_ap_p2p_info(value)
        too_many = summarize_ap_p2p_info({"mainAp": None, "childAps": [None] * 1025})
        self.assertTrue(too_many["partial"])
        self.assertEqual(too_many["invalid_field_count"], 1)


class ApP2pInfoClientTests(unittest.TestCase):
    def test_reads_fixed_route_for_inventoried_ap(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        response = {"errorCode": 0, "result": {
            "mainAp": {"deviceName": "private"}, "childAps": []}}
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/p2pInfo"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_ap_p2p_info(site_ref, ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_p2p_info")
        self.assertNotIn("private", repr(result))

    def test_request_guard_rejects_modified_p2p_route(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/p2pInfo?extra=1")
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
