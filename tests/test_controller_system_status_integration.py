import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerSystemStatusIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def _read(self, name, path, resource, payload, *args):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
            result = getattr(self.client, name)(*args)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], resource)
        return result

    def test_remote_binding_fixed_route(self):
        result = self._read("read_controller_remote_binding",
                            "/openapi/v1/ctrl/cloud/remote/bind/status",
                            "controller_remote_binding", {"enable": False})
        self.assertFalse(result["data"]["enabled"])

    def test_controller_adopt_tip_fixed_route_and_count_projection(self):
        result = self._read(
            "read_controller_device_adoption_tip_summary",
            "/openapi/v1/ctrl/adopt-tip",
            "controller_device_adoption_tip_summary",
            {"adoptDeviceNum": 3, "recommendDeviceNum": 2,
             "deviceList": [{"name": "private-device"}]})
        self.assertEqual(result["data"], {
            "adopted_device_count": 3, "recommended_device_count": 2,
        })
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private-device", repr(result))

    def test_controller_adopt_tip_invalid_projection_is_redacted(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"adoptDeviceNum": None, "recommendDeviceNum": True}}):
            result = self.client.read_controller_device_adoption_tip_summary()
        self.assertEqual(result["data"], {})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertTrue(result["partial"])
        self.assertNotIn("None", repr(result))

    def test_backup_result_fixed_route(self):
        result = self._read("read_controller_backup_result",
                            "/openapi/v1/ctrl/maintenance/backup/result",
                            "controller_backup_result", {"status": 1})
        self.assertEqual(result["data"]["status"], "running")

    def test_restore_result_fixed_route(self):
        result = self._read("read_controller_restore_result",
                            "/openapi/v1/ctrl/maintenance/restore/result",
                            "controller_restore_result", {"status": 3})
        self.assertEqual(result["data"]["status"], "failed")

    def test_privacy_policy_fixed_route(self):
        result = self._read("read_controller_privacy_policy",
                            "/openapi/v1/ctrl/privacy-policy",
                            "controller_privacy_policy", {"status": 1})
        self.assertTrue(result["data"]["enabled"])

    def test_mail_status_fixed_route_redacts_all_config_values(self):
        result = self._read("read_controller_mail_status",
                            "/openapi/v1/ctrl/mail/status", "controller_mail_status",
                            {"sender": "private@example.invalid", "receiver": "private",
                             "ssl": True, "auth": False, "authCode": "private-code"})
        self.assertTrue(result["data"]["sender_configured"])
        self.assertNotIn("private", repr(result))

    def test_global_mfa_status_uses_fixed_controller_route(self):
        result = self._read("read_controller_global_mfa_status",
                            "/openapi/v1/ctrl/mfa/status",
                            "controller_global_mfa_status",
                            {"enable": True, "secret": "private"})
        self.assertTrue(result["data"]["enabled"])
        self.assertNotIn("private", repr(result))

    def test_msp_cloud_status_fixed_route_uses_bounded_reference(self):
        result = self._read("read_msp_cloud_access_status",
                            "/openapi/v1/msp/msp-id_safe/cloud/status",
                            "msp_cloud_access_status",
                            {"enable": True, "status": 0, "owner": "private"},
                            "msp-id_safe")
        self.assertEqual(result["data"]["connection"], "disconnected")
        self.assertNotIn("private", repr(result))

    def test_msp_privacy_policy_fixed_route(self):
        result = self._read("read_msp_privacy_policy",
                            "/openapi/v1/msp/msp-id_safe/privacy-policy",
                            "msp_privacy_policy", {"status": 1}, "msp-id_safe")
        self.assertTrue(result["data"]["enabled"])

    def test_msp_dst_info_fixed_route_uses_bounded_reference(self):
        result = self._read("read_msp_dst_info",
                            "/openapi/v1/msp/msp-id_safe/dst-info",
                            "msp_dst_info", {"enable": False}, "msp-id_safe")
        self.assertFalse(result["data"]["settings"]["enabled"])

    def test_msp_remote_logging_fixed_route_redacts_destination(self):
        result = self._read("read_msp_remote_logging",
                            "/openapi/v1/msp/msp-id_safe/remote-logging",
                            "msp_remote_logging",
                            {"enable": True, "host": "private.test", "port": 514},
                            "msp-id_safe")
        self.assertTrue(result["data"]["settings"]["host_present"])
        self.assertNotIn("private", repr(result))

    def test_msp_mail_server_fixed_route_redacts_credentials(self):
        result = self._read("read_msp_mail_server",
                            "/openapi/v1/msp/msp-id_safe/settings/mail-server",
                            "msp_mail_server",
                            {"authEnable": True, "port": 465,
                             "smtpServer": "smtp.private.test", "sslEnable": True,
                             "username": "private-user", "password": "private-pass"},
                            "msp-id_safe")
        self.assertNotIn("private", repr(result))

    def test_msp_general_settings_fixed_route_redacts_name(self):
        result = self._read("read_msp_general_settings",
                            "/openapi/v1/msp/msp-id_safe/general-setting",
                            "msp_general_settings",
                            {"name": "Private MSP", "timeZone": "UTC",
                             "dst": {"enable": False}}, "msp-id_safe")
        self.assertNotIn("Private MSP", repr(result))

    def test_msp_log_notification_route_redacts_ids_and_labels(self):
        result = self._read("read_msp_log_notification_settings",
                            "/openapi/v1/msp/msp-id_safe/log-notification",
                            "msp_log_notification_settings",
                            {"webhookConfig": {"webhookEnable": True,
                                                "webhookId": "private-webhook"},
                             "logNotifications": [{"key": "PRIVATE", "alert": True}]},
                            "msp-id_safe")
        self.assertNotIn("private", repr(result).lower())

    def test_msp_data_retention_fixed_route(self):
        result = self._read("read_msp_data_retention",
                            "/openapi/v1/msp/msp-id_safe/retention",
                            "msp_data_retention",
                            {"clientsDataEnable": True, "knownClient": 7},
                            "msp-id_safe")
        self.assertTrue(result["data"]["flags"]["clients_data_enable"])

    def test_msp_ui_interface_fixed_route_redacts_label_values(self):
        result = self._read("read_msp_ui_interface",
                            "/openapi/v1/msp/msp-id_safe/ui-interface",
                            "msp_ui_interface",
                            {"fixedMenu": True, "refreshBtnEnable": True,
                             "refreshRate": 0, "use24hour": False,
                             "websocketEnable": True,
                             "privateLabelingUrl": "https://private.test/logo"},
                            "msp-id_safe")
        self.assertNotIn("private.test", repr(result))

    def test_msp_user_interface_fixed_route(self):
        result = self._read("read_msp_user_interface",
                            "/openapi/v1/msp/msp-id_safe/settings/user-interface",
                            "msp_user_interface", {"refreshRate": 2}, "msp-id_safe")
        self.assertEqual(result["data"]["settings"]["refresh_rate_code"], 2)

    def test_msp_available_roles_fixed_route_redacts_role_identity(self):
        result = self._read("read_msp_available_roles",
                            "/openapi/v1/msp/msp-id_safe/roles/available",
                            "msp_available_roles",
                            [{"id": "private-id", "name": "Private name",
                              "type": 2, "source": 2, "defaultRole": False}],
                            "msp-id_safe")
        self.assertEqual(result["data"]["role_count"], 1)
        self.assertNotIn("private", repr(result).lower())

    def test_msp_available_customer_roles_fixed_route(self):
        result = self._read("read_msp_available_customer_roles",
                            "/openapi/v1/msp/msp-id_safe/roles/customer/roles/available",
                            "msp_available_customer_roles", [], "msp-id_safe")
        self.assertEqual(result["data"]["role_count"], 0)

    def test_msp_dashboard_overall_fixed_route(self):
        result = self._read("read_msp_dashboard_overall",
                            "/openapi/v1/msp/msp-id_safe/dashboard/client/overview-diagram",
                            "msp_dashboard_overall",
                            {"totalClientNum": 8, "wiredUser": 2,
                             "wirelessUser": 5, "wirelessGuest": 1},
                            "msp-id_safe")
        self.assertEqual(result["data"]["total"], 8)

    def test_msp_cluster_nodes_fixed_route_redacts_identity(self):
        result = self._read("read_msp_cluster_nodes",
                            "/openapi/v1/msp/msp-id_safe/cluster/nodes/info",
                            "msp_cluster_nodes",
                            [{"nodeName": "private-node", "role": "leader",
                              "status": "online", "managedSites": 2,
                              "managedDevices": 9}],
                            "msp-id_safe")
        self.assertEqual(result["data"]["managed_devices"], 9)
        self.assertNotIn("private-node", repr(result))

    def test_msp_adopt_tip_fixed_route(self):
        result = self._read("read_msp_adopt_tip",
                            "/openapi/v1/msp/msp-id_safe/adopt-tip",
                            "msp_adopt_tip",
                            {"adoptDeviceNum": 5, "recommendDeviceNum": 2},
                            "msp-id_safe")
        self.assertEqual(result["data"]["recommended_device_count"], 2)

    def test_msp_role_summary_fixed_route_redacts_privilege_details(self):
        result = self._read("read_msp_role_summary",
                            "/openapi/v1/msp/msp-id_safe/roles",
                            "msp_role_summary",
                            [{"id": "private-id", "name": 2,
                              "defaultRole": False,
                              "privilege": {"mspDashboard": 2}}],
                            "msp-id_safe")
        self.assertEqual(result["data"]["role_count"], 1)
        self.assertNotIn("private-id", repr(result))

    def test_msp_references_reject_path_syntax(self):
        for value in ("../admin", "msp/id", "", "a" * 129):
            with self.subTest(value=value), self.assertRaisesRegex(
                    OpenApiError, "openapi_path_rejected"):
                self.client.read_msp_cloud_access_status(value)

    def test_all_fixed_paths_reject_a_different_controller(self):
        paths = ("/openapi/v1/other/cloud/remote/bind/status",
                 "/openapi/v1/other/maintenance/backup/result",
                 "/openapi/v1/other/maintenance/restore/result",
                 "/openapi/v1/other/privacy-policy",
                 "/openapi/v1/other/mail/status")
        for path in paths:
            with self.subTest(path=path), self.assertRaisesRegex(
                    OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)


if __name__ == "__main__":
    unittest.main()
