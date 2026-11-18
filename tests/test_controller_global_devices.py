from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerGlobalDeviceReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64,
            page_size=32))

    def test_known_and_unknown_device_reads_use_fixed_bounded_pages(self) -> None:
        payload = {"data": [{"mac": "secret-mac", "name": "secret-name", "ip": "10.0.0.2",
                             "type": "ap", "status": 1, "deviceSeriesType": 1}],
                   "totalRows": 4, "currentPage": 1, "currentSize": 1}
        for method, suffix, resource in (
            (self.client.read_controller_known_devices, "known-devices", "controller_known_devices"),
            (self.client.read_controller_unknown_devices, "unknown-devices", "controller_unknown_devices"),
        ):
            with self.subTest(resource=resource), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
                result = method()
            request.assert_called_once_with(
                "GET", f"/openapi/v1/ctrl/devices/{suffix}?page=1&pageSize=32", token="token")
            self.assertEqual(result["resource"], resource)
            self.assertTrue(result["partial"])
            for secret in ("secret-mac", "secret-name", "10.0.0.2"):
                self.assertNotIn(secret, repr(result))

    def test_fixed_page_paths_are_controller_bound_and_allowlisted(self) -> None:
        paths = (
            "/openapi/v1/ctrl/devices/known-devices?page=1&pageSize=32",
            "/openapi/v1/ctrl/devices/unknown-devices?page=1&pageSize=32",
        )
        for path in paths:
            with self.subTest(path=path), patch.object(
                    self.client, "_connection", side_effect=OpenApiError("connection_reached")):
                with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path)
        invalid_paths = (
            paths[0].replace("/ctrl/", "/other/"),
            paths[0].replace("page=1", "page=2"),
            paths[0].replace("pageSize=32", "pageSize=33"),
            paths[0] + "&sort=name",
        )
        for path in invalid_paths:
            with self.subTest(path=path), patch.object(self.client, "_connection") as connection:
                with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    self.client._request_json("GET", path)
                connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
