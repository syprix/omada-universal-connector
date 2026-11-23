import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_stack_dhcp_user_summary import summarize_stack_dhcp_user_rows


class SiteStackDhcpUserSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-internal"

    def test_counts_documented_user_and_static_dynamic_codes_only(self):
        result = summarize_stack_dhcp_user_rows([
            {"type": 0, "status": 1, "ipAddress": "192.0.2.4",
             "macAddress": "private-mac", "name": "private-name"},
            {"type": 1, "status": 0, "netId": "private-network"},
            {"type": 9, "status": 2},
        ])
        self.assertEqual(result["by_documented_user_type"],
                         {"client": 1, "device": 1, "unknown": 1})
        self.assertEqual(result["by_documented_binding_status"],
                         {"dynamic": 1, "static": 1, "unreported": 1})
        self.assertTrue(result["partial"])
        for secret in ("192.0.2.4", "private-mac", "private-name", "private-network"):
            self.assertNotIn(secret, repr(result))

    def test_fresh_unique_same_site_binding_and_bounded_grid(self):
        stack_ref = self.client._opaque_ref("stack", "site-internal:stack-1")
        stack_page = {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
                      "currentSize": 1, "data": [{"id": "stack-1"}]}}
        user_page = {"errorCode": 0, "result": {"totalRows": 2, "currentPage": 1,
                      "currentSize": 2, "data": [{"type": 0, "status": 0},
                                                   {"type": 1, "status": 1}]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[stack_page, user_page]) as request:
            result = self.client.read_site_stack_dhcp_user_summary(self.site_ref, stack_ref)
        self.assertEqual(request.call_args_list[0].args[1],
                         "/openapi/v1/ctrl/sites/site-internal/stacks?page=1&pageSize=32")
        self.assertEqual(request.call_args_list[1].args[1],
                         "/openapi/v1/ctrl/sites/site-internal/stack/stack-1/dhcp/user-list?page=1&pageSize=100")
        self.assertEqual(result["reported_user_total"], 2)
        self.assertEqual(result["by_documented_binding_status"],
                         {"dynamic": 1, "static": 1, "unreported": 0})
        self.assertFalse(result["addresses_names_and_binding_rows_returned"])

    def test_rejects_ambiguous_or_truncated_stack_inventory(self):
        stack_ref = self.client._opaque_ref("stack", "site-internal:stack-1")
        for rows, omitted in (([{"id": "stack-1"}, {"id": "stack-1"}], 0),
                              ([{"id": "stack-1"}], 1)):
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_read_bounded_grid_rows",
                                 return_value=(rows, omitted)) as read, \
                    patch.object(self.client, "_request_json") as request:
                with self.assertRaises(OpenApiError):
                    self.client.read_site_stack_dhcp_user_summary(self.site_ref, stack_ref)
                request.assert_not_called()
                self.assertTrue(read.call_args.kwargs["require_success_code"])


if __name__ == "__main__":
    unittest.main()
