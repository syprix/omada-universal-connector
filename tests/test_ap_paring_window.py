from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_paring_window import ApParingWindowError, summarize_ap_paring_window


class ApParingWindowProjectionTests(unittest.TestCase):
    def test_aggregates_status_and_rssi_without_device_identity(self):
        result = summarize_ap_paring_window({
            "status": 1, "countdown": 35,
            "clientAps": [
                {"mac": "AA:BB:CC:DD:EE:FF", "status": 20, "rssi": -58,
                 "model": "EAP-private", "modelVersion": "9.9"},
                {"mac": "00:11:22:33:44:55", "status": 20, "rssi": -67,
                 "model": "EAP-secret", "modelVersion": "8.0"},
            ],
        })
        self.assertEqual(result["window_status_code"], 1)
        self.assertEqual(result["countdown_value"], 35)
        self.assertEqual(result["client_ap_count"], 2)
        self.assertEqual(result["client_status_counts"], {20: 2})
        self.assertEqual(result["rssi_value_counts"], {-67: 1, -58: 1})
        self.assertEqual(result["redacted_identity_field_count"], 6)
        self.assertFalse(result["partial"])
        for private in ("AA:BB:CC:DD:EE:FF", "00:11:22:33:44:55",
                        "EAP-private", "EAP-secret", "9.9", "8.0"):
            self.assertNotIn(private, repr(result))

    def test_missing_invalid_and_unknown_values_mark_partial(self):
        result = summarize_ap_paring_window({
            "status": True, "countdown": -1, "clientAps": [
                {"status": "private", "rssi": 999999999999, "secret": "private"},
                {},
            ],
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 4)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["missing_field_count"], 2)
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_root_shapes_and_caps_client_rows(self):
        for value in (None, [], {f"extra{index}": True for index in range(9)}):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ApParingWindowError):
                    summarize_ap_paring_window(value)
        large = summarize_ap_paring_window({"status": 0, "countdown": 0,
                                            "clientAps": [None] * 257})
        self.assertTrue(large["partial"])
        self.assertEqual(large["invalid_field_count"], 1)


class ApParingWindowClientTests(unittest.TestCase):
    def test_reads_fixed_route_for_inventoried_ap(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        response = {"errorCode": 0, "result": {
            "status": 0, "countdown": 0, "clientAps": []}}
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/paring-window-result"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_ap_paring_window(site_ref, ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_paring_window")

    def test_request_guard_rejects_modified_pairing_route(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/"
                    "paring-window-result?extra=1")
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
