from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wifi_calling_top_ssid_summary import (
    MAX_TOP_SSID_ROWS, WifiCallingTopSsidError,
    project_site_wifi_calling_top_ssid_summary,
)

SITE_REF = "a" * 24


def complete_row():
    return {
        "clientName": "redact-client", "apName": "redact-ap", "apMac": "redact-ap-mac",
        "clientMac": "redact-client-mac", "ip": "redact-ip", "carrierName": "redact-carrier",
        "wifiCallingProfileName": "redact-profile", "priority": 2, "ssid": "redact-ssid",
        "band": 5, "domain": "redact-domain", "totalTraffic": 101,
        "trafficDown": 61, "trafficUp": 40, "startTime": 1_799_913_600,
        "endTime": 1_800_000_000, "callNum": 3, "deviceType": "redact-device",
        "model": "redact-model",
    }


class WifiCallingTopSsidProjectionTests(unittest.TestCase):
    def test_counts_documented_field_coverage_without_returning_values(self):
        result = project_site_wifi_calling_top_ssid_summary({"topKSsids": [complete_row()]})
        self.assertEqual(result["top_ssid_source_state"], "present")
        self.assertEqual(result["top_ssid_row_count"], 1)
        self.assertEqual(result["documented_field_count"], 19)
        self.assertEqual(result["documented_field_observed_count"], 19)
        self.assertEqual(result["documented_field_presence_count"], 19)
        self.assertEqual(result["documented_field_missing_count"], 0)
        self.assertEqual(result["documented_field_type_valid_count"], 19)
        self.assertEqual(result["rows_with_all_documented_fields_count"], 1)
        self.assertFalse(result["partial"])
        encoded = json.dumps(result)
        for marker in ("redact-client", "redact-ap", "redact-ssid", "redact-domain",
                       "redact-ip", "redact-client-mac", "redact-profile", "redact-model",
                       "101", "1799913600"):
            self.assertNotIn(marker, encoded)

    def test_empty_missing_invalid_and_oversized_sources_remain_distinct(self):
        empty = project_site_wifi_calling_top_ssid_summary({"topKSsids": []})
        missing = project_site_wifi_calling_top_ssid_summary({"data": []})
        invalid = project_site_wifi_calling_top_ssid_summary({"topKSsids": None})
        large = project_site_wifi_calling_top_ssid_summary(
            {"topKSsids": [{} for _ in range(MAX_TOP_SSID_ROWS + 1)]})
        self.assertEqual(empty["top_ssid_source_state"], "empty")
        self.assertEqual(empty["top_ssid_row_count"], 0)
        self.assertFalse(empty["partial"])
        self.assertEqual(missing["top_ssid_source_state"], "missing")
        self.assertIsNone(missing["top_ssid_row_count"])
        self.assertTrue(missing["partial"])
        self.assertEqual(invalid["top_ssid_source_state"], "invalid")
        self.assertIsNone(invalid["top_ssid_row_count"])
        self.assertEqual(large["top_ssid_source_state"], "too_large")
        self.assertEqual(large["top_ssid_row_count"], MAX_TOP_SSID_ROWS + 1)
        self.assertTrue(large["partial"])

    def test_invalid_row_types_and_unknown_fields_are_only_counted(self):
        row = complete_row()
        row["priority"] = True
        row["ssid"] = "redact-ssid-invalid"
        row["futureField"] = "redact-unknown"
        result = project_site_wifi_calling_top_ssid_summary({"topKSsids": [None, row]})
        self.assertEqual(result["top_ssid_source_state"], "invalid")
        self.assertEqual(result["invalid_row_count"], 1)
        self.assertEqual(result["documented_field_type_invalid_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("redact-ssid-invalid", json.dumps(result))
        self.assertNotIn("redact-unknown", json.dumps(result))

    def test_non_object_result_is_rejected(self):
        with self.assertRaises(WifiCallingTopSsidError):
            project_site_wifi_calling_top_ssid_summary([])


class WifiCallingTopSsidClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "/tmp/client-id",
            "/tmp/client-secret", cert_sha256="a" * 64,
        ))
        self.client._site_ids_by_ref[SITE_REF] = "site-1"

    def test_uses_one_fixed_site_bound_top_list_get_with_seconds_and_disabled_sources(self):
        with patch("app.openapi.time.time", return_value=1_800_000_000), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": {"topKSsids": [complete_row()]},
                }) as request:
            result = self.client.read_site_wifi_calling_top_ssid_summary(SITE_REF)
        request.assert_called_once()
        method, path = request.call_args.args[:2]
        self.assertEqual(method, "GET")
        self.assertEqual(urlsplit(path).path,
                         "/openapi/v1/controller_1/sites/site-1/profiles/wifi-calling/grid/summary")
        query = dict(parse_qsl(urlsplit(path).query))
        self.assertEqual(query, {
            "filters.timeStart": "1799913600", "filters.timeEnd": "1800000000",
            "topK": "10", "queryTopSsid": "true", "queryTopEPDG": "false",
            "queryClients": "false", "queryClientsByMac": "false", "page": "1",
            "pageSize": "1",
        })
        self.assertEqual(request.call_args.kwargs, {"token": "token"})
        self.assertEqual(result["resource"], "site_wifi_calling_top_ssid_summary")
        self.assertEqual(result["top_ssid_row_count"], 1)
        self.assertNotIn(SITE_REF, json.dumps(result))
        self.assertEqual(dict(OmadaOpenApiClient.CAPABILITY_OPERATIONS)[
            "site_wifi_calling_top_ssid_summary"],
            "GET /v1/sites/{site_ref}/wifi-calling/top-ssid/summary")

    def test_invalid_top_ssid_source_is_separately_redacted(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": {"topKSsids": "private-source"},
                }) as request:
            result = self.client.read_site_wifi_calling_top_ssid_summary(SITE_REF)
        self.assertEqual(result["top_ssid_source_state"], "invalid")
        self.assertTrue(result["partial"])
        self.assertNotIn("private-source", json.dumps(result))
        self.assertEqual(request.call_count, 1)

    def test_fixed_path_guard_rejects_extra_or_changed_query_and_other_controller(self):
        valid = ("/openapi/v1/controller_1/sites/site-1/profiles/wifi-calling/grid/summary"
                 "?filters.timeStart=1799913600&filters.timeEnd=1800000000&topK=10"
                 "&queryTopSsid=true&queryTopEPDG=false&queryClients=false"
                 "&queryClientsByMac=false&page=1&pageSize=1")
        self.assertTrue(self.client._site_wifi_calling_top_ssid_request_valid(valid))
        for invalid in (
            valid + "&searchKey=x",
            valid.replace("queryClients=false", "queryClients=true"),
            valid.replace("pageSize=1", "pageSize=2"),
            valid.replace("filters.timeEnd=1800000000", "filters.timeEnd=1800000001"),
            valid.replace("controller_1", "other-controller"),
        ):
            self.assertFalse(self.client._site_wifi_calling_top_ssid_request_valid(invalid))

    def test_unknown_site_fails_before_request(self):
        with patch.object(self.client, "_access_token") as token, \
                patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_wifi_calling_top_ssid_summary("b" * 24)
        token.assert_not_called()
        request.assert_not_called()
