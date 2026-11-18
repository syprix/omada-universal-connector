from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_snmp_config import ApSnmpConfigError, summarize_ap_snmp_config
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ApSnmpConfigProjectionTests(unittest.TestCase):
    def test_redacts_custom_location_and_contact(self):
        result = summarize_ap_snmp_config({
            "type": 1, "location": "private-office", "contact": "ops@example.invalid",
        })
        self.assertEqual(result["type_code"], 1)
        self.assertTrue(result["location_present"])
        self.assertTrue(result["contact_present"])
        self.assertEqual(result["redacted_field_count"], 2)
        self.assertNotIn("private-office", repr(result))
        self.assertNotIn("ops@example.invalid", repr(result))
        self.assertFalse(result["partial"])

    def test_site_mode_does_not_require_custom_text(self):
        result = summarize_ap_snmp_config({"type": 0})
        self.assertFalse(result["location_present"])
        self.assertFalse(result["contact_present"])
        self.assertEqual(result["missing_field_count"], 0)
        self.assertFalse(result["partial"])

    def test_custom_mode_marks_missing_fields_partial(self):
        result = summarize_ap_snmp_config({"type": 1, "location": "room-1"})
        self.assertTrue(result["location_present"])
        self.assertEqual(result["missing_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_rejects_invalid_types_and_string_shapes(self):
        result = summarize_ap_snmp_config({"type": True, "location": "a\tb", "contact": "with space"})
        self.assertIsNone(result["type_code"])
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertTrue(result["partial"])

    def test_unknown_fields_are_counted_without_returning_values(self):
        result = summarize_ap_snmp_config({"type": 0, "community": "secret-community"})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("secret-community", repr(result))
        self.assertTrue(result["partial"])

    def test_rejects_unbounded_or_wrong_root(self):
        for raw in (None, [], {str(i): i for i in range(9)}):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(ApSnmpConfigError):
                summarize_ap_snmp_config(raw)


class ApSnmpConfigClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"
        self.client._device_macs_by_site_ref[self.site_ref] = {
            self.ap_ref: "AA-BB-CC-DD-EE-FF"}

    def test_reads_fixed_inventoried_ap_route(self):
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/snmp"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": {"type": 1, "location": "secret"}}) as request:
            result = self.client.read_ap_snmp_config(self.site_ref, self.ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_snmp_config")
        self.assertNotIn("secret", repr(result))

    def test_rejects_modified_path_and_controller_error(self):
        with patch.object(self.client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/snmp?extra=1")
        connection.assert_not_called()
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": -39303}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ap_snmp_config(self.site_ref, self.ap_ref)


if __name__ == "__main__":
    unittest.main()
