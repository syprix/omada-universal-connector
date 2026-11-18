from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_internet_summary import (
    SiteInternetSummaryError, _SUPPORT_FLAGS, project_site_internet,
)


def source_result() -> dict[str, object]:
    return {
        "siteId": "private-site-id", "omadacId": "private-controller-id", "enable": True,
        "osgPortInfo": {"wanPortNum": 2, "realOsgModel": "private-model",
                         "wanLanPortSettings": [{"portUuid": "private-port-id"}]},
        "portUuids": ["private-port-id"], "interval": 60, "unit": 1,
        "supportMaxWanNum": 4, "supportDualSim": 2, "resource": 1,
        "wanPortSettings": [{"portId": "private-wan-id", "password": "private-secret"}],
        "usbLteSettings": [{"pin": "private-pin"}],
        "lteWanSettings": [], "networkNames": ["private-network"],
        "unmatchedWans": [{"portName": "private-name"}],
        "wanLoadBalance": {"weights": [{"portUuid": "private-port-id"}],
                           "appOptRouting": True, "linkBackup": False,
                           "primaryWans": ["private-wan-id"]},
        "portOnlineStatus": {"wanOnlineStatus": [{"portUuid": "private-port-id"}],
                              "virtualWanOnlineStatus": []},
        **{key: True for key in _SUPPORT_FLAGS},
    }


class SiteInternetProjectionTests(unittest.TestCase):
    def test_returns_safe_counts_and_flags_without_raw_configuration(self) -> None:
        result = project_site_internet(source_result())
        self.assertEqual(result["data"]["configured_wan_port_count"], 1)
        self.assertEqual(result["data"]["configured_usb_lte_port_count"], 1)
        self.assertEqual(result["data"]["gateway_wan_port_count"], 2)
        self.assertEqual(result["data"]["wan_status_entry_count"], 1)
        self.assertTrue(result["data"]["load_balance"]["app_optimized_routing"])
        self.assertEqual(result["data"]["load_balance"]["weight_entry_count"], 1)
        self.assertFalse(result["partial"])
        for secret in ("private-site-id", "private-controller-id", "private-model",
                       "private-port-id", "private-secret", "private-pin", "private-network",
                       "private-name", "private-wan-id"):
            self.assertNotIn(secret, repr(result))

    def test_missing_invalid_and_unknown_values_are_counted(self) -> None:
        result = project_site_internet({"siteId": "", "enable": "yes", "private": "secret"})
        self.assertTrue(result["partial"])
        self.assertGreater(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("secret", repr(result))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(97)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(SiteInternetSummaryError):
                project_site_internet(value)


class SiteInternetClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path_and_projects_response(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": source_result()}) as request:
            result = self.client.read_site_internet_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/internet", token="test-token")
        self.assertEqual(result["data"]["configured_wan_port_count"], 1)
        self.assertNotIn("private-secret", repr(result))

    def test_rejects_invalid_response_unknown_site_and_other_controllers(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_internet_summary(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_internet_summary("7" * 24)
        self.assertTrue(self.client._site_internet_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/internet"))
        self.assertFalse(self.client._site_internet_request_valid(
            "/openapi/v1/other/sites/site_internal/internet"))


if __name__ == "__main__":
    unittest.main()
