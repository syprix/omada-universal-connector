from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_ddns_summary import SiteDdnsError, project_site_ddns


def page(number, total, rows):
    return {"totalRows": total, "currentPage": number,
            "currentSize": len(rows), "data": rows,
            "supportCustomDdns": True, "supportCustomInterval": True,
            "supportTpLinkddns": 2, "supportByDsLiteAndMapE": False}


class SiteDdnsProjectionTests(unittest.TestCase):
    def test_counts_status_and_service_code_without_secrets(self):
        rows = [
            {"id": "private-id", "service": 0, "status": True,
             "interfacePortId": "private-port", "username": "private-user",
             "password": "private-password", "domainName": "private.example",
             "updateUrl": "https://private.example/[PASSWORD]", "updateInterval": 24},
            {"service": 5, "status": False, "domainName": "private2.example",
             "customInterval": 10},
        ]
        result = project_site_ddns([page(1, 2, rows)])
        self.assertEqual(result["data"]["enabled_ddns_count"], 1)
        self.assertEqual(result["data"]["disabled_ddns_count"], 1)
        self.assertEqual(result["data"]["service_code_counts"], {"0": 1, "5": 1})
        self.assertEqual(result["data"]["support_flags"], {
            "supportCustomDdns": True, "supportCustomInterval": True,
            "supportTpLinkddns": 2, "supportByDsLiteAndMapE": False})
        self.assertEqual(result["data"]["reported_total_ddns_count"], 2)
        self.assertFalse(result["partial"])
        for secret in ("private-id", "private-port", "private-user", "private-password",
                       "private.example", "[PASSWORD]"):
            self.assertNotIn(secret, repr(result))

    def test_missing_invalid_unknown_and_page_cap(self):
        partial = project_site_ddns([page(1, 1, [{"username": "secret"}])])
        self.assertIsNone(partial["data"]["enabled_ddns_count"])
        self.assertIsNone(partial["data"]["service_code_counts"])
        self.assertTrue(partial["data"]["support_flags"]["supportCustomDdns"])
        self.assertTrue(partial["partial"])
        capped = project_site_ddns([
            page(i, 800, [{"status": True, "service": 4}] * 100)
            for i in range(1, 6)])
        self.assertEqual(capped["data"]["returned_ddns_count"], 500)
        self.assertTrue(capped["data"]["truncated"])
        with self.assertRaises(SiteDdnsError):
            project_site_ddns([page(i, 0, []) for i in range(6)])

    def test_unknown_service_code_and_inconsistent_support_are_reported(self):
        first = page(1, 2, [{"service": 9, "status": True}])
        second = page(2, 2, [{"service": 0, "status": False}])
        second["supportCustomDdns"] = False
        result = project_site_ddns([first, second])
        self.assertEqual(result["data"]["unknown_service_code_count"], 1)
        self.assertIsNone(result["data"]["support_flags"]["supportCustomDdns"])
        self.assertTrue(result["partial"])


class SiteDdnsClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_bounded_pages_without_sort_filters(self):
        responses = [{"result": page(i, 700, [{"service": 5, "status": True}] * 100)}
                     for i in range(1, 6)]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=responses) as request:
            result = self.client.read_site_ddns_summary(self.site_ref)
        self.assertEqual(request.call_count, 5)
        self.assertEqual(request.call_args_list[0].args[1],
                         "/openapi/v1/ctrl/sites/site_internal/setting/service/ddns?page=1&pageSize=100")
        self.assertEqual(request.call_args_list[-1].args[1],
                         "/openapi/v1/ctrl/sites/site_internal/setting/service/ddns?page=5&pageSize=100")
        self.assertTrue(result["data"]["truncated"])

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/site_internal/setting/service/ddns?page=1&pageSize=100"
        self.assertTrue(self.client._site_ddns_request_valid(path))
        self.assertFalse(self.client._site_ddns_request_valid(
            path.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_ddns_request_valid(path + "&sorts.status=asc"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_ddns_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
