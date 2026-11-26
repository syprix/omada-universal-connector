import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SiteBluetoothAdvertisingV2IntegrationTests(unittest.TestCase):
    def test_uses_fixed_pinned_site_page_and_redacted_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {
            "totalRows": 1, "currentPage": 1, "currentSize": 100,
            "data": [{"id": "private-id", "name": "private-name",
                      "boundDeviceNum": 2, "enable": True, "uuid": "private-uuid",
                      "macList": ["private-mac"],
                      "selectMacInfo": [{"mac": "private-ap-mac"}],
                      "transmitPower": 17}],
        }
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="synthetic-token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_bluetooth_advertising_v2_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v2/ctrl/sites/" + site_ref
            + "/setting/iot/devices/config?page=1&pageSize=100", token="synthetic-token")
        rendered = repr(result)
        for marker in ("private-id", "private-name", "private-uuid", "private-mac",
                       "private-ap-mac", "transmit_power"):
            self.assertNotIn(marker, rendered)
        self.assertEqual(result["data"]["observed_row_count"], 1)

    def test_request_guard_rejects_other_controller_and_unbounded_query(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site = "a" * 24
        valid = f"/openapi/v2/ctrl/sites/{site}/setting/iot/devices/config?page=1&pageSize=100"
        self.assertTrue(client._site_bluetooth_advertising_v2_request_valid(valid))
        self.assertFalse(client._site_bluetooth_advertising_v2_request_valid(
            valid.replace("/v2/ctrl/", "/v2/other/")))
        self.assertFalse(client._site_bluetooth_advertising_v2_request_valid(
            valid.replace("pageSize=100", "pageSize=1000")))
        self.assertFalse(client._site_bluetooth_advertising_v2_request_valid(
            valid + "&page=2"))

    def test_unknown_site_binding_stops_before_upstream_request(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref = {}
        with patch.object(client, "_access_token") as token, \
                patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_bluetooth_advertising_v2_summary("a" * 24)
        token.assert_not_called()
        request.assert_not_called()

    def test_real_transport_guard_accepts_only_the_pinned_read_route(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref = {site_ref: "site-internal"}

        class Response:
            status = 200

            def read(self, _limit):
                return (b'{"errorCode":0,"result":{"totalRows":0,'
                        b'"currentPage":1,"currentSize":100,"data":[]}}')

            def getheader(self, _name, _default=""):
                return "application/json"

        class Connection:
            _omada_tls_verified = True

            def __init__(self):
                self.requests = []
                self.closed = False

            def request(self, method, path, body=None, headers=None):
                self.requests.append((method, path, body, headers))

            def getresponse(self):
                return Response()

            def close(self):
                self.closed = True

        conn = Connection()
        with patch.object(client, "_access_token", return_value="synthetic-token"), \
                patch.object(client, "_connection", return_value=conn):
            result = client.read_site_bluetooth_advertising_v2_summary(site_ref)
        self.assertFalse(result["partial"])
        self.assertEqual(len(conn.requests), 1)
        self.assertEqual(
            conn.requests[0][1],
            "/openapi/v2/ctrl/sites/site-internal/setting/iot/devices/config?page=1&pageSize=100",
        )
        self.assertTrue(conn.closed)
        bad = Connection()
        with patch.object(client, "_connection", return_value=bad) as connect:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json(
                    "GET",
                    "/openapi/v2/ctrl/sites/site-internal/setting/iot/devices/config?page=2&pageSize=100",
                    token="synthetic-token",
                )
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
