import unittest
from unittest.mock import patch

from app.controller_firmware_pool_channel_counts import (
    ControllerFirmwarePoolCountsError, project_firmware_pool_channel_counts,
)
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient


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


class ControllerFirmwarePoolChannelCountsTests(unittest.TestCase):
    def client(self):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64,
        ))

    @staticmethod
    def result(fw_num=None, *, total=1, page=1, size=1, data=None):
        if data is None:
            data = [{}] if total else []
        return {"result": {"totalRows": total, "currentPage": page,
                           "currentSize": size, "data": data, "fwNum": fw_num}}

    def test_projects_all_documented_counts_and_explicit_zero(self):
        result = project_firmware_pool_channel_counts({"0": 0, "1": 4, "2": 7})
        self.assertEqual(result["channel_counts"], {
            "stable": 0, "release_candidate": 4, "beta": 7,
        })
        self.assertEqual(result["reported_count"], 3)
        self.assertEqual(result["missing_count"], 0)
        self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_entries_remain_distinct(self):
        missing = project_firmware_pool_channel_counts(None)
        self.assertEqual(missing["missing_count"], 3)
        self.assertTrue(missing["partial"])
        invalid = project_firmware_pool_channel_counts({"0": True, "1": -1, "2": 1 << 31})
        self.assertEqual(invalid["reported_count"], 3)
        self.assertEqual(invalid["invalid_count"], 3)
        self.assertEqual(invalid["missing_count"], 0)
        distinct = project_firmware_pool_channel_counts({
            "0": None, "1": 0, "x-private": 9,
        })
        self.assertEqual(distinct["channel_counts"], {
            "stable": None, "release_candidate": 0, "beta": None,
        })
        self.assertEqual(distinct["reported_count"], 2)
        self.assertEqual(distinct["missing_count"], 1)
        self.assertEqual(distinct["invalid_count"], 1)
        self.assertEqual(distinct["unknown_key_count"], 1)
        self.assertNotIn("x-private", repr(distinct))
        self.assertNotIn("9", repr(distinct))
        with self.assertRaises(ControllerFirmwarePoolCountsError):
            project_firmware_pool_channel_counts([])

    def test_connector_uses_only_exact_controller_bound_request(self):
        client = self.client()
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value=self.result(
                    {"0": 1, "1": 0, "2": 3})) as request:
            result = client.read_controller_firmware_pool_channel_counts()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/upgrade/overview/firmwares?channel=0&page=1&pageSize=1",
            token="test-token")
        self.assertEqual(result["channel_counts"], {
            "stable": 1, "release_candidate": 0, "beta": 3,
        })
        self.assertTrue(client._controller_firmware_pool_channel_counts_request_valid(
            "/openapi/v1/ctrl/upgrade/overview/firmwares?channel=0&page=1&pageSize=1"))
        for path in (
            "/openapi/v1/other/upgrade/overview/firmwares?channel=0&page=1&pageSize=1",
            "/openapi/v1/ctrl/upgrade/overview/firmwares?channel=1&page=1&pageSize=1",
            "/openapi/v1/ctrl/upgrade/overview/firmwares?page=1&pageSize=1&channel=0",
            "/openapi/v1/ctrl/upgrade/overview/firmwares?channel=0&page=2&pageSize=1",
            "/openapi/v1/ctrl/upgrade/overview/firmwares?channel=0&page=1&pageSize=2",
            "/openapi/v2/ctrl/upgrade/overview/firmwares?channel=0&page=1&pageSize=1",
        ):
            with self.subTest(path=path):
                self.assertFalse(client._controller_firmware_pool_channel_counts_request_valid(path))
        with patch.object(client, "_connection") as connection_factory:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("POST",
                    "/openapi/v1/ctrl/upgrade/overview/firmwares?channel=0&page=1&pageSize=1")
        connection_factory.assert_not_called()

    def test_page_metadata_and_rows_are_bounded(self):
        client = self.client()
        malformed = (
            self.result({"0": 1}, data=[{}, {}]),
            self.result({"0": 1}, page=2),
            self.result({"0": 1}, size=2),
            self.result({"0": 1}, total=True),
            self.result({"0": 1}, page=False, total=0, size=0, data=[]),
            self.result({"0": 1}, page=1, total=0, size=1, data=[{}]),
            self.result({"0": 1}, data={}),
        )
        for payload in malformed:
            with self.subTest(payload=payload):
                with patch.object(client, "_access_token", return_value="token"), \
                        patch.object(client, "_request_json", return_value=payload):
                    with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                        client.read_controller_firmware_pool_channel_counts()

    def test_zero_empty_page_and_missing_map_are_partial_without_inference(self):
        client = self.client()
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=self.result(
                    None, total=0, page=0, size=0, data=[])):
            result = client.read_controller_firmware_pool_channel_counts()
        self.assertEqual(result["channel_counts"], {
            "stable": None, "release_candidate": None, "beta": None,
        })
        self.assertTrue(result["partial"])
        self.assertFalse(result["installed_firmware_or_upgrade_state_inferred"])
        self.assertFalse(result["firmware_details_returned"])

    def test_http_allowlist_and_upstream_error_keep_standard_transport(self):
        client = self.client()
        payload = {"errorCode": 0, "result": {
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"id": "private", "latestVersion": "private-version"}],
            "fwNum": {"0": 3, "1": 2, "2": 1},
        }}
        connection = FakeConnection(payload)
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_connection", return_value=connection):
            result = client.read_controller_firmware_pool_channel_counts()
        self.assertEqual(connection.request_args[:3], (
            "GET", "/openapi/v1/ctrl/upgrade/overview/firmwares?channel=0&page=1&pageSize=1", None))
        self.assertEqual(result["channel_counts"]["stable"], 3)
        self.assertNotIn("private", repr(result))
        denied = FakeConnection({"errorCode": -1501})
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_connection", return_value=denied):
            with self.assertRaises(OpenApiError) as caught:
                client.read_controller_firmware_pool_channel_counts()
        self.assertEqual(caught.exception.code, "openapi_rejected")
        self.assertEqual(caught.exception.upstream_error_code, -1501)
        wrong_query_connection = FakeConnection(payload)
        with patch.object(client, "_connection", return_value=wrong_query_connection) as factory:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", "/openapi/v1/ctrl/upgrade/overview/firmwares?channel=1&page=1&pageSize=1")
        factory.assert_not_called()

    def test_standard_upstream_errors_are_preserved(self):
        client = self.client()
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=OpenApiError(
                    "openapi_rejected", upstream_error_code=-1501,
                    upstream_http_status=200)):
            with self.assertRaises(OpenApiError) as caught:
                client.read_controller_firmware_pool_channel_counts()
        self.assertEqual(caught.exception.code, "openapi_rejected")
        self.assertEqual(caught.exception.upstream_error_code, -1501)


if __name__ == "__main__":
    unittest.main()
