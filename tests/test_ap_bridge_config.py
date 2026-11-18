from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_bridge_config import ApBridgeConfigError, summarize_ap_bridge_config


class ApBridgeConfigProjectionTests(unittest.TestCase):
    def test_summarizes_bridge_state_and_redacts_credentials_and_devices(self):
        result = summarize_ap_bridge_config({
            "bridgeSsidName": "private-ssid", "bridgeSsidPassword": "secret-password",
            "paringCode": 765432, "hwSwitch": 1,
            "tdmaConfig": {"status": 1,
                "clients": [{"mac": "AA:BB:CC:DD:EE:FF", "name": "private AP",
                             "model": "model-secret", "modelVersion": "3.0",
                             "priority": 0},
                            {"priority": 2}],
                "notSupportTdmaClients": [{"mac": "00:11:22:33:44:55"}]},
        })
        self.assertEqual(result["data"], {
            "hw_switch_code": 1, "tdma_status_code": 1,
            "tdma_client_count": 2, "tdma_unsupported_client_count": 1,
            "client_priority_counts": {0: 1, 1: 0, 2: 1},
        })
        self.assertEqual(result["redacted_field_count"], 8)
        self.assertFalse(result["partial"])
        for secret in ("private-ssid", "secret-password", "765432",
                       "AA:BB:CC:DD:EE:FF", "private AP", "model-secret"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_and_unknown_values_are_counted_not_disclosed(self):
        result = summarize_ap_bridge_config({
            "hwSwitch": True, "tdmaConfig": {"status": 2,
                "clients": [{"priority": True, "privateExtension": "secret"}],
                "vendorField": "private-value"},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("private-value", repr(result))

    def test_absent_optional_status_and_lists_remain_unknown_and_partial(self):
        result = summarize_ap_bridge_config({"tdmaConfig": {}})
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["hw_switch_code"], None)
        self.assertEqual(result["data"]["tdma_status_code"], None)
        self.assertIsNone(result["data"]["tdma_client_count"])
        self.assertIsNone(result["data"]["tdma_unsupported_client_count"])
        self.assertEqual(result["missing_field_count"], 4)

    def test_rejects_malformed_and_oversized_structures(self):
        for value in (None, [], {"tdmaConfig": {"clients": [None] * 257}},
                      {"tdmaConfig": {"clients": {"private": "value"}}},
                      {"x" * 129: 1}):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ApBridgeConfigError):
                    summarize_ap_bridge_config(value)


class ApBridgeConfigClientTests(unittest.TestCase):
    def test_fixed_read_is_bound_to_inventoried_ap(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        payload = {"errorCode": 0, "result": {"hwSwitch": 1,
                   "bridgeSsidPassword": "private-password", "tdmaConfig": {"status": 0}}}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload) as request:
            result = client.read_ap_bridge_config(site_ref, ap_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/bridge",
            token="token")
        self.assertEqual(result["data"]["hw_switch_code"], 1)
        self.assertNotIn("private-password", repr(result))
        upstream = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/bridge"
        with patch.object(client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", upstream, token="token")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            client._request_json("GET", upstream.replace("/ctrl/", "/other/"), token="token")
        with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            with patch.object(client, "_access_token", return_value="token"), \
                    patch.object(client, "_request_json", return_value={"errorCode": -39303}):
                client.read_ap_bridge_config(site_ref, ap_ref)


if __name__ == "__main__":
    unittest.main()
