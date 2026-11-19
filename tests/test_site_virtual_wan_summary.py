from __future__ import annotations

import unittest
from unittest.mock import patch

from app.site_virtual_wan_summary import SiteVirtualWanError, project_virtual_wan_pages
from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteVirtualWanProjectionTests(unittest.TestCase):
    def test_summarizes_status_and_keeps_physical_keys_private(self) -> None:
        projected = project_virtual_wan_pages([{
            "totalRows": 2, "currentPage": 1, "currentSize": 2,
            "data": [
                {"id": "private-vwan", "physicalWanId": "private-physical",
                 "physicalWanPortId": 7, "status": True},
                {"id": "private-vwan-2", "physicalWanId": "private-physical-2",
                 "physicalWanPortId": 8, "status": False},
            ],
        }], [{"virtualWanId": "private-vwan", "name": "hidden"}])
        self.assertEqual(projected["virtual_wan_count"], 2)
        self.assertEqual(projected["enabled_count"], 1)
        self.assertEqual(projected["disabled_count"], 1)
        self.assertTrue(projected["complete"])
        self.assertEqual(projected["physical_join"], "not_defined_by_source_contract")
        self.assertEqual(projected["matched_virtual_wan_count"], 1)
        self.assertEqual(projected["unmatched_inventory_count"], 1)
        self.assertTrue(projected["join_complete"])
        for secret in ("private-vwan", "private-physical", "private-physical-2"):
            self.assertNotIn(secret, repr(projected))

    def test_incomplete_page_is_explicit(self) -> None:
        projected = project_virtual_wan_pages([{
            "totalRows": 101, "currentPage": 1, "currentSize": 1,
            "data": [{"status": True, "physicalWanId": "id", "physicalWanPortId": 1}],
        }], [])
        self.assertFalse(projected["complete"])

    def test_duplicate_documented_ids_are_reported_as_ambiguous(self) -> None:
        page = {"totalRows": 2, "currentPage": 1, "currentSize": 2,
                "data": [{"id": "same", "status": True},
                         {"id": "same", "status": False}]}
        projected = project_virtual_wan_pages(
            [page], [{"virtualWanId": "same"}, {"virtualWanId": "same"}])
        self.assertEqual(projected["matched_virtual_wan_count"], 0)
        self.assertEqual(projected["ambiguous_join_key_count"], 1)
        self.assertFalse(projected["join_complete"])

    def test_rejects_inconsistent_or_misordered_pages(self) -> None:
        for pages in ([], [{"totalRows": True, "currentPage": 1, "data": []}],
                      [{"totalRows": 0, "currentPage": 2, "data": []}]):
            with self.subTest(pages=pages), self.assertRaises(SiteVirtualWanError):
                project_virtual_wan_pages(pages, [])


class SiteVirtualWanClientTests(unittest.TestCase):
    def test_uses_fixed_paginated_read_and_returns_redacted_summary(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        result_page = {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                       "data": [{"id": "private-id", "status": True, "physicalWanId": "private-id",
                                 "physicalWanPortId": 3, "name": "private-name"}]}
        def response_for_path(method: str, path: str, *, token: str) -> dict[str, object]:
            if "available-virtual-wans" in path:
                return {"result": {"wanPorts": [{"virtualWanId": "private-id"}]}}
            return {"result": result_page}

        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=response_for_path) as request:
            result = client.read_site_virtual_wan_summary(site_ref)
        self.assertEqual(request.call_args_list[0].args,
                         ("GET", "/openapi/v1/ctrl/sites/site_internal/setting/virtual-wans?page=1&pageSize=100"))
        self.assertEqual(request.call_args_list[0].kwargs, {"token": "token"})
        self.assertEqual(request.call_args_list[1].args,
                         ("GET", "/openapi/v1/ctrl/sites/site_internal/setting/available-virtual-wans"))
        self.assertEqual(request.call_args_list[1].kwargs, {"token": "token"})
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result["matched_virtual_wan_count"], 1)
        self.assertNotIn("private-id", repr(result))
        self.assertNotIn("private-name", repr(result))


if __name__ == "__main__":
    unittest.main()
