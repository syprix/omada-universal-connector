from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_dhcp_snoops_summary import SiteDhcpSnoopsError, project_site_dhcp_snoops


def page(number, total, rows):
    return {"totalRows": total, "currentPage": number,
            "currentSize": len(rows), "data": rows}


class SiteDhcpSnoopsProjectionTests(unittest.TestCase):
    def test_projects_type_and_status_counts_without_device_details(self):
        rows = [
            {"id": "private-id", "omadacId": "private-controller", "siteId": "private-site",
             "name": "private-name", "mac": "private-mac", "deviceName": "private-device",
             "deviceModel": "private-model", "deviceType": "gateway", "status": 1,
             "ports": [{"portId": "private-port"}]},
            {"deviceType": "ap", "status": 0},
            {"deviceType": "switch", "status": 1},
            {"deviceType": "olt", "status": 1},
        ]
        result = project_site_dhcp_snoops([page(1, 4, rows)])
        self.assertEqual(result["data"]["device_type_counts"], {
            "ap": 1, "gateway": 1, "switch": 1, "olt": 1, "other": 0})
        self.assertEqual(result["data"]["connected_status_code_counts"], {"0": 1, "1": 3})
        self.assertEqual(result["data"]["reported_total_device_count"], 4)
        self.assertFalse(result["partial"])
        for value in ("private-id", "private-controller", "private-site", "private-name",
                      "private-mac", "private-device", "private-model", "private-port"):
            self.assertNotIn(value, repr(result))

    def test_missing_invalid_unknown_and_capped_result(self):
        partial = project_site_dhcp_snoops([page(1, 1, [{"privateKey": "secret"}])])
        self.assertIsNone(partial["data"]["device_type_counts"])
        self.assertGreater(partial["unknown_field_count"], 0)
        self.assertTrue(partial["partial"])
        full = [page(i, 800, [{"deviceType": "gateway", "status": 2}] * 100)
                for i in range(1, 6)]
        capped = project_site_dhcp_snoops(full)
        self.assertEqual(capped["data"]["returned_device_count"], 500)
        self.assertTrue(capped["data"]["truncated"])
        with self.assertRaises(SiteDhcpSnoopsError):
            project_site_dhcp_snoops([page(i, 0, []) for i in range(6)])


class SiteDhcpSnoopsClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_bounded_pages(self):
        responses = [{"result": page(i, 700, [{"deviceType": "switch", "status": 1}] * 100)}
                     for i in range(1, 6)]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=responses) as request:
            result = self.client.read_site_dhcp_snoops_summary(self.site_ref)
        self.assertEqual(request.call_count, 5)
        self.assertEqual(request.call_args_list[0].args[1],
                         "/openapi/v1/ctrl/sites/site_internal/dhcpSnoops?page=1&pageSize=100")
        self.assertEqual(request.call_args_list[-1].args[1],
                         "/openapi/v1/ctrl/sites/site_internal/dhcpSnoops?page=5&pageSize=100")
        self.assertEqual(result["data"]["returned_device_count"], 500)
        self.assertTrue(result["data"]["truncated"])

    def test_path_guard_and_unknown_site(self):
        path = "/openapi/v1/ctrl/sites/site_internal/dhcpSnoops?page=1&pageSize=100"
        self.assertTrue(self.client._site_dhcp_snoops_request_valid(path))
        self.assertFalse(self.client._site_dhcp_snoops_request_valid(
            path.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_dhcp_snoops_request_valid(path + "&sort=mac"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_dhcp_snoops_summary("7" * 24)


if __name__ == "__main__":
    unittest.main()
