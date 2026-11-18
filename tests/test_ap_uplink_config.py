from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_uplink_config import ApUplinkConfigError, project_ap_uplink_config
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF, AP_REF = "a" * 24, "b" * 24
AP_MAC = "00:11:22:33:44:55"


class ApUplinkConfigProjectionTests(unittest.TestCase):
    def test_projects_only_documented_auto_and_port_fields(self) -> None:
        result = project_ap_uplink_config([
            {"auto": True, "port": "1/0/3", "deviceName": "private-name"},
            {"auto": False},
        ])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["items"], [{"auto": True, "port": "1/0/3"}, {"auto": False}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private-name", repr(result))

    def test_missing_or_malformed_values_are_partial_without_inference(self) -> None:
        result = project_ap_uplink_config([{"auto": "yes", "port": "x\nsecret"}, {}])
        self.assertEqual(result["items"], [{}, {}])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_empty_is_a_bounded_empty_result_and_oversized_values_are_rejected(self) -> None:
        self.assertEqual(project_ap_uplink_config([])["items"], [])
        with self.assertRaises(ApUplinkConfigError):
            project_ap_uplink_config([{"auto": True}] * 65)
        with self.assertRaises(ApUplinkConfigError):
            project_ap_uplink_config(None)


class ApUplinkConfigClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._device_macs_by_site_ref[SITE_REF] = {AP_REF: AP_MAC}

    def test_reads_the_fixed_inventory_bound_route(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": [{"auto": True, "port": "1/0/3"}]}) as request:
            result = self.client.read_ap_uplink_config(SITE_REF, AP_REF)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site_1/aps/{AP_MAC}/uplink-config", token="token")
        self.assertEqual(result["resource"], "ap_uplink_config")
        self.assertEqual(result["device_ref"], AP_REF)

    def test_fixed_transport_allows_only_the_configured_controller_uplink_path(self) -> None:
        class Response:
            status = 200
            def read(self, _size):
                return b'{"errorCode":0,"result":[{"auto":true,"port":"1/0/3"}]}'
            def getheader(self, key, default=None):
                return "application/json" if key.lower() == "content-type" else default

        class Connection:
            _omada_tls_verified = True
            def request(self, *_args, **_kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_connection", return_value=Connection()) as connection:
            result = self.client.read_ap_uplink_config(SITE_REF, AP_REF)
        connection.assert_called_once_with()
        self.assertEqual(result["items"], [{"auto": True, "port": "1/0/3"}])
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", f"/openapi/v1/other/sites/site_1/aps/{AP_MAC}/uplink-config")

    def test_unknown_ap_is_rejected_before_controller_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                self.client.read_ap_uplink_config(SITE_REF, "c" * 24)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
