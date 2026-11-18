from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class FirewallReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_returns_redacted_gateway_acl_subset_and_evidence(self) -> None:
        rows = [{"id": "rule-1", "index": 2, "description": "private name 192.0.2.1",
                 "status": True, "policy": 0, "protocols": [6, 17],
                 "sourceType": 1, "sourceIds": ["internal-group"],
                 "destinationType": 0, "destinationIds": ["network-2"],
                 "stateMode": 1, "syslog": False, "secret": "private"}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as read:
            result = self.client.list_gateway_firewall_rules(self.site_ref)
        read.assert_called_once_with("/openapi/v1/ctrl/sites/site_1/acls/osg-acls", "token")
        rule = result["items"][0]
        self.assertEqual(rule["index"], 2)
        self.assertTrue(rule["enabled"])
        self.assertEqual(rule["protocols"], [6, 17])
        self.assertEqual(len(rule["source_refs"][0]), 24)
        self.assertNotIn("id", rule)
        for forbidden in ("192.0.2.1", "private name", "internal-group", "network-2", "secret"):
            self.assertNotIn(forbidden, str(result))
        cap = next(item for item in self.client.capabilities()["items"]
                   if item["operation"] == "gateway_firewall_rules")
        self.assertEqual(cap["runtime_evidence"][0]["result"], "success")

    def test_unknown_site_and_malformed_sensitive_fields_rejected(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.list_gateway_firewall_rules("b" * 24)
        malformed = [{"id": "r1", "status": 1, "sourceIds": ["group"]}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=malformed):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.list_gateway_firewall_rules(self.site_ref)

    def test_switch_and_ap_acl_reads_use_their_documented_paths(self) -> None:
        operations = (
            ("list_switch_firewall_rules", "osw-acls", "switch_firewall_rules"),
            ("list_ap_firewall_rules", "eap-acls", "ap_firewall_rules"),
        )
        rows = [{"id": "rule-1", "index": 1, "status": True, "policy": 0,
                 "protocols": [6], "sourceType": 0, "sourceIds": [],
                 "destinationType": 0, "destinationIds": [],
                 "stateMode": 1, "syslog": False}]
        for method_name, endpoint, resource in operations:
            with self.subTest(resource=resource):
                method = getattr(self.client, method_name)
                with patch.object(self.client, "_access_token", return_value="token"), \
                        patch.object(self.client, "_read_pages", return_value=rows) as read:
                    result = method(self.site_ref)
                read.assert_called_once_with(
                    f"/openapi/v1/ctrl/sites/site_1/acls/{endpoint}", "token")
                self.assertEqual(result["resource"], resource)
                self.assertEqual(result["count"], 1)
                self.assertEqual(result["items"][0]["index"], 1)

    def test_allowlist_accepts_only_paged_read_endpoint(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/acls/osg-acls?page=1&pageSize=100"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", allowed + "&search=anything")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", "/openapi/v1/ctrl/sites/site_1/acls/osg-acls")


if __name__ == "__main__":
    unittest.main()
