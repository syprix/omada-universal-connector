from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_general_config import ApGeneralConfigError, summarize_ap_general_config


class ApGeneralConfigProjectionTests(unittest.TestCase):
    def test_projects_settings_and_redacts_identity_tags_and_location(self):
        result = summarize_ap_general_config({
            "name": "private AP name", "ledSetting": 2,
            "remoteReset": False, "wifiControlEnable": True,
            "gpsEnable": True, "rememberDevice": 1, "disableHwReset": False,
            "tagIds": ["private-tag-id"],
            "location": {"longitude": 13.4, "latitude": 52.5,
                         "address": "private street", "timestamp": 1},
            "rssiLedSettings": [{"ledId": "private-led-name", "threshold": -65},
                                {"ledId": "another-private-led", "threshold": -65}],
        })
        self.assertEqual(result["ledSetting"], 2)
        self.assertFalse(result["remoteReset"])
        self.assertTrue(result["wifiControlEnable"])
        self.assertEqual(result["tag_count"], 1)
        self.assertTrue(result["location_configured"])
        self.assertEqual(result["rssi_threshold_counts"], {-65: 2})
        self.assertFalse(result["partial"])
        for private in ("private AP name", "private-tag-id", "private street",
                        "private-led-name", "another-private-led", "13.4", "52.5"):
            self.assertNotIn(private, repr(result))

    def test_missing_invalid_and_unknown_fields_mark_partial_without_echo(self):
        result = summarize_ap_general_config({
            "name": "secret", "ledSetting": 8, "remoteReset": 1,
            "tagIds": ["tag"], "location": {},
            "rssiLedSettings": [{"threshold": "private", "vendor": "private value"}],
            "vendorSetting": "private value",
        })
        self.assertTrue(result["partial"])
        self.assertGreater(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertNotIn("private", repr(result))

    def test_rejects_invalid_root_and_bounded_lists(self):
        for raw in (None, [], {"x" * 129: 1}, {"tagIds": ["x"] * 129},
                    {"rssiLedSettings": [{}] * 33}):
            with self.subTest(raw_type=type(raw).__name__):
                if raw in (None, []):
                    with self.assertRaises(ApGeneralConfigError):
                        summarize_ap_general_config(raw)
                else:
                    result = summarize_ap_general_config(raw)
                    self.assertTrue(result["partial"])
                    self.assertNotIn("x" * 129, repr(result))

    def test_nonfinite_and_out_of_range_coordinates_mark_partial(self):
        result = summarize_ap_general_config({
            "location": {"longitude": 10**1000, "latitude": float("nan")},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertNotIn("nan", repr(result).lower())


class ApGeneralConfigClientTests(unittest.TestCase):
    def test_reads_fixed_route_for_inventoried_ap(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        response = {"errorCode": 0, "result": {
            "name": "private", "ledSetting": 1, "remoteReset": False,
            "wifiControlEnable": True, "gpsEnable": False,
            "rememberDevice": 2, "disableHwReset": False,
            "tagIds": [], "location": {}, "rssiLedSettings": [],
        }}
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/general-config"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_ap_general_config(site_ref, ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_general_config")
        self.assertNotIn("private", repr(result))

    def test_request_guard_rejects_modified_general_config_path(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/general-config?extra=1")
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
