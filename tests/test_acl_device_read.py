from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class DeviceAclReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_switch_acl_whitelists_policy_and_opaque_refs(self) -> None:
        rows = [{"id": "switch-rule", "index": 1, "description": "private text",
                 "status": True, "policy": 0, "protocols": [6, 17], "sourceType": 1,
                 "sourceIds": ["private-ip-group"], "destinationType": 0,
                 "destinationIds": ["network-id"], "bindingType": 1,
                 "bindingBridgeVlan": 20, "customAclOsws": ["00:11:22:33:44:55"],
                 "customAclPorts": [{"switchMac": "00:11:22:33:44:55"}] }]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as read:
            result = self.client.list_switch_firewall_rules(self.site_ref)
        read.assert_called_once_with("/openapi/v1/ctrl/sites/site_1/acls/osw-acls", "token")
        item = result["items"][0]
        self.assertEqual(item["policy"], 0)
        self.assertTrue(item["enabled"])
        self.assertEqual(item["binding_type"], 1)
        self.assertEqual(len(item["source_refs"][0]), 24)
        for forbidden in ("private text", "switch-rule", "private-ip-group", "network-id",
                          "00:11:22:33:44:55", "customAclPorts"):
            self.assertNotIn(forbidden, str(result))
        cap = next(x for x in self.client.capabilities()["items"]
                   if x["operation"] == "switch_firewall_rules")
        self.assertEqual(cap["runtime_evidence"][0]["result"], "success")

    def test_ap_acl_uses_documented_eap_list_and_separate_evidence(self) -> None:
        rows = [{"id": "eap-acl-1", "index": 2, "description": "private",
                 "status": False, "policy": 1, "protocols": [], "sourceType": 4,
                 "sourceIds": ["ssid-id"], "destinationType": 6, "destinationIds": ["v6-group"]}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as read:
            result = self.client.list_ap_firewall_rules(self.site_ref)
        read.assert_called_once_with("/openapi/v1/ctrl/sites/site_1/acls/eap-acls", "token")
        self.assertFalse(result["items"][0]["enabled"])
        self.assertEqual(result["items"][0]["policy"], 1)
        self.assertNotIn("ssid-id", str(result))
        self.assertEqual(next(x for x in self.client.capabilities()["items"]
                              if x["operation"] == "ap_firewall_rules")["runtime_evidence"][0]["result"],
                         "success")

    def test_unknown_site_and_bad_enums_fail_closed(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.list_switch_firewall_rules("b" * 24)
        bad = [{"id": "acl1", "policy": 2}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=bad):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.list_ap_firewall_rules(self.site_ref)

    def test_only_exact_paged_get_paths_are_allowlisted(self) -> None:
        for path in (
            "/openapi/v1/ctrl/sites/site_1/acls/osw-acls?page=1&pageSize=100",
            "/openapi/v1/ctrl/sites/site_1/acls/eap-acls?page=1&pageSize=100",
        ):
            with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
                with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("POST", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path + "&extra=1")


if __name__ == "__main__":
    unittest.main()
