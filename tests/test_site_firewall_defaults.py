from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_firewall_defaults import (
    SiteFirewallDefaultsError, project_site_firewall_defaults,
)


def source_defaults():
    return {
        "icmp": 30, "other": 120, "tcpClose": 10, "tcpCloseWait": 60,
        "tcpEstablished": 900, "tcpFinWait": 30, "tcpLastAck": 30,
        "tcpSynReceive": 60, "tcpSynSent": 60, "tcpTimeWait": 30,
        "udpOther": 120, "udpStream": 180,
        "broadcastPing": False, "receiveRedirects": False,
        "sendRedirects": False, "synCookies": True,
    }


class SiteFirewallDefaultsProjectionTests(unittest.TestCase):
    def test_projects_only_documented_timeout_and_flag_fields(self):
        value = source_defaults()
        value["privateExtra"] = "must not be returned"
        result = project_site_firewall_defaults(value)
        self.assertEqual(result["data"]["timeouts"]["tcpEstablished"], 900)
        self.assertEqual(result["data"]["flags"]["synCookies"], True)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("privateExtra", repr(result))

    def test_missing_and_out_of_range_values_are_partial(self):
        value = source_defaults()
        del value["tcpClose"]
        value["tcpEstablished"] = 2_097_152
        value["broadcastPing"] = 1
        result = project_site_firewall_defaults(value)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertNotIn("tcpClose", result["data"]["timeouts"])
        self.assertTrue(result["partial"])

    def test_non_object_response_is_rejected(self):
        with self.assertRaises(SiteFirewallDefaultsError):
            project_site_firewall_defaults([])


class SiteFirewallDefaultsClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_site_bound_route_and_projects_result(self):
        response = {"result": source_defaults()}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_site_firewall_defaults(self.site_ref)
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v1/ctrl/sites/site_internal/firewall/timeout/default")
        self.assertEqual(result["data"]["timeouts"]["icmp"], 30)
        self.assertFalse(result["partial"])

    def test_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/site_internal/firewall/timeout/default"
        self.assertTrue(self.client._site_firewall_defaults_request_valid(path))
        self.assertFalse(self.client._site_firewall_defaults_request_valid(
            path.replace("/ctrl/", "/other/")))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_firewall_defaults("7" * 24)


if __name__ == "__main__":
    unittest.main()
