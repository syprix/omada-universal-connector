import unittest
from unittest.mock import patch

from app.controller_system_ports import (
    ControllerSystemPortsError,
    project_controller_system_ports,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerSystemPortsProjectionTests(unittest.TestCase):
    def test_upgrade_port_is_bounded(self):
        result = project_controller_system_ports(
            {"upgradeHttpsPort": 10443}, "controller_upgrade_port")
        self.assertEqual(result["data"]["settings"], {"upgrade_https_port": 10443})
        self.assertFalse(result["partial"])
        self.assertEqual(project_controller_system_ports(
            {"upgradeHttpsPort": 0}, "controller_upgrade_port")["data"]["invalid_count"], 1)

    def test_portal_host_is_redacted_and_ports_and_flags_are_projected(self):
        raw = {"portalHttpPort": 80, "portalHttpsPort": 10443,
               "portalHost": "portal.private.example", "autoPortalIpEnable": True,
               "portalHttpsRedirect": False}
        result = project_controller_system_ports(raw, "controller_portal_port_settings")
        settings = result["data"]["settings"]
        self.assertEqual(settings, {"http_port": 80, "https_port": 10443,
                                    "portal_host_present": True,
                                    "auto_portal_ip_enabled": True,
                                    "https_redirect_enabled": False})
        self.assertNotIn("portal.private.example", str(result))
        self.assertFalse(result["partial"])

    def test_controller_hostname_is_redacted_and_http_defaults_are_valid(self):
        raw = {"manageHttpPort": 80, "manageHttpsPort": 443,
               "hostName": "controller.private.example", "autoRefresh": False}
        result = project_controller_system_ports(raw, "controller_port_settings")
        self.assertEqual(result["data"]["settings"], {"http_port": 80,
                    "https_port": 443, "host_name_present": True, "auto_refresh": False})
        self.assertNotIn("controller.private.example", str(result))
        self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_fields_are_partial(self):
        result = project_controller_system_ports(
            {"portalHttpPort": True, "portalHost": "bad\nvalue", "extra": "hidden"},
            "controller_portal_port_settings")
        self.assertEqual(result["data"]["invalid_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertEqual(result["data"]["settings"], {})
        self.assertTrue(result["partial"])

    def test_response_size_and_operation_id_fail_closed(self):
        with self.assertRaises(ControllerSystemPortsError):
            project_controller_system_ports({str(i): 1 for i in range(33)},
                                            "controller_upgrade_port")
        with self.assertRaises(ControllerSystemPortsError):
            project_controller_system_ports({}, "controller_arbitrary")


class ControllerSystemPortsClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_each_operation_uses_its_fixed_get_route(self):
        cases = (
            ("read_controller_upgrade_port", "/system/setting/upgrade-port", {"upgradeHttpsPort": 10443}),
            ("read_controller_portal_port_settings", "/system/setting/portal-port", {"portalHost": "portal.private.example"}),
            ("read_controller_port_settings", "/system/setting/controller-port", {"hostName": "controller.private.example"}),
        )
        for method, suffix, result in cases:
            with self.subTest(operation=method), patch.object(
                    self.client, "_access_token", return_value="token"), patch.object(
                    self.client, "_request_json", return_value={"result": result}) as request:
                response = getattr(self.client, method)()
                request.assert_called_once_with(
                    "GET", f"/openapi/v1/ctrl{suffix}", token="token")
                self.assertEqual(response["status"], "ok")
                self.assertNotIn("private.example", str(response))

    def test_paths_are_bound_to_the_configured_controller(self):
        for suffix in ("upgrade-port", "portal-port", "controller-port"):
            with self.subTest(route=suffix), self.assertRaisesRegex(
                    OpenApiError, "openapi_path_rejected"):
                self.client._request_json(
                    "GET", f"/openapi/v1/other/system/setting/{suffix}")


if __name__ == "__main__":
    unittest.main()
