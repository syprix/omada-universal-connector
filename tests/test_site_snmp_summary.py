from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_snmp_summary import SiteSnmpError, project_site_snmp


class SiteSnmpProjectionTests(unittest.TestCase):
    def test_validates_safe_flags_and_modes_and_redacts_private_fields(self):
        value = {
            "snmpV1V2CEnable": True, "snmpV3Enable": True,
            "communityString": "community-secret", "username": "private-user",
            "password": "private-password", "privacyPassword": "private-privacy",
            "securityLevel": 2, "authMode": 2, "privacyMode": 1,
            "location": "private-location", "contact": "private-contact",
            "privateExtra": "not forwarded",
        }
        result = project_site_snmp(value)
        self.assertTrue(result["data"]["snmp_v1_v2c_enabled"])
        self.assertEqual(result["data"]["security_level_code"], 2)
        self.assertEqual(result["data"]["authentication_mode_code"], 2)
        self.assertNotIn("redacted_field_count", result["data"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        for secret in ("community-secret", "private-user", "private-password",
                       "private-privacy", "private-location", "private-contact",
                       "not forwarded"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_mode_bool_and_missing_enablement_are_partial(self):
        result = project_site_snmp({"snmpV1V2CEnable": 1, "securityLevel": True,
                                    "authMode": 7, "communityString": 4})
        self.assertIsNone(result["data"]["snmp_v1_v2c_enabled"])
        self.assertIsNone(result["data"]["security_level_code"])
        self.assertIsNone(result["data"]["authentication_mode_code"])
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["invalid_field_count"], 4)
        self.assertTrue(result["partial"])

    def test_non_object_response_is_rejected(self):
        with self.assertRaises(SiteSnmpError):
            project_site_snmp([])


class SiteSnmpClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_route_and_discards_credentials(self):
        response = {"result": {
            "snmpV1V2CEnable": False, "snmpV3Enable": True,
            "communityString": "secret-community", "username": "secret-user",
            "password": "secret-password", "privacyPassword": "secret-privacy",
            "securityLevel": 2, "authMode": 2, "privacyMode": 2,
            "location": "secret-location", "contact": "secret-contact",
        }}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_site_snmp_settings_summary(self.site_ref)
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v1/ctrl/sites/site_internal/setting/service/snmp")
        for secret in ("secret-community", "secret-user", "secret-password",
                       "secret-privacy", "secret-location", "secret-contact"):
            self.assertNotIn(secret, repr(result))

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/site_internal/setting/service/snmp"
        self.assertTrue(self.client._site_snmp_request_valid(path))
        self.assertFalse(self.client._site_snmp_request_valid(
            path.replace("/ctrl/", "/other/")))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_snmp_settings_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
