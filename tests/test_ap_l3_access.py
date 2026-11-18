from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_l3_access import ApL3AccessError, summarize_ap_l3_access


class ApL3AccessProjectionTests(unittest.TestCase):
    def test_projects_enablement_and_hardware_support(self):
        self.assertEqual(summarize_ap_l3_access(
            {"enable": True, "supportL3Access": False}), {
                "status": "ok", "resource": "ap_l3_access",
                "enabled": True, "supported": False,
                "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False,
            })

    def test_partial_and_invalid_values_are_counted(self):
        result = summarize_ap_l3_access({"enable": 1, "vendor": "private"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_root_shape(self):
        for value in (None, [], {f"extra{index}": True for index in range(9)}):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ApL3AccessError):
                    summarize_ap_l3_access(value)


class ApL3AccessClientTests(unittest.TestCase):
    def test_reads_fixed_route_for_inventoried_ap(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        response = {"errorCode": 0, "result": {"enable": True, "supportL3Access": True}}
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/l3access"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_ap_l3_access(site_ref, ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertTrue(result["enabled"])
        self.assertTrue(result["supported"])

    def test_request_guard_rejects_modified_l3_route(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/l3access?extra=1")
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
