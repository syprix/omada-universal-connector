from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wan_max_speed_summary import (
    SiteWanMaxSpeedError, project_site_wan_max_speed,
)


class SiteWanMaxSpeedProjectionTests(unittest.TestCase):
    def test_preserves_documented_int32_values_and_unknown_unit(self) -> None:
        result = project_site_wan_max_speed({"upstream": 0, "downstream": 125000})
        self.assertEqual(result["data"], {
            "upstream": 0, "downstream": 125000, "unit": "unspecified_by_source"})
        self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_fields_are_counted(self) -> None:
        result = project_site_wan_max_speed({
            "upstream": True, "downstream": -(2 ** 31) - 1, "extra": "private"})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_missing_fields_are_partial_and_bad_outer_shapes_rejected(self) -> None:
        result = project_site_wan_max_speed({"upstream": 42})
        self.assertEqual(result["missing_field_count"], 1)
        self.assertIsNone(result["data"]["downstream"])
        for value in (None, [], {str(i): i for i in range(17)}):
            with self.subTest(value=type(value).__name__), \
                    self.assertRaises(SiteWanMaxSpeedError):
                project_site_wan_max_speed(value)


class SiteWanMaxSpeedClientTests(unittest.TestCase):
    def test_uses_inventoried_explicit_port_and_required_query_parameter(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        port_id = "port /&1"
        port_ref = client._opaque_ref("wan-port", site_ref + ":" + port_id)
        calls = []

        def request(method, path, **kwargs):
            calls.append((method, path, kwargs["token"]))
            if path.endswith("/internet/ports-config"):
                return {"result": {"wanPortsConfig": [{"portId": port_id}]}}
            return {"result": {"upstream": 5, "downstream": 8}}

        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=request):
            result = client.read_site_wan_max_speed_summary(site_ref, port_ref)
        self.assertEqual(calls, [
            ("GET", "/openapi/v1/ctrl/sites/site_internal/internet/ports-config", "token"),
            ("GET", "/openapi/v1/ctrl/sites/site_internal/wan-max-speed?wanId=port+%2F%261", "token"),
        ])
        self.assertEqual(result["data"]["upstream"], 5)
        self.assertEqual(result["data"]["unit"], "unspecified_by_source")
        self.assertEqual(result["wan_port_ref"], port_ref)
        self.assertNotIn(port_id, repr(result))

    def test_rejects_unknown_selection_without_calling_max_speed(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={
                    "result": {"wanPortsConfig": [{"portId": "another_port"}]}}) as request:
            with self.assertRaisesRegex(OpenApiError, "wan_port_ref_unknown"):
                client.read_site_wan_max_speed_summary(site_ref, "1" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/internet/ports-config", token="token")

    def test_request_guard_requires_one_canonical_wan_id(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.assertTrue(client._site_wan_max_speed_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/wan-max-speed?wanId=port+%2F%261"))
        for path in (
            "/openapi/v1/ctrl/sites/site_internal/wan-max-speed",
            "/openapi/v1/ctrl/sites/site_internal/wan-max-speed?other=x",
            "/openapi/v1/ctrl/sites/site_internal/wan-max-speed?wanId=x&wanId=y",
            "/openapi/v1/other/sites/site_internal/wan-max-speed?wanId=x",
            "/openapi/v1/ctrl/sites/site_internal/wan-max-speed?wanId=x,y",
        ):
            with self.subTest(path=path):
                self.assertFalse(client._site_wan_max_speed_request_valid(path))

    def test_request_json_accepts_only_the_fixed_selected_port_query_offline(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", "/openapi/v1/ctrl/sites/site_internal/wan-max-speed?wanId=port-1", token="token")
        for path in (
            "/openapi/v1/ctrl/sites/site_internal/wan-max-speed",
            "/openapi/v1/ctrl/sites/site_internal/wan-max-speed?other=port-1",
            "/openapi/v1/ctrl/sites/site_internal/wan-max-speed?wanId=port-1#fragment",
        ):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", path, token="token")


if __name__ == "__main__":
    unittest.main()
