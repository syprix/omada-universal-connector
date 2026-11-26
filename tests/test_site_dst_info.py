import json
import unittest
from unittest.mock import patch

from app.mcp import handle_mcp_request
from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient


class FakeResponse:
    status = 200

    def __init__(self, payload):
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


class SiteDstInfoTests(unittest.TestCase):
    def client(self):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64,
        ))

    def test_fixed_get_uses_same_site_inventory_binding_and_dst_projection(self):
        client = self.client()
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_read_pages", return_value=[{"siteId": "site-safe"}]), \
                patch.object(client, "_request_json", return_value={"result": {
                    "enable": True, "status": True, "mode": 2, "offset": 3_600_000,
                    "timeZone": "Europe/Berlin", "start": {
                        "month": 3, "serial": 5, "day": 7, "hour": 2, "minute": 0},
                    "end": {"month": 10, "serial": 5, "day": 7, "hour": 3, "minute": 0},
                    "startTime": 1_800_000_000_000, "endTime": 1_810_000_000_000,
                    "nextStart": 1_900_000_000_000, "nextEnd": 1_920_000_000_000,
                    "lastStart": 1_700_000_000_000, "lastEnd": 1_710_000_000_000}}) as target:
            site = client.list_sites()["items"][0]
            result = client.read_site_dst_info(site["site_ref"])
        target.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/dst-info", token="test-token")
        self.assertEqual(result["resource"], "site_dst_info")
        self.assertEqual(result["site_ref"], site["site_ref"])
        self.assertTrue(result["data"]["settings"]["enabled"])
        self.assertEqual(result["data"]["settings"]["time_zone"], "Europe/Berlin")
        self.assertEqual(result["data"]["timestamps_unit_unspecified"], {
            "startTime": 1_800_000_000_000, "endTime": 1_810_000_000_000})
        self.assertEqual(result["data"]["timestamps_ms"]["nextStart"], 1_900_000_000_000)
        self.assertNotIn("startTime", result["data"]["timestamps_ms"])
        self.assertFalse(result["partial"])

    def test_site_timestamp_unit_unknown_mixed_missing_and_invalid(self):
        client = self.client()
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "enable": True, "startTime": 123, "endTime": "not-an-integer",
                    "nextStart": 456}}):
            result = client.read_site_dst_info(site_ref)
        self.assertEqual(result["data"]["timestamps_unit_unspecified"], {
            "startTime": 123})
        self.assertEqual(result["data"]["timestamps_ms"], {"nextStart": 456})
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["timestamps_unit_unspecified"].keys(), {"startTime"})

        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "enable": True, "endTime": "invalid"}}):
            missing = client.read_site_dst_info(site_ref)
        self.assertEqual(missing["data"]["timestamps_unit_unspecified"], {})
        self.assertEqual(missing["data"]["timestamps_ms"], {})
        self.assertTrue(missing["partial"])

    def test_false_and_sparse_disabled_response_remains_valid(self):
        client = self.client()
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={
                    "result": {"enable": False}}):
            result = client.read_site_dst_info(site_ref)
        self.assertFalse(result["data"]["settings"]["enabled"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["missing_count"], 12)

    def test_malformed_and_unexpected_fields_are_partial_and_redacted(self):
        client = self.client()
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "enable": "yes", "timeZone": "private-zone-value",
                    "unknown": "private-field-value"}}):
            result = client.read_site_dst_info(site_ref)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("private-field-value", repr(result))

    def test_invalid_or_unbound_site_stops_before_target_request(self):
        client = self.client()
        with patch.object(client, "_request_json") as target:
            for site_ref, error in (("bad-ref", "site_ref_invalid"),
                                    ("a" * 24, "site_ref_unknown")):
                with self.subTest(error=error):
                    with self.assertRaisesRegex(OpenApiError, error):
                        client.read_site_dst_info(site_ref)
            target.assert_not_called()

    def test_pinned_route_rejects_other_controller_and_other_method(self):
        client = self.client()
        for method, path in (
            ("GET", "/openapi/v1/other/sites/site-safe/dst-info"),
            ("POST", "/openapi/v1/ctrl/sites/site-safe/dst-info"),
            ("GET", "/openapi/v1/ctrl/sites/site-safe/dst-info?x=1"),
        ):
            with self.subTest(method=method, path=path):
                with patch.object(client, "_connection") as connection:
                    with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                        client._request_json(method, path)
                    connection.assert_not_called()

    def test_registry_is_fixed_site_bound_read_and_available_via_mcp(self):
        site_ref = "a" * 24
        operation = REGISTRY.get("site_dst_info")
        self.assertEqual(operation.public_template, "/v1/sites/{site_ref}/dst-info")
        self.assertEqual(operation.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/dst-info")
        route, bindings = REGISTRY.match("GET", f"/v1/sites/{site_ref}/dst-info")
        self.assertEqual(route.operation_id, "site_dst_info")
        self.assertEqual(dict(bindings), {"site_ref": site_ref})
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", f"/v1/sites/{site_ref}/dst-info")
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        page = handle_mcp_request(request, None, REGISTRY, lambda *_: {})["result"]
        tools = list(page["tools"])
        while "nextCursor" in page:
            page = handle_mcp_request({**request, "params": {
                "cursor": page["nextCursor"]}}, None, REGISTRY, lambda *_: {})["result"]
            tools.extend(page["tools"])
        tool = next(item for item in tools if item["name"] == "omada_site_dst_info")
        self.assertEqual(tool["inputSchema"]["required"], ["site_ref"])
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        calls = []
        def invoke(operation_id, arguments):
            calls.append((operation_id, arguments))
            return {"status": "ok", "resource": operation_id, "site_ref": site_ref,
                    "data": {"settings": {"enabled": False}}, "partial": False}
        result = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "omada_site_dst_info", "arguments": {
                "site_ref": site_ref}}}, None, REGISTRY, invoke)
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(calls, [("site_dst_info", {"site_ref": site_ref})])


if __name__ == "__main__":
    unittest.main()
