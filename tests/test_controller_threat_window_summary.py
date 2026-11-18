import json
import unittest
from unittest.mock import patch

from app.controller_threat_window_summary import (
    ThreatWindowError, summarize_threat_rows,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF = "a" * 24


class _Response:
    status = 200

    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def read(self, _limit=-1):
        return self.body

    def getheader(self, name, default=""):
        return "application/json" if name.lower() == "content-type" else default


class _Connection:
    def __init__(self, payload):
        self.response = _Response(payload)
        self.calls = []

    def request(self, method, path, body=None, headers=None):
        self.calls.append((method, path, body, headers or {}))

    def getresponse(self):
        return self.response

    def close(self):
        pass


class ControllerThreatWindowSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "client-id-file",
            "client-secret-file", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_7"

    def test_projection_keeps_only_severity_counts_and_time_bounds(self):
        result = summarize_threat_rows([
            {"time": 1794903300, "severity": 0, "srcIp": "192.0.2.1", "id": "secret"},
            {"time": 1794904500, "severity": 3, "classification": "private"},
            {"time": 1794904000, "severity": 9, "signature": "private"},
        ], 1794903300, 1794904500, 3, archived=False, max_items=10000)
        self.assertEqual(result["counts"]["critical"], 1)
        self.assertEqual(result["counts"]["minor"], 1)
        self.assertEqual(result["unknown_severity"], 1)
        self.assertEqual((result["first_event_s"], result["last_event_s"]),
                         (1794903300, 1794904500))
        self.assertFalse(result["partial"])
        self.assertNotIn("srcIp", repr(result))
        self.assertNotIn("classification", repr(result))

    def test_missing_rows_are_partial_and_invalid_rows_fail_closed(self):
        result = summarize_threat_rows([], 10, 20, 1, archived=True, max_items=10000)
        self.assertTrue(result["partial"])
        with self.assertRaises(ThreatWindowError):
            summarize_threat_rows([{"time": True, "severity": 0}], 10, 20, 1,
                                  archived=False, max_items=10000)

    def test_source_call_is_site_bound_and_returns_aggregate_only(self):
        payload = {"result": {"totalRows": 2, "data": [
            {"time": 1794903300, "severity": 0, "srcIp": "192.0.2.4", "id": "secret"},
            {"time": 1794904500, "severity": 2, "dstIp": "192.0.2.9"},
        ]}}
        connection = _Connection({"errorCode": 0, **payload})
        start_ms, end_ms = 1794903300000, 1794904500000
        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_connection", return_value=connection):
            result = self.client.read_site_threat_window_summary(
                SITE_REF, start_ms, end_ms, archived=True)
        self.assertEqual(connection.calls[0][:2], (
            "GET", "/openapi/v1/controller_1/security/threat-management"
            "?siteList=site_7&archived=true&page=1&pageSize=1000"
            "&filters.startTime=1794903300&filters.endTime=1794904500"))
        self.assertEqual(result["counts"]["critical"], 1)
        self.assertEqual(result["counts"]["moderate"], 1)
        self.assertEqual(result["site_ref"], SITE_REF)
        self.assertNotIn("srcIp", repr(result))
        self.assertNotIn("secret", repr(result))

    def test_page_cap_marks_truncation_and_rejects_bad_source_shape(self):
        page = [{"time": 1794903300, "severity": 1} for _ in range(1000)]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"totalRows": 10001, "data": page}}) as request:
            result = self.client.read_site_threat_window_summary(
                SITE_REF, 1794903300000, 1794904500000)
        self.assertEqual(request.call_count, 10)
        self.assertTrue(result["partial"])
        self.assertEqual(result["returned_rows"], 10000)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"totalRows": 1, "data": [{"time": 1, "severity": 0}]}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_threat_window_summary(
                    SITE_REF, 1794903300000, 1794904500000)

    def test_window_site_and_request_guards(self):
        for start_ms, end_ms in ((True, 1794904500000),
                                 (1794904500000, 1794903300000),
                                 (1794903300000, 1794989700001)):
            with self.subTest(start_ms=start_ms, end_ms=end_ms), self.assertRaises(
                    OpenApiError):
                self.client.read_site_threat_window_summary(SITE_REF, start_ms, end_ms)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_threat_window_summary("b" * 24, 1794903300000,
                                                        1794904500000)
        for path in (
            "/openapi/v1/controller_1/security/threat-management?siteList=site_7&archived=false&page=1&pageSize=1000&filters.startTime=1794903300&filters.endTime=1794904500&extra=x",
            "/openapi/v1/controller_1/security/threat-management?siteList=site_7&archived=false&page=0&pageSize=1000&filters.startTime=1794903300&filters.endTime=1794904500",
        ):
            self.assertFalse(self.client._site_threat_window_request_valid(path))


if __name__ == "__main__":
    unittest.main()
