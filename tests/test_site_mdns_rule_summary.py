from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_mdns_rule_summary import SiteMdnsRuleError, project_site_mdns_rules


def page(number, total, rows):
    return {"totalRows": total, "currentPage": number,
            "currentSize": len(rows), "data": rows}


class SiteMdnsRuleProjectionTests(unittest.TestCase):
    def test_counts_rule_state_and_type_codes_redacting_rule_details(self):
        rows = [
            {"id": "private-id", "name": "Private rule", "status": True, "type": 0,
             "profileIds": ["private-profile"],
             "ap": {"serviceVlan": "private-vlan", "clientVlan": "private-clients"}},
            {"id": "private-id-2", "name": "Private rule 2", "status": False, "type": 1,
             "osg": {"serviceNetworks": ["private-service-network"],
                     "clientNetworks": ["private-client-network"]}},
        ]
        result = project_site_mdns_rules([page(1, 2, rows)])
        self.assertEqual(result["data"]["enabled_rule_count"], 1)
        self.assertEqual(result["data"]["disabled_rule_count"], 1)
        self.assertEqual(result["data"]["rule_type_code_counts"], {"0": 1, "1": 1})
        self.assertEqual(result["data"]["reported_total_rule_count"], 2)
        self.assertFalse(result["partial"])
        for value in ("private-id", "Private rule", "private-profile", "private-vlan",
                      "private-clients", "private-service-network", "private-client-network"):
            self.assertNotIn(value, repr(result))

    def test_missing_invalid_unknown_and_page_cap(self):
        partial = project_site_mdns_rules([page(1, 1, [{"name": "Secret"}])])
        self.assertIsNone(partial["data"]["enabled_rule_count"])
        self.assertIsNone(partial["data"]["rule_type_code_counts"])
        self.assertTrue(partial["partial"])
        capped = project_site_mdns_rules([
            page(i, 800, [{"status": True, "type": 0}] * 100) for i in range(1, 6)])
        self.assertEqual(capped["data"]["returned_rule_count"], 500)
        self.assertTrue(capped["data"]["truncated"])
        with self.assertRaises(SiteMdnsRuleError):
            project_site_mdns_rules([page(i, 0, []) for i in range(6)])


class SiteMdnsRuleClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_bounded_pages_without_optional_filters(self):
        responses = [{"result": page(i, 700, [{"status": True, "type": 1}] * 100)}
                     for i in range(1, 6)]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=responses) as request:
            result = self.client.read_site_mdns_rule_summary(self.site_ref)
        self.assertEqual(request.call_count, 5)
        self.assertEqual(request.call_args_list[0].args[1],
                         "/openapi/v1/ctrl/sites/site_internal/setting/service/mdns?page=1&pageSize=100")
        self.assertEqual(request.call_args_list[-1].args[1],
                         "/openapi/v1/ctrl/sites/site_internal/setting/service/mdns?page=5&pageSize=100")
        self.assertTrue(result["data"]["truncated"])

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/site_internal/setting/service/mdns?page=1&pageSize=100"
        self.assertTrue(self.client._site_mdns_rules_request_valid(path))
        self.assertFalse(self.client._site_mdns_rules_request_valid(
            path.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_mdns_rules_request_valid(path + "&sort=name"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_mdns_rule_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
