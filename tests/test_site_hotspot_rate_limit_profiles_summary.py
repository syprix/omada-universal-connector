import unittest
from unittest.mock import patch

from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_hotspot_rate_limit_profiles_summary import (
    SiteHotspotRateLimitProfilesError, summarize_hotspot_rate_limit_profiles,
)


MAX_KBPS = 10_485_760


class FakeResponse:
    status = 200

    def __init__(self, payload):
        import json
        self.raw = json.dumps(payload).encode()

    def read(self, limit=-1):
        return self.raw[:limit]

    def getheader(self, name, default=""):
        return "application/json" if name.lower() == "content-type" else default


class FakeConnection:
    _omada_tls_verified = True

    def __init__(self, payload):
        self.response = FakeResponse(payload)
        self.request_args = None

    def request(self, method, path, body=None, headers=None):
        self.request_args = (method, path, body, headers)

    def getresponse(self):
        return self.response

    def close(self):
        pass


class SiteHotspotRateLimitProfilesSummaryTests(unittest.TestCase):
    def client(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64,
        ))
        client._site_ids_by_ref = {"a" * 24: "controller-site"}
        return client

    def test_aggregates_only_valid_enabled_kbps_limits_at_boundaries(self):
        result = summarize_hotspot_rate_limit_profiles([
            {"id": "private-id", "name": "private-name", "site": "private-site",
             "downLimitEnable": True, "downLimit": 1,
             "upLimitEnable": True, "upLimit": MAX_KBPS, "isDefault": True},
            {"downLimitEnable": False, "downLimit": MAX_KBPS,
             "upLimitEnable": False, "upLimit": 999, "isDefault": False},
        ])
        self.assertEqual(result["profile_count"], 2)
        self.assertEqual(result["directional_coverage"]["downstream"]["enable_counts"], {
            "enabled": 1, "disabled": 1, "missing": 0, "invalid": 0,
        })
        self.assertEqual(result["directional_coverage"]["downstream"]["enabled_limit_kbps"], {
            "count": 1, "sum": 1, "min": 1, "max": 1,
        })
        self.assertEqual(result["directional_coverage"]["upstream"]["enabled_limit_kbps"], {
            "count": 1, "sum": MAX_KBPS, "min": MAX_KBPS, "max": MAX_KBPS,
        })
        self.assertEqual(result["default_profile_counts"], {
            "true": 1, "false": 1, "missing": 0, "invalid": 0,
        })
        self.assertFalse(result["partial"])
        self.assertFalse(result["disabled_limit_values_counted"])
        for private in ("private-id", "private-name", "private-site"):
            self.assertNotIn(private, repr(result))
        self.assertNotIn("downLimit", repr(result))
        self.assertNotIn("upLimit", repr(result))

    def test_missing_invalid_unknown_fields_and_unknown_flags_stay_explicit(self):
        result = summarize_hotspot_rate_limit_profiles([
            {"downLimitEnable": True, "downLimit": 0,
             "upLimitEnable": True, "upLimit": True,
             "isDefault": "yes", "private_field_name": "private-value"},
            {"downLimitEnable": "true", "upLimitEnable": False,
             "upLimit": 123, "isDefault": None},
            {"upLimitEnable": True, "upLimit": None},
        ])
        down = result["directional_coverage"]["downstream"]
        self.assertEqual(down["enable_counts"], {
            "enabled": 1, "disabled": 0, "missing": 1, "invalid": 1,
        })
        self.assertEqual(down["enabled_limit_coverage"], {
            "reported": 1, "valid": 0, "missing": 0, "invalid": 1,
        })
        up = result["directional_coverage"]["upstream"]
        self.assertEqual(up["enabled_limit_coverage"]["missing"], 1)
        self.assertEqual(up["enabled_limit_coverage"]["invalid"], 1)
        self.assertEqual(result["default_profile_counts"]["invalid"], 2)
        self.assertEqual(result["default_profile_counts"]["missing"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private_field_name", repr(result))
        self.assertNotIn("private-value", repr(result))

    def test_empty_list_and_malformed_rows_are_bounded_and_redacted(self):
        empty = summarize_hotspot_rate_limit_profiles([])
        self.assertEqual(empty["profile_count"], 0)
        self.assertFalse(empty["partial"])
        result = summarize_hotspot_rate_limit_profiles([None, {"name": "secret", **{
            "x" + str(i): i for i in range(16)
        }}])
        self.assertEqual(result["invalid_profile_count"], 2)
        self.assertTrue(result["partial"])
        self.assertNotIn("secret", repr(result))
        with self.assertRaises(SiteHotspotRateLimitProfilesError):
            summarize_hotspot_rate_limit_profiles([{}] * 1001)
        with self.assertRaises(SiteHotspotRateLimitProfilesError):
            summarize_hotspot_rate_limit_profiles({"data": []})

    def test_client_binds_fixed_get_to_inventory_site_and_redacts_rows(self):
        client = self.client()
        profiles = [{"id": "secret-id", "name": "secret-name", "site": "secret-site",
                     "downLimitEnable": True, "downLimit": 512,
                     "upLimitEnable": False, "upLimit": 777, "isDefault": True}]
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": profiles}) as request:
            result = client.read_site_hotspot_rate_limit_profiles_summary("a" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/hotspot/sites/controller-site/setting/profiles/rateLimits",
            token="test-token")
        self.assertEqual(result["directional_coverage"]["downstream"]["enabled_limit_kbps"]["sum"], 512)
        self.assertEqual(result["directional_coverage"]["upstream"]["enabled_limit_kbps"]["count"], 0)
        self.assertEqual(result["status"], "ok")
        for private in ("secret-id", "secret-name", "secret-site", "site_ref"):
            self.assertNotIn(private, repr(result))
        self.assertEqual(result["resource"], "site_hotspot_rate_limit_profiles_summary")
        with patch.object(client, "_request_json") as no_request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_hotspot_rate_limit_profiles_summary("b" * 24)
        no_request.assert_not_called()

    def test_http_transport_allowlists_only_documented_site_route_and_errors_survive(self):
        client = self.client()
        response = {"errorCode": 0, "result": [{
            "name": "private", "downLimitEnable": True, "downLimit": 321,
            "upLimitEnable": False, "upLimit": 900, "isDefault": True,
        }]}
        connection = FakeConnection(response)
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_connection", return_value=connection):
            result = client.read_site_hotspot_rate_limit_profiles_summary("a" * 24)
        self.assertEqual(connection.request_args[:3], (
            "GET", "/openapi/v1/ctrl/hotspot/sites/controller-site/setting/profiles/rateLimits", None))
        self.assertEqual(result["profile_count"], 1)
        self.assertNotIn("private", repr(result))
        wrong_connection = FakeConnection(response)
        with patch.object(client, "_connection", return_value=wrong_connection) as factory:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", "/openapi/v1/other/hotspot/sites/controller-site/setting/profiles/rateLimits")
        factory.assert_not_called()
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=OpenApiError(
                    "openapi_rejected", upstream_error_code=-33004,
                    upstream_http_status=200)):
            with self.assertRaises(OpenApiError) as caught:
                client.read_site_hotspot_rate_limit_profiles_summary("a" * 24)
        self.assertEqual(caught.exception.upstream_error_code, -33004)
        self.assertEqual(caught.exception.upstream_http_status, 200)


if __name__ == "__main__":
    unittest.main()
