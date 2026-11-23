import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_remote_access_tunnel_status_summary import (
    MAX_ROWS, summarize_remote_access_tunnel_status,
)


class RemoteAccessTunnelStatusSummaryTests(unittest.TestCase):
    def test_counts_documented_connection_and_open_status_without_identity(self):
        result = summarize_remote_access_tunnel_status([
            {"tunnelId": 1, "name": "private-name", "status": 1, "openStatus": True},
            {"tunnelId": 2, "name": "private-name-2", "status": -1, "openStatus": False},
            {"status": 7, "openStatus": None},
        ])
        self.assertEqual(result["by_documented_connection_status"], {
            "connected": 1, "heartbeat_missed": 1, "unknown": 1,
        })
        self.assertEqual(result["by_documented_open_status"], {
            "open": 1, "closed": 1, "unreported": 1,
        })
        self.assertEqual(result["status"], "partial")
        self.assertNotIn("private-name", repr(result))
        self.assertNotIn("tunnelId", repr(result))

    def test_unknown_fields_rows_and_omitted_data_are_partial(self):
        rows = [{"status": 0, "openStatus": False, "future": "private-value"}, None]
        result = summarize_remote_access_tunnel_status(rows)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["invalid_row_count"], 1)
        self.assertNotIn("private-value", repr(result))
        truncated = summarize_remote_access_tunnel_status([{"status": 1, "openStatus": True}] * (MAX_ROWS + 3))
        self.assertEqual(truncated["summarized_tunnel_count"], MAX_ROWS)
        self.assertEqual(truncated["omitted_tunnel_count"], 3)
        self.assertTrue(truncated["partial"])

    def test_client_binds_site_and_reads_fixed_status_path(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"tunnelsStatus": [{"status": 1, "openStatus": True}]},
                }) as request:
            result = client.read_site_remote_access_tunnel_status_summary(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-internal/remoteAccess/tunnel/status",
            token="token")
        self.assertEqual(result["reported_tunnel_count"], 1)
        self.assertEqual(result["by_documented_connection_status"], {"connected": 1})

    def test_fixed_request_guard_binds_controller_and_path(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.assertTrue(client._site_remote_access_tunnel_status_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/remoteAccess/tunnel/status"))
        self.assertFalse(client._site_remote_access_tunnel_status_request_valid(
            "/openapi/v1/other/sites/site-internal/remoteAccess/tunnel/status"))
        self.assertFalse(client._site_remote_access_tunnel_status_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/remoteAccess/tunnel/status?raw=true"))


if __name__ == "__main__":
    unittest.main()
