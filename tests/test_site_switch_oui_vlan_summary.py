import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_switch_oui_vlan_summary import summarize_switch_oui_vlan_rows


class SiteSwitchOuiVlanSummaryTests(unittest.TestCase):
    def test_counts_only_enable_and_documented_port_scope_mode(self):
        result = summarize_switch_oui_vlan_rows([
            {"id": "private-rule", "name": "private-name", "enable": True,
             "mode": 0, "deviceList": [{"mac": "private-mac"}]},
            {"enable": False, "mode": 1, "ruleCombine": [{"vlanId": 99}]},
            {"enable": "true", "mode": 2},
        ])
        self.assertEqual(result["by_reported_enabled_flag"],
                         {"true": 1, "false": 1, "unreported": 1})
        self.assertEqual(result["by_documented_port_scope_mode"],
                         {"all_device_ports": 1, "custom_device_ports": 1,
                          "unknown": 1})
        self.assertTrue(result["partial"])
        for secret in ("private-rule", "private-name", "private-mac", "99"):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["enforcement_or_assignments_inferred"])

    def test_bounded_site_pagination_and_guard(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        pages = [
            {"errorCode": 0, "result": {"totalRows": 101, "currentPage": 1,
             "currentSize": 100, "data": [{"enable": True, "mode": 0} for _ in range(100)]}},
            {"errorCode": 0, "result": {"totalRows": 101, "currentPage": 2,
             "currentSize": 1, "data": [{"enable": False, "mode": 1}]}},
        ]
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=pages) as request:
            result = client.read_site_switch_oui_vlan_summary(site_ref)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[1],
                         "/openapi/v1/ctrl/sites/site-internal/switch-oui-rules?page=1&pageSize=100")
        self.assertEqual(result["reported_rule_total"], 101)
        self.assertEqual(result["by_documented_port_scope_mode"],
                         {"all_device_ports": 100, "custom_device_ports": 1})
        self.assertTrue(client._site_switch_oui_vlan_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/switch-oui-rules?page=10&pageSize=1000"))
        self.assertFalse(client._site_switch_oui_vlan_request_valid(
            "/openapi/v1/other/sites/site-internal/switch-oui-rules?page=1&pageSize=100"))


if __name__ == "__main__":
    unittest.main()
