from __future__ import annotations

import unittest

from app.ap_lldp import ApLldpError, project_ap_lldp


class ApLldpTests(unittest.TestCase):
    def test_projects_documented_codes_without_inventing_effective_site_value(self) -> None:
        for code, label in ((0, "off"), (1, "on"), (2, "site_default")):
            with self.subTest(code=code):
                result = project_ap_lldp({"lldpEnable": code, "supportLldp": True})
                self.assertEqual(result["data"], {
                    "setting_code": code, "setting": label, "supported": True,
                })
                self.assertFalse(result["partial"])

    def test_invalid_missing_and_unknown_fields_are_counted_and_values_omitted(self) -> None:
        result = project_ap_lldp({"lldpEnable": True, "supportLldp": "yes",
                                  "secret": "private"})
        self.assertEqual(result["data"], {})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_rejects_non_object_and_oversized_object(self) -> None:
        for value in (None, [], {str(n): n for n in range(9)}):
            with self.subTest(value=value):
                with self.assertRaises(ApLldpError):
                    project_ap_lldp(value)


class ApLldpIntegrationTests(unittest.TestCase):
    def test_exact_route_inventory_binding_and_response_validation(self) -> None:
        from unittest.mock import patch
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "lldpEnable": 2, "supportLldp": True}}) as request:
            result = client.read_ap_lldp_config(site_ref, ap_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/lldp",
            token="token")
        self.assertEqual(result["resource"], "ap_lldp_config")
        self.assertEqual(result["data"]["setting"], "site_default")
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/lldp",
                                     token="token")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            client._request_json("GET", "/openapi/v1/other/sites/site-1/aps/AA-BB-CC-DD-EE-FF/lldp",
                                 token="token")
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client.read_ap_lldp_config(site_ref, ap_ref)


if __name__ == "__main__":
    unittest.main()
