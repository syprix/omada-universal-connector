from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_static_route_summary import (
    SiteStaticRouteSummaryError, summarize_site_static_routes,
)


class SiteStaticRouteSummaryTests(unittest.TestCase):
    def test_counts_only_types_status_and_reference_occurrences(self) -> None:
        rows = [
            {"id": "secret-id", "name": "secret-name", "destinations": ["192.0.2.4"],
             "nextHopIp": "192.0.2.1", "routeType": 0, "status": True,
             "existVpnClient": True, "existVirtualWan": False},
            {"interfaceId": "secret-interface", "routeType": 1, "status": False,
             "existVpnClient": False, "existVirtualWan": True},
            {"routeType": 9, "status": "enabled"},
        ]
        result = summarize_site_static_routes(rows)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["summary"], {
            "by_type": {"interface": 1, "next_hop": 1, "unknown": 1},
            "by_status": {"false": 1, "true": 1, "unknown": 1},
            "reference_occurrences": {
                "interface": 1, "vpn_client": 1, "virtual_wan": 1,
            },
            "unknown_rows": 1,
        })
        rendered = repr(result)
        for value in ("secret-id", "secret-name", "192.0.2.4", "192.0.2.1", "secret-interface"):
            self.assertNotIn(value, rendered)

    def test_non_objects_and_missing_reference_flags_are_partial(self) -> None:
        result = summarize_site_static_routes([None, {"routeType": 0, "status": True}])
        self.assertEqual(result["summary"]["unknown_rows"], 1)
        self.assertEqual(result["summary"]["reference_occurrences"], {})
        self.assertTrue(result["partial"])

    def test_enforces_row_ceiling(self) -> None:
        with self.assertRaises(SiteStaticRouteSummaryError):
            summarize_site_static_routes([{}] * 10_001)

    def test_client_uses_bound_site_and_documented_pagination(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        site_ref = "a" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        calls = []

        def request(method: str, path: str, **kwargs: object) -> dict[str, object]:
            calls.append((method, path))
            return {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                               "data": [{"routeType": 1, "status": True,
                                         "name": "hidden", "destinations": ["198.51.100.2"]}]}}

        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=request):
            result = client.read_site_static_route_summary(site_ref)
        self.assertEqual(calls, [(
            "GET", "/openapi/v1/ctrl/sites/site_1/routing/static-routings?page=1&pageSize=100",
        )])
        self.assertEqual(result["count"], 1)
        self.assertNotIn("hidden", repr(result))
        self.assertNotIn("198.51.100.2", repr(result))

    def test_unknown_site_is_rejected_before_upstream_request(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        with patch.object(client, "_access_token") as access:
            with self.assertRaises(OpenApiError) as caught:
                client.read_site_static_route_summary("a" * 24)
        self.assertEqual(caught.exception.code, "site_ref_unknown")
        access.assert_not_called()
