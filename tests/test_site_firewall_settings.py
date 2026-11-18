from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_firewall_settings import (
    SiteFirewallSettingsError,
    project_site_firewall_settings,
)


def complete_result() -> dict[str, object]:
    result: dict[str, object] = {
        key: 1 for key in (
            "icmp", "other", "tcpClose", "tcpCloseWait", "tcpEstablished",
            "tcpFinWait", "tcpLastAck", "tcpSynReceive", "tcpSynSent",
            "tcpTimeWait", "udpOther", "udpStream",
        )
    }
    result.update({"broadcastPing": True, "receiveRedirects": False,
                   "sendRedirects": True, "synCookies": False})
    return result


class SiteFirewallSettingsProjectionTests(unittest.TestCase):
    def test_projects_all_required_fields(self) -> None:
        source = complete_result()
        result = project_site_firewall_settings(source)
        self.assertEqual(result["data"], source)
        self.assertEqual(result["missing_field_count"], 0)
        self.assertFalse(result["partial"])

    def test_checks_integer_bounds_and_strict_booleans(self) -> None:
        result = project_site_firewall_settings({
            "icmp": 0, "other": 2_097_152, "tcpClose": True,
            "broadcastPing": 1,
        })
        self.assertEqual(result["invalid_field_count"], 4)
        self.assertTrue(result["partial"])

    def test_reports_missing_and_unknown_fields_without_echoing(self) -> None:
        result = project_site_firewall_settings({
            "icmp": 100, "unknown": "not returned",
        })
        self.assertEqual(result["missing_field_count"], 15)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("not returned", repr(result))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(33)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteFirewallSettingsError):
                project_site_firewall_settings(value)


class SiteFirewallSettingsClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "2" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "icmp": 100, "broadcastPing": True}}) as request:
            result = self.client.read_site_firewall_settings(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/firewall",
            token="test-token")
        self.assertEqual(result["data"], {"icmp": 100, "broadcastPing": True})

    def test_rejects_invalid_response_and_unknown_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_firewall_settings(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_firewall_settings("0" * 24)

    def test_path_guard_binds_controller(self) -> None:
        self.assertTrue(self.client._site_firewall_settings_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/firewall"))
        self.assertFalse(self.client._site_firewall_settings_request_valid(
            "/openapi/v1/other/sites/site_internal/firewall"))


if __name__ == "__main__":
    unittest.main()
