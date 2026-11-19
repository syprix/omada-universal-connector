from __future__ import annotations

import unittest
from unittest.mock import patch

from app.gateway_info_summary import GatewayInfoSummaryError, project_gateway_info
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


def gateway_info(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "mac": "00:11:22:33:44:55", "showModel": "Gateway Model X",
        "firmwareVersion": "1.2.3", "ip": "192.0.2.1", "uptime": "1 day",
        "temp": 45, "cpuUtil": 8, "memUtil": 32,
        "ipv6List": ["2001:db8::1"], "lastSeen": 1_790_000_000_000,
        "portConfigs": [{"port": 1, "linkSpeed": 1000}],
        "multiChipGateway": False, "multiChipInfos": [],
    }
    value.update(updates)
    return value


class GatewayInfoSummaryTests(unittest.TestCase):
    def test_projects_only_documented_model_version_and_last_seen_fields(self) -> None:
        result = project_gateway_info(gateway_info())
        self.assertEqual(result["data"], {
            "model": "Gateway Model X", "firmware_version": "1.2.3",
            "last_seen_source_value": 1_790_000_000_000,
        })
        self.assertFalse(result["partial"])
        rendered = repr(result)
        for private_value in ("00:11:22:33:44:55", "192.0.2.1", "2001:db8::1"):
            self.assertNotIn(private_value, rendered)
        for omitted in ("cpu", "temperature", "port_config", "uptime"):
            self.assertNotIn(omitted, rendered)

    def test_missing_invalid_and_unknown_fields_are_visible_without_echoing_values(self) -> None:
        result = project_gateway_info({
            "showModel": "Model\nwith text", "firmwareVersion": 5,
            "lastSeen": True, "futureField": "private value",
        })
        self.assertEqual(result["data"], {
            "model": None, "firmware_version": None, "last_seen_source_value": None,
        })
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private value", repr(result))

    def test_missing_fields_and_unknown_schema_fields_are_partial(self) -> None:
        result = project_gateway_info({"showModel": "Model X"})
        self.assertEqual(result["missing_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 0)
        self.assertTrue(result["partial"])

    def test_rejects_unbounded_outer_shapes(self) -> None:
        for value in (None, [], {str(index): index for index in range(33)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(GatewayInfoSummaryError):
                project_gateway_info(value)

    def test_client_uses_only_a_gateway_reference_from_site_inventory(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        site_ref, device_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._gateway_macs_by_site_ref[site_ref] = {device_ref: "00:11:22:33:44:55"}
        seen = []

        def request(method: str, path: str, **kwargs: object) -> dict[str, object]:
            seen.append((method, path))
            return {"result": gateway_info()}

        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=request):
            summary = client.read_gateway_info_summary(site_ref, device_ref)
        self.assertEqual(seen, [("GET", "/openapi/v1/ctrl/sites/site_1/gateways/00:11:22:33:44:55")])
        self.assertEqual(summary["device_ref"], device_ref)
        self.assertNotIn("00:11:22:33:44:55", repr(summary))
        self.assertNotIn("192.0.2.1", repr(summary))
        with self.assertRaisesRegex(OpenApiError, "gateway_ref_unknown"):
            client.read_gateway_info_summary(site_ref, "c" * 24)

    def test_fixed_read_path_allowlist(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", "/openapi/v1/ctrl/sites/site_1/gateways/00-11-22-33-44-55")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            client._request_json("GET", "/openapi/v1/other/sites/site_1/gateways/00-11-22-33-44-55")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            client._request_json("GET", "/openapi/v1/ctrl/sites/site_1/gateways/00-11-22-33-44-55/extra")


if __name__ == "__main__":
    unittest.main()
