import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_routing_table_summary import (
    SiteRoutingTableError, project_site_routing_table,
)


class SiteRoutingTableSummaryTests(unittest.TestCase):
    def test_counts_rows_and_uninterpreted_type_values_without_destinations(self):
        result = project_site_routing_table({
            "totalRows": 12, "currentPage": 1, "currentSize": 2,
            "data": [{"mac": "private-mac", "name": "private-name", "type": "static",
                      "destinationIp": "192.0.2.1", "nextHops": ["192.0.2.2"],
                      "distance": 1, "metric": 5},
                     {"type": "static", "nextHop": "192.0.2.3"}],
        }, "switch", 0, 10)
        self.assertEqual(result["reported_route_count"], 12)
        self.assertEqual(result["sampled_route_count"], 2)
        self.assertEqual(result["distinct_uninterpreted_type_value_count"], 1)
        self.assertEqual(result["rows_with_distance"], 1)
        self.assertTrue(result["has_more"])
        for private in ("private-mac", "private-name", "192.0.2.1", "192.0.2.2", "static"):
            self.assertNotIn(private, repr(result))

    def test_accepts_only_documented_types_and_rejects_bad_page(self):
        for device_type in ("ap", "router", "Switch"):
            with self.assertRaises(SiteRoutingTableError):
                project_site_routing_table({}, device_type, 0, 10)
        with self.assertRaises(SiteRoutingTableError):
            project_site_routing_table(
                {"totalRows": 0, "currentPage": 2, "currentSize": 0, "data": []},
                "gateway", 0, 10)

    def test_client_binds_device_type_and_page(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "totalRows": 0, "currentPage": 3, "currentSize": 0, "data": []}}) as request:
            result = client.read_site_routing_table_summary("a" * 24, "gateway", 2, 25)
        self.assertEqual(result["reported_route_count"], 0)
        path = request.call_args.args[1]
        self.assertTrue(client._site_routing_table_request_valid(path))
        self.assertIn("/insight/routing/gateway?page=3&pageSize=25", path)


if __name__ == "__main__":
    unittest.main()
