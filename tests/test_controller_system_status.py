import unittest

from app.controller_system_status import (
    ControllerSystemStatusError, project_controller_backup_result,
    project_controller_mail_status, project_controller_mfa_status, project_msp_cloud_access_status,
    project_msp_dst_info,
    project_msp_remote_logging,
    project_msp_mail_server,
    project_msp_general_settings,
    project_msp_log_notification_settings,
    project_msp_data_retention,
    project_msp_ui_interface, project_msp_user_interface,
    project_msp_available_roles,
    project_msp_dashboard_overall,
    project_msp_cluster_nodes,
    project_msp_adopt_tip,
    project_controller_adopt_tip,
    project_msp_roles,
    project_controller_privacy_policy, project_controller_remote_binding,
    project_controller_restore_result,
)


class ControllerSystemStatusTests(unittest.TestCase):
    def test_msp_dashboard_overall_returns_only_bounded_aggregate_counts(self):
        result = project_msp_dashboard_overall({
            "totalClientNum": 12, "wiredUser": 3,
            "wirelessUser": 7, "wirelessGuest": 2,
            "futurePersonalField": "private",
        })
        self.assertEqual(result["data"], {
            "total": 12, "wired": 3, "wireless": 7, "wireless_guest": 2,
        })
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_msp_dashboard_overall_rejects_invalid_counts(self):
        result = project_msp_dashboard_overall({
            "totalClientNum": True, "wiredUser": -1,
            "wirelessUser": 4, "wirelessGuest": 2_147_483_648,
        })
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertTrue(result["partial"])

    def test_msp_cluster_nodes_aggregates_capacity_without_node_identity(self):
        result = project_msp_cluster_nodes([
            {"nodeName": "private-node", "currentNode": "private-id",
             "role": "leader", "status": "online", "systemTime": 12,
             "managedSites": 3, "managedDevices": 21},
            {"nodeName": "private-node-2", "role": "worker",
             "status": "online", "managedSites": 2, "managedDevices": 19},
        ])
        self.assertEqual(result["data"], {
            "node_count": 2, "managed_sites": 5, "managed_devices": 40,
            "nodes_reporting_role": 2, "nodes_reporting_status": 2,
        })
        self.assertNotIn("private", repr(result))
        self.assertNotIn("leader", repr(result))

    def test_msp_cluster_nodes_rejects_invalid_and_unbounded_data(self):
        result = project_msp_cluster_nodes([
            {"managedSites": True, "managedDevices": -1,
             "status": "ok", "extra": "private"},
        ])
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        with self.assertRaises(ControllerSystemStatusError):
            project_msp_cluster_nodes([{}] * 201)

    def test_msp_adopt_tip_returns_only_bounded_documented_counts(self):
        result = project_msp_adopt_tip({
            "adoptDeviceNum": 4, "recommendDeviceNum": 3,
            "deviceNames": ["private-device"],
        })
        self.assertEqual(result["data"], {
            "adopted_device_count": 4, "recommended_device_count": 3,
        })
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private-device", repr(result))

    def test_msp_adopt_tip_rejects_invalid_counts(self):
        result = project_msp_adopt_tip({
            "adoptDeviceNum": True, "recommendDeviceNum": -1,
        })
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertTrue(result["partial"])

    def test_controller_adopt_tip_returns_only_documented_bounded_counts(self):
        result = project_controller_adopt_tip({
            "adoptDeviceNum": 0, "recommendDeviceNum": 2_147_483_647,
            "deviceList": [{"name": "private-device"}],
        })
        self.assertEqual(result["data"], {
            "adopted_device_count": 0,
            "recommended_device_count": 2_147_483_647,
        })
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private-device", repr(result))

    def test_controller_adopt_tip_tracks_missing_null_and_invalid_fields(self):
        self.assertEqual(project_controller_adopt_tip({}), {
            "data": {}, "missing_field_count": 2, "invalid_field_count": 0,
            "unknown_field_count": 0, "partial": True,
        })
        result = project_controller_adopt_tip({
            "adoptDeviceNum": None, "recommendDeviceNum": True,
        })
        self.assertEqual(result["data"], {})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertTrue(result["partial"])
        overrange = project_controller_adopt_tip({
            "adoptDeviceNum": 2_147_483_648, "recommendDeviceNum": 1.5,
        })
        self.assertEqual(overrange["invalid_field_count"], 2)
        self.assertNotIn("2147483648", repr(overrange))

    def test_msp_roles_aggregates_privilege_levels_without_role_identity(self):
        result = project_msp_roles([
            {"id": "private-id", "name": 1, "defaultRole": True,
             "privilege": {"mspDashboard": 1, "mspDevice": 2,
                           "mspAdopt": 2, "mspLicenseBind": 1}},
            {"id": "another-id", "name": 2, "defaultRole": False,
             "privilege": {"mspDashboard": 0, "mspDevice": 0,
                           "mspAdopt": 0}},
        ])
        self.assertEqual(result["data"]["role_count"], 2)
        self.assertEqual(result["data"]["default_role_count"], 1)
        self.assertEqual(result["data"]["permission_level_counts"]["mspDashboard"],
                         {"blocked": 1, "view_only": 1, "modify_or_access": 0})
        self.assertEqual(result["data"]["permission_level_counts"]["mspAdopt"],
                         {"blocked": 1, "view_only": 0, "modify_or_access": 1})
        self.assertNotIn("private-id", repr(result))

    def test_msp_roles_rejects_invalid_permission_shapes_and_bounds(self):
        result = project_msp_roles([
            {"name": True, "defaultRole": 1,
             "privilege": {"mspDashboard": 3, "mspAdopt": 1,
                           "unexpected": 0}},
        ])
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        with self.assertRaises(ControllerSystemStatusError):
            project_msp_roles([{}] * 501)

    def test_msp_dst_info_uses_bounded_documented_daylight_saving_projection(self):
        result = project_msp_dst_info({
            "mode": 1, "enable": True, "status": True, "offset": 3600000,
            "timeZone": "Europe/Berlin", "startTime": 1, "endTime": 2,
            "start": {"month": 3, "serial": 5, "day": 7,
                      "hour": 2, "minute": 0},
            "end": {"month": 10, "serial": 5, "day": 7,
                    "hour": 3, "minute": 0},
        })
        self.assertEqual(result["data"]["settings"]["time_zone"], "Europe/Berlin")
        self.assertEqual(result["data"]["settings"]["offset_ms"], 3600000)
        self.assertTrue(result["partial"])

    def test_msp_dst_info_rejects_unbounded_or_invalid_response(self):
        invalid = project_msp_dst_info({"enable": True, "start": {"month": 99}})
        self.assertGreater(invalid["data"]["invalid_count"], 0)
        self.assertTrue(invalid["partial"])
        with self.assertRaises(ValueError):
            project_msp_dst_info({str(i): i for i in range(17)})

    def test_msp_remote_logging_redacts_host_and_port_values(self):
        result = project_msp_remote_logging({
            "enable": True, "host": "syslog.test", "port": 514,
        })
        self.assertTrue(result["data"]["settings"]["enabled"])
        self.assertTrue(result["data"]["settings"]["host_present"])
        self.assertTrue(result["data"]["settings"]["port_present"])
        self.assertNotIn("private", repr(result))

    def test_msp_mail_server_redacts_credentials_addresses_and_endpoints(self):
        result = project_msp_mail_server({
            "smtpEnable": True, "smtpServer": "smtp.private.test", "port": 465,
            "sslEnable": True, "authEnable": True, "username": "private-user",
            "password": "private-password", "senderAddress": "from@private.test",
            "receiver": "to@private.test",
        })
        self.assertEqual(result["data"]["settings"], {
            "server_enabled": True, "secure_transport_enabled": True,
            "authentication_enabled": True, "port_configured": True,
            "server_configured": True, "username_configured": True,
            "password_configured": True, "sender_configured": True,
            "receiver_configured": True,
        })
        for secret in ("smtp.private.test", "private-user", "private-password",
                       "from@private.test", "to@private.test", "465"):
            self.assertNotIn(secret, repr(result))

    def test_msp_general_settings_redacts_name_and_projects_dst(self):
        result = project_msp_general_settings({
            "name": "Private MSP", "timeZone": "Europe/Berlin",
            "dst": {"enable": False},
        })
        self.assertEqual(result["data"]["settings"], {
            "name_configured": True, "time_zone": "Europe/Berlin",
        })
        self.assertFalse(result["data"]["dst"]["partial"])
        self.assertNotIn("Private MSP", repr(result))

    def test_msp_log_notification_settings_return_only_bounded_counts(self):
        result = project_msp_log_notification_settings({
            "webhookConfig": {"webhookEnable": True, "webhookId": "private-webhook"},
            "logNotifications": [
                {"key": "LOGIN_OK", "shortMsg": "Private label", "alert": True,
                 "event": False, "email": True, "webhook": True},
                {"key": "PRIVATE_EVENT", "shortMsg": "Another label", "alert": False,
                 "event": True, "email": False, "webhook": False},
            ],
            "alertEmailSetting": {"alertEmailEnable": True, "delayEnable": True,
                                  "delay": 30},
        })
        settings = result["data"]["settings"]
        self.assertEqual(settings["notification_count"], 2)
        self.assertEqual(settings["alert_enabled_count"], 1)
        self.assertEqual(settings["event_enabled_count"], 1)
        self.assertEqual(settings["email_enabled_count"], 1)
        self.assertNotIn("private", repr(result).lower())

    def test_msp_log_notification_settings_reject_oversized_lists(self):
        result = project_msp_log_notification_settings({"logNotifications": [{}] * 501})
        self.assertTrue(result["partial"])
        self.assertGreater(result["data"]["invalid_field_count"], 0)

    def test_msp_data_retention_uses_bounded_retention_projection(self):
        result = project_msp_data_retention({
            "clientsDataEnable": True, "knownClient": 7,
            "knownClientAvailableRetentionDays": [1, 7, 31],
        })
        self.assertTrue(result["data"]["flags"]["clients_data_enable"])
        self.assertEqual(result["data"]["retention_values"]["known_client"], 7)
        self.assertTrue(result["partial"])
        oversized = project_msp_data_retention({"clientsDataEnable": True,
                                                "knownClientAvailableRetentionDays": [1] * 65})
        self.assertTrue(oversized["partial"])

    def test_msp_ui_interface_redacts_private_label_urls_and_identifiers(self):
        result = project_msp_ui_interface({
            "language": 4, "use24hour": True, "fixedMenu": False, "theme": 1,
            "showPDevices": True, "refreshBtnEnable": True, "refreshRate": 1,
            "websocketEnable": True, "controllerNotification": False,
            "privateLabelingEnable": True, "privateLabelingUrl": "https://brand.private.test/logo",
            "privateLabelingFileId": "secret-file-id", "privateLabelingFileName": "brand.png",
        })
        settings = result["data"]["settings"]
        self.assertEqual(settings["language_code"], 4)
        self.assertTrue(settings["private_labeling_url_present"])
        self.assertNotIn("private.test", repr(result))
        self.assertNotIn("secret-file-id", repr(result))
        self.assertFalse(result["partial"])

    def test_msp_user_interface_redacts_private_label_values(self):
        result = project_msp_user_interface({
            "refreshRate": 4, "privateLabelingEnable": True,
            "privateLabelingUrl": "https://brand.private.test/logo",
        })
        self.assertEqual(result["data"]["settings"]["refresh_rate_code"], 4)
        self.assertNotIn("private.test", repr(result))

    def test_msp_available_roles_returns_aggregates_without_names_or_ids(self):
        result = project_msp_available_roles([
            {"id": "private-role-id", "name": "Private role", "type": 2,
             "source": 2, "defaultRole": False},
            {"id": "standard-role", "name": "Standard role", "type": 0,
             "source": 0, "defaultRole": True},
        ])
        self.assertEqual(result["data"]["role_count"], 2)
        self.assertEqual(result["data"]["role_type_counts"], {"0": 1, "1": 0, "2": 1})
        self.assertEqual(result["data"]["msp_created_role_count"], 1)
        self.assertNotIn("private", repr(result).lower())
        self.assertFalse(result["partial"])

    def test_remote_binding_returns_only_the_documented_boolean(self):
        result = project_controller_remote_binding({"enable": True, "account": "private"})
        self.assertEqual(result["data"], {"enabled": True})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        self.assertTrue(result["partial"])

    def test_privacy_policy_returns_only_the_documented_enable_state(self):
        self.assertEqual(project_controller_privacy_policy({"status": 1}), {
            "data": {"enabled": True}, "missing_field_count": 0,
            "invalid_field_count": 0, "unknown_field_count": 0, "partial": False,
        })
        self.assertEqual(project_controller_privacy_policy({"status": 0})["data"],
                         {"enabled": False})
        result = project_controller_privacy_policy({"status": 2, "secret": "private"})
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_mail_status_redacts_addresses_server_and_authorization_code(self):
        result = project_controller_mail_status({
            "sender": "sender@example.invalid", "receiver": "receiver@example.invalid",
            "ssl": True, "auth": True, "smtpServer": "smtp.private.invalid",
            "smtpPort": 465, "username": "private-user", "authCode": "private-code",
            "id": "private-id", "resource": 2,
        })
        self.assertEqual(result["data"], {
            "sender_configured": True, "receiver_configured": True,
            "username_configured": True, "server_configured": True,
            "authorization_code_present": True, "server_id_present": True,
            "secure_transport_enabled": True, "authentication_enabled": True,
            "smtp_port_present": True, "resource_present": True,
        })
        for secret in ("sender@example.invalid", "smtp.private.invalid", "private-user",
                       "private-code", "private-id"):
            self.assertNotIn(secret, repr(result))

    def test_controller_mfa_status_returns_only_boolean_enable(self):
        result = project_controller_mfa_status({"enable": True, "secret": "private"})
        self.assertEqual(result["data"], {"enabled": True})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        self.assertEqual(project_controller_mfa_status({"enable": "true"})[
            "invalid_field_count"], 1)
        with self.assertRaises(ControllerSystemStatusError):
            project_controller_mfa_status({str(i): i for i in range(17)})

    def test_mail_status_missing_invalid_unknown_and_oversized_values_are_handled(self):
        result = project_controller_mail_status({"ssl": "yes", "auth": False,
                                                "sender": 7, "receiver": "",
                                                "extra": "private"})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        with self.assertRaises(ControllerSystemStatusError):
            project_controller_mail_status({str(i): i for i in range(33)})

    def test_msp_cloud_status_returns_only_bounded_state(self):
        result = project_msp_cloud_access_status({
            "enable": True, "status": 1, "owner": "private-account",
        })
        self.assertEqual(result["data"], {
            "enabled": True, "connection": "connected", "owner_present": True,
        })
        self.assertNotIn("private-account", repr(result))
        result = project_msp_cloud_access_status({"enable": 0, "status": 8, "extra": "private"})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_backup_result_uses_the_documented_status_values(self):
        self.assertEqual(project_controller_backup_result({"status": 0})["data"]["status"],
                         "idle_or_finished")
        self.assertEqual(project_controller_backup_result({"status": 1})["data"]["status"],
                         "running")

    def test_restore_result_uses_the_documented_status_values(self):
        values = {0: "finished", 1: "prepared", 2: "running", 3: "failed"}
        for code, label in values.items():
            with self.subTest(code=code):
                self.assertEqual(project_controller_restore_result({"status": code})["data"]["status"],
                                 label)

    def test_missing_invalid_unknown_and_non_object_results_are_explicit(self):
        result = project_controller_backup_result({"status": 7, "private": "omit"})
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("omit", repr(result))
        self.assertTrue(project_controller_restore_result({})["partial"])
        with self.assertRaises(ControllerSystemStatusError):
            project_controller_remote_binding([])
        with self.assertRaises(ControllerSystemStatusError):
            project_controller_backup_result({str(i): i for i in range(17)})


if __name__ == "__main__":
    unittest.main()
