import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ApPortsIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64,
        ))
        self.site_ref = "a" * 24
        self.ap_ref = "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-id"
        self.client._device_macs_by_site_ref[self.site_ref] = {self.ap_ref: "aa:bb:cc:dd:ee:ff"}

    def test_site_and_inventory_bound_fixed_route(self) -> None:
        rows = [{"port": 1, "linkStatus": 1, "linkSpeed": 3, "uplinkPort": True}]
        with patch.object(self.client, "_access_token", return_value="token"), \
             patch.object(self.client, "_request_json", return_value={"errorCode": 0, "result": rows}) as request:
            result = self.client.list_ap_ports(self.site_ref, self.ap_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-id/aps/aa:bb:cc:dd:ee:ff/ports", token="token")
        self.assertEqual(result["resource"], "ap_ports")
        self.assertEqual(result["summary"]["uplink_ports"], 1)

    def test_rejects_unknown_site_or_ap_and_bad_response(self) -> None:
        with self.assertRaises(OpenApiError):
            self.client.list_ap_ports("c" * 24, self.ap_ref)
        with patch.object(self.client, "_request_json", return_value={"errorCode": 0, "result": {}}), \
             patch.object(self.client, "_access_token", return_value="token"):
            with self.assertRaises(OpenApiError):
                self.client.list_ap_ports(self.site_ref, self.ap_ref)

    def test_transport_allows_only_the_exact_fixed_path(self) -> None:
        path = "/openapi/v1/ctrl/sites/site-id/aps/aa:bb:cc:dd:ee:ff/ports"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", path + "?include=private")


if __name__ == "__main__":
    unittest.main()
