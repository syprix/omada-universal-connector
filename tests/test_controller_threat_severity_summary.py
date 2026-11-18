import unittest
import json
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class _Response:
    status = 200

    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def read(self, _limit=-1):
        return self.body

    def getheader(self, name, default=""):
        return "application/json" if name.lower() == "content-type" else default


class _Connection:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, path, body=None, headers=None):
        self.calls.append((method, path, body, headers or {}))

    def getresponse(self):
        return self.response

    def close(self):
        pass


class ControllerThreatSeveritySummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "client-id-file",
            "client-secret-file", cert_sha256="a" * 64))

    def test_projects_only_documented_counts_and_preserves_window(self):
        start_ms, end_ms = 1_794_903_300_000, 1_794_904_500_000
        response = {"result": {"critical": 1, "major": 2, "moderate": 3,
                               "minor": 4, "low": 5,
                               "privateThreatList": ["do-not-return"]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_controller_threat_severity_summary(start_ms, end_ms)
        self.assertEqual(request.call_args.args[:2], (
            "GET", "/openapi/v1/controller_1/security/threat-management/severity"
            "?startTime=1794903300000&endTime=1794904500000"))
        self.assertEqual(result, {
            "status": "ok", "resource": "controller_threat_severity_summary",
            "counts": {"critical": 1, "major": 2, "moderate": 3, "minor": 4, "low": 5},
            "partial": False,
        })
        self.assertNotIn("privateThreatList", repr(result))

    def test_fixed_transport_allowlist_accepts_only_the_upstream_read(self):
        start_ms, end_ms = 1_794_903_300_000, 1_794_904_500_000
        connection = _Connection(_Response({"errorCode": 0, "result": {
            "critical": 1, "major": 2, "moderate": 3, "minor": 4, "low": 5}}))
        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_connection", return_value=connection):
            result = self.client.read_controller_threat_severity_summary(start_ms, end_ms)
        self.assertEqual(result["counts"]["critical"], 1)
        self.assertEqual(connection.calls[0][:2], (
            "GET", "/openapi/v1/controller_1/security/threat-management/severity"
            "?startTime=1794903300000&endTime=1794904500000"))

    def test_missing_fields_are_unknown_and_mark_partial(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"critical": 0}}):
            result = self.client.read_controller_threat_severity_summary(1_794_903_300_000,
                                                                           1_794_904_500_000)
        self.assertTrue(result["partial"])
        self.assertEqual(result["counts"], {
            "critical": 0, "major": None, "moderate": None, "minor": None, "low": None,
        })

    def test_rejects_invalid_counts_windows_and_request_paths(self):
        for value in (True, -1, "2", 1.5):
            with self.subTest(value=value), patch.object(
                    self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": {"critical": value}}):
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    self.client.read_controller_threat_severity_summary(
                        1_794_903_300_000, 1_794_904_500_000)
        for start_ms, end_ms in ((True, 1_794_904_500_000),
                                 (1_794_904_500_000, 1_794_903_300_000),
                                 (1_794_903_300_000, 1_794_903_300_000 + 86_400_001)):
            with self.subTest(start_ms=start_ms, end_ms=end_ms), self.assertRaisesRegex(
                    OpenApiError, "threat_time_window_invalid"):
                self.client.read_controller_threat_severity_summary(start_ms, end_ms)
        for path in (
            "/openapi/v1/other/security/threat-management/severity?startTime=1794903300000&endTime=1794904500000&extra=x",
            "/openapi/v1/controller_1/security/threat-management/severity?startTime=1794903300000&endTime=1794904500000&extra=x",
            "/openapi/v1/controller_1/security/threat-management/severity?startTime=1794904500000&endTime=1794903300000",
        ):
            self.assertFalse(self.client._controller_threat_severity_request_valid(path))


if __name__ == "__main__":
    unittest.main()
