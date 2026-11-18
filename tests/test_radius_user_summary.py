import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.radius_user_summary import RadiusUserSummaryError, summarize_radius_users


class RadiusUserSummaryProjectionTests(unittest.TestCase):
    def test_returns_aggregate_counts_and_redacts_account_data(self):
        rows = [{
            "userId": "private-user-id", "type": 2, "username": "private-user",
            "password": "private-password", "upRateLimit": 100,
            "downRateLimit": 200, "upLimit": 300, "downLimit": 400,
            "vlanId": 31, "timeout": 900, "description": "private note",
        }, {"type": 1, "username": "", "password": ""}]
        result = summarize_radius_users(rows)
        self.assertEqual(result, {"data": {
            "user_count": 2, "user_type_code_counts": {"1": 1, "2": 1},
            "username_present": 1, "password_present": 1,
            "vlan_id_field_present": 1, "session_timeout_field_present": 1,
            "upload_rate_limit_field_present": 1, "download_rate_limit_field_present": 1,
            "upload_traffic_limit_field_present": 1, "download_traffic_limit_field_present": 1,
            "invalid_field_count": 0, "unknown_field_count": 0,
        }, "partial": False})
        for sensitive in ("private-user-id", "private-user", "private-password", "private note", "31"):
            self.assertNotIn(sensitive, repr(result))

    def test_invalid_and_unknown_fields_are_counted_without_echo(self):
        result = summarize_radius_users([{
            "type": True, "username": 7, "password": "secret", "vendorData": "private",
        }])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertEqual(result["data"]["password_present"], 1)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("private", repr(result))

    def test_empty_inventory_is_valid_and_bounds_are_enforced(self):
        self.assertFalse(summarize_radius_users([])["partial"])
        with self.assertRaisesRegex(RadiusUserSummaryError, "response_invalid"):
            summarize_radius_users(None)
        with self.assertRaisesRegex(RadiusUserSummaryError, "response_invalid"):
            summarize_radius_users([{}] * 10_001)


class RadiusUserSummaryClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"

    def test_reads_fixed_paginated_site_route_and_returns_only_summary(self):
        response = {"errorCode": 0, "result": {
            "data": [{"userId": "private-id", "type": 3,
                      "username": "private-name", "password": "private-secret"}],
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
        }}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_site_radius_user_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/profiles/radius-server/users?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["resource"], "site_radius_user_summary")
        self.assertEqual(result["data"]["user_count"], 1)
        for sensitive in ("private-id", "private-name", "private-secret"):
            self.assertNotIn(sensitive, repr(result))

    def test_rejects_unknown_site_before_upstream_request(self):
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_radius_user_summary("b" * 24)
        request.assert_not_called()

    def test_request_guard_binds_controller_and_fixed_pagination(self):
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/sites/site-1/profiles/radius-server/users"
                "?page=1&pageSize=100")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/ctrl/sites/site-1/profiles/radius-server/users"
                "?page=1&pageSize=100&username=private")


if __name__ == "__main__":
    unittest.main()
