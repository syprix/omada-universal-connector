import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_recent_clients_summary import (
    SiteRecentClientsError, project_site_recent_clients,
)


class SiteRecentClientsSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projection_counts_only_and_does_not_interpret_last_seen(self):
        result = project_site_recent_clients({
            "totalRows": 4, "currentPage": 1, "currentSize": 2,
            "data": [{"name": "private", "mac": "aa:bb", "lastSeen": 123},
                     {"name": "private2", "ip": "192.0.2.1", "lastSeen": 456}],
        }, 1_000, 2_000, 2)
        self.assertEqual(result["reported_client_count"], 4)
        self.assertEqual(result["sampled_row_count"], 2)
        self.assertTrue(result["partial"])
        self.assertFalse(result["last_seen_unit_interpreted"])
        self.assertNotIn("private", repr(result))
        self.assertNotIn("192.0.2.1", repr(result))

    def test_rejects_invalid_window_page_and_source_shape(self):
        for args in ((2_000, 1_000, 2), (0, 31 * 86_400_000 + 1, 2),
                     (1, 2, 101)):
            with self.assertRaises(SiteRecentClientsError):
                project_site_recent_clients(
                    {"totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []},
                    *args)

    def test_uses_site_bound_controller_time_filters_and_one_page(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 3, "currentPage": 1, "currentSize": 2,
                    "data": [{"mac": "private"}, {"mac": "private2"}],
                }}) as request:
            result = self.client.read_site_recent_clients_summary(
                "a" * 24, 1_790_000_000_000, 1_790_000_001_000)
        path = request.call_args.args[1]
        self.assertTrue(self.client._site_recent_clients_request_valid(path))
        self.assertIn("filters.timeStart=1790000000000&filters.timeEnd=1790000001000", path)
        self.assertEqual(result["sampled_row_count"], 2)
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_window_before_network(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_request_json") as request:
            with self.assertRaises(OpenApiError):
                self.client.read_site_recent_clients_summary("a" * 24, 2_000, 1_000)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
