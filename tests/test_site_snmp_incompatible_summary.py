import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_snmp_incompatible_summary import summarize_snmp_incompatible_rows


class SiteSnmpIncompatibleSummaryTests(unittest.TestCase):
    def test_reports_counts_without_projecting_any_source_specific_fields(self):
        rows = [
            {"mac": "private-mac", "stackId": "private-stack", "ports": [], "impbs": []},
            {"customName": "private-name", "ip": "192.0.2.4", "status": 1,
             "location": {"longitude": 1}},
            None,
        ]
        result = summarize_snmp_incompatible_rows(rows, 5, 2)
        self.assertEqual(result["reported_incompatible_device_total"], 5)
        self.assertEqual(result["returned_device_row_count"], 3)
        self.assertEqual(result["omitted_device_row_count"], 2)
        self.assertEqual(result["invalid_row_count"], 1)
        self.assertTrue(result["partial"])
        for secret in ("private-mac", "private-stack", "private-name", "192.0.2.4"):
            self.assertNotIn(secret, repr(result))

    def test_client_uses_bounded_typed_grid_path_and_only_counts_rows(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        rows = [{"mac": "not-returned", "customName": "also-not-returned"}]
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_bounded_grid_rows", return_value=(rows, 3)) as read:
            result = client.read_site_snmp_incompatible_summary(site_ref)
        read.assert_called_once_with(
            "/openapi/v1/ctrl/sites/site-internal/setting/service/snmp/incompatible-devices",
            "token", 1000, require_success_code=True)
        self.assertEqual(result["reported_incompatible_device_total"], 4)
        self.assertNotIn("not-returned", repr(result))

    def test_path_guard_is_bounded_and_controller_bound(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        base = "/openapi/v1/ctrl/sites/site-1/setting/service/snmp/incompatible-devices"
        self.assertTrue(client._site_snmp_incompatible_request_valid(base + "?page=10&pageSize=1000"))
        self.assertFalse(client._site_snmp_incompatible_request_valid(
            base.replace("/ctrl/", "/other/") + "?page=1&pageSize=100"))
        self.assertFalse(client._site_snmp_incompatible_request_valid(base + "?page=11&pageSize=100"))
        self.assertFalse(client._site_snmp_incompatible_request_valid(base + "?page=1&pageSize=1001"))


if __name__ == "__main__":
    unittest.main()
