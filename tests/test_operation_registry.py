import unittest

from app.operation_registry import Operation, OperationRegistry, RegistryError, REGISTRY
from app.mcp import _tool


class OperationRegistryTests(unittest.TestCase):
    def test_event_window_mcp_schema_requires_one_complete_time_format(self):
        operation = REGISTRY.get("site_events_window_summary")
        schema = _tool(operation)["inputSchema"]
        self.assertEqual(schema["required"], ["site_ref"])
        self.assertEqual(len(schema["oneOf"]), 2)
        self.assertEqual(set(schema["properties"]), {
            "site_ref", "start_ms", "end_ms", "start_local", "end_local", "time_zone"})

    def test_msp_client_detail_setting_route_binds_bounded_reference(self):
        op, bindings = REGISTRY.match(
            "GET", "/v1/msp/msp-id_safe/client-detail-information")
        self.assertEqual(op.operation_id, "msp_client_detail_info")
        self.assertEqual(bindings, (("msp_ref", "msp-id_safe"),))
        with self.assertRaises(RegistryError):
            REGISTRY.match("GET", "/v1/msp/../client-detail-information")

    def test_only_declared_routes_match_with_exact_lowercase_refs(self):
        operation, bindings = REGISTRY.match("GET", "/v1/sites/0123456789abcdef01234567/devices")
        self.assertEqual(operation.operation_id, "devices")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/networks/abcdef0123456789abcdef01/dhcp-server/capabilities")
        self.assertEqual(op.operation_id, "network_dhcp_server_capabilities")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("network_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/clients/filter-options/summary")
        self.assertEqual(op.operation_id, "site_client_filter_options_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi-calling/profiles/summary")
        self.assertEqual(op.operation_id, "site_wifi_calling_profiles_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/networks/abcdef0123456789abcdef01/vlan-devices/summary")
        self.assertEqual(op.operation_id, "site_vlan_device_usage_summary")
        self.assertEqual(dict(op.path_bindings)["vlan_id"], "vlan_id")
        self.assertEqual(op.local_arguments, ("vlan_id",))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/networks/abcdef0123456789abcdef01/vlan-ssids/summary")
        self.assertEqual(op.operation_id, "site_vlan_ssid_usage_summary")
        self.assertEqual(dict(op.path_bindings)["vlan_id"], "vlan_id")
        self.assertEqual(op.local_arguments, ("vlan_id",))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/networks/abcdef0123456789abcdef01/dhcp-server/info")
        self.assertEqual(op.operation_id, "network_dhcp_server_info")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("network_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/capabilities")
        self.assertEqual(op.operation_id, "site_capabilities")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/ssids/duplicate-summary")
        self.assertEqual(op.operation_id, "site_duplicate_ssid_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/ap-groups")
        self.assertEqual(op.operation_id, "site_ap_group_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/dot1x/eap-candidates/summary")
        self.assertEqual(op.operation_id, "site_eap_dot1x_candidates_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/dot1x/switch-candidates/summary")
        self.assertEqual(op.operation_id, "site_switch_dot1x_candidates_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/ap-oui-rules/summary")
        self.assertEqual(op.operation_id, "site_ap_oui_vlan_rules_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/ssids/cccccccccccccccccccccccc/ap-groups")
        self.assertEqual(op.operation_id, "ssid_ap_groups")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("ssid_ref", "cccccccccccccccccccccccc")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/topology/network-summary")
        self.assertEqual(op.operation_id, "site_topology_network_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/topology/vlan-summary")
        self.assertEqual(op.operation_id, "site_topology_vlan_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/incidents/unresolved-count")
        self.assertEqual(op.operation_id, "site_unresolved_incident_count")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/incidents/summary")
        self.assertEqual(op.operation_id, "site_incident_overview")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/incidents/distribution")
        self.assertEqual(op.operation_id, "site_incident_distribution")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/incidents/categories")
        self.assertEqual(op.operation_id, "site_incident_category_counts")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/incidents/list")
        self.assertEqual(op.operation_id, "site_incident_list")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/incidents/"
            "abcdef0123456789abcdef01/influencing-clients")
        self.assertEqual(op.operation_id, "site_incident_influencing_clients")
        self.assertEqual(dict(op.path_bindings)["mac"], "$incident_context_mac")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("incident_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/switch-support")
        self.assertEqual(op.operation_id, "site_switch_support")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/dashboard/history")
        self.assertEqual(op.operation_id, "rf_planning_dashboard_history")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/excluded-aps")
        self.assertEqual(op.operation_id, "rf_excluded_aps")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/deployment-history")
        self.assertEqual(op.operation_id, "rf_deploy_history")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        for path in ("/v1/sites/0123456789ABCDEF01234567/devices", "/v1/sites/abc/devices",
                     "/v1/sites/0123456789abcdef01234567/devices/extra",
                     "/v1/sites/0123456789abcdef01234567/devices?path=/evil",
                     "/v1/sites/0123456789ABCDEF01234567/health/summary",
                     "/v1/sites/0123456789abcdef01234567/health/timeline?start=1&end=2",
                     "/v1/msp/msp/id/cloud-access",
                     "/v1/msp/msp-id%2fsecret/privacy-policy",
                     "/v1/msp/msp-id/customers/customer%2fsecret/sites/" + "a" * 24 +
                     "/switches/" + "b" * 24 + "/health/timeline",
                     "/v1/msp/msp-1/customers/bad%2fref/sites/" + "a" * 24 +
                     "/olts/" + "b" * 24 + "/system-info",
                     "/v1/msp/../cloud-access"):
            with self.subTest(path=path), self.assertRaises(RegistryError):
                REGISTRY.match("GET", path)
        # The controller documents capture stop as GET, but it has a write effect.
        # It must stay outside both the fixed read registry and MCP tool discovery.
        with self.assertRaises(RegistryError):
            REGISTRY.match("GET", "/v1/sites/0123456789abcdef01234567/capture/device-type/1/abcdefabcdef/stop")
        op, bindings = REGISTRY.match(
            "GET", "/v1/msp/msp-1/customers/customer-2/sites/" + "a" * 24 +
            "/olts/" + "b" * 24 + "/system-info")
        self.assertEqual(op.operation_id, "olt_system_info_msp")
        self.assertEqual(dict(bindings), {"msp_ref": "msp-1", "customer_ref": "customer-2",
                                          "site_ref": "a" * 24, "device_ref": "b" * 24})
        for operation, family, ref_name, suffix in (
                ("msp_ap_health_detail", "aps", "device_ref", "health"),
                ("msp_gateway_health_detail", "gateways", "gateway_ref", "health"),
                ("msp_switch_health_detail", "switches", "switch_ref", "health"),
                ("msp_ap_health_timeline", "aps", "device_ref", "health/timeline"),
                ("msp_ap_mesh_statistics", "aps", "device_ref", "mesh"),
                ("msp_gateway_health_timeline", "gateways", "gateway_ref", "health/timeline"),
                ("msp_switch_health_timeline", "switches", "switch_ref", "health/timeline")):
            route = (f"/v1/msp/msp-1/customers/customer-2/sites/{'a' * 24}/{family}/"
                     f"{'b' * 24}/{suffix}")
            matched, bindings = REGISTRY.match("GET", route)
            self.assertEqual(matched.operation_id, operation)
            self.assertEqual(dict(bindings)[ref_name], "b" * 24)
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/summary")
        self.assertEqual(op.operation_id, "olt_detail_summary")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        for suffix, operation in (
                ("summary", "msp_olt_detail_summary"),
                ("ports-config-summary", "msp_olt_eth_config_summary"),
                ("pon-port-config-summary", "msp_olt_pon_port_config_summary")):
            route = ("/v1/msp/msp-1/customers/customer-2/sites/" + "a" * 24 +
                     "/olts/" + "b" * 24 + "/" + suffix)
            matched, _ = REGISTRY.match("GET", route)
            self.assertEqual(matched.operation_id, operation)
        site_ports = ("/v1/msp/msp-1/customers/customer-2/sites/" + "a" * 24 +
                      "/olt-ports-summary")
        self.assertEqual(REGISTRY.match("GET", site_ports)[0].operation_id,
                         "msp_olt_site_ports_summary")
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/ports-summary")
        self.assertEqual(op.operation_id, "olt_ports_summary")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        for suffix, operation in (("onu-global-status", "olt_onu_global_status"),
                                  ("onu-isolation-status", "olt_onu_isolation_status")):
            op, bindings = REGISTRY.match(
                "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/" + suffix)
            self.assertEqual(op.operation_id, operation)
            self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        for suffix, operation in (("ports-config-summary", "olt_eth_config_summary"),
                                  ("lags-summary", "olt_lag_config_summary")):
            op, bindings = REGISTRY.match(
                "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/" + suffix)
            self.assertEqual(op.operation_id, operation)
            self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        for suffix, operation in (("auto-refresh-summary", "olt_auto_refresh_summary"),
                                  ("pon-information-summary", "olt_pon_information_summary")):
            op, bindings = REGISTRY.match(
                "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/" + suffix)
            self.assertEqual(op.operation_id, operation)
            self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/pon-port-config-page-summary")
        self.assertEqual(op.operation_id, "olt_pon_port_config_page_summary")
        self.assertEqual(op.extra_arguments, ("page_number", "page_size"))
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/service-port-profiles-summary")
        self.assertEqual(op.operation_id, "olt_service_port_profiles_summary")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/pon-port-config-summary")
        self.assertEqual(op.operation_id, "olt_pon_port_config_summary")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        for suffix, operation in (("onu-auto-auth-status", "olt_onu_auto_auth_status"),
                                  ("onu-autofind-summary", "olt_onu_autofind_summary")):
            op, bindings = REGISTRY.match(
                "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/" + suffix)
            self.assertEqual(op.operation_id, operation)
            self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/onu-inventory-summary")
        self.assertEqual(op.operation_id, "olt_onu_inventory_summary")
        self.assertEqual(op.extra_arguments, ("pon_port",))
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        for suffix, operation in (("onu-reboot-status-summary", "olt_onu_reboot_status_summary"),):
            op, bindings = REGISTRY.match(
                "GET", "/v1/sites/" + "a" * 24 + "/olts/" + "b" * 24 + "/" + suffix)
            self.assertEqual(op.operation_id, operation)
            self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "device_ref": "b" * 24})
        op, bindings = REGISTRY.match("GET", "/v1/controller/health")
        self.assertEqual(op.operation_id, "controller_health")
        op, bindings = REGISTRY.match("GET", "/v1/controller/scenarios")
        self.assertEqual(op.operation_id, "controller_scenarios")
        self.assertEqual(dict(bindings), {})
        op, bindings = REGISTRY.match("GET", "/v1/controller/scenario-differences")
        self.assertEqual(op.operation_id, "controller_scenario_differences")
        self.assertEqual(dict(bindings), {})
        op, _ = REGISTRY.match("GET", "/v1/controller/threat-severity-summary")
        self.assertEqual(op.operation_id, "controller_threat_severity_summary")
        self.assertEqual(op.local_arguments, ("start_ms", "end_ms"))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/threats/window")
        self.assertEqual(op.operation_id, "site_threat_window_summary")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        self.assertEqual(op.local_arguments, ("start_ms", "end_ms", "archived"))
        op, _ = REGISTRY.match("GET", "/v1/controller/gateway-wan-status-summary")
        self.assertEqual(op.operation_id, "controller_gateway_wan_status_summary")
        self.assertEqual(op.extra_arguments, ("page_number", "page_size"))
        op, bindings = REGISTRY.match("GET", "/v1/controller/settings/client-recognition")
        self.assertEqual(op.operation_id, "controller_client_recognition")
        self.assertEqual(bindings, ())
        for path, operation_id in (
                ("/v1/controller/settings/backup-schedule", "controller_backup_schedule"),
                ("/v1/controller/cloud-access", "controller_cloud_access"),
                ("/v1/controller/settings/device-management", "controller_device_management"),
                ("/v1/controller/cloud-binding", "controller_remote_binding"),
                ("/v1/controller/maintenance/backup-status", "controller_backup_result"),
                ("/v1/controller/maintenance/restore-status", "controller_restore_result"),
                ("/v1/controller/settings/privacy-policy", "controller_privacy_policy"),
                ("/v1/controller/settings/mail-server-status", "controller_mail_status"),
                ("/v1/controller/settings/mfa-status", "controller_global_mfa_status"),
                ("/v1/sites/aaaaaaaaaaaaaaaaaaaaaaaa/iot/aging-time-summary",
                 "site_iot_aging_time"),
                ("/v1/sites/aaaaaaaaaaaaaaaaaaaaaaaa/iot/radio-summary",
                 "site_iot_radio_summary"),
                ("/v1/sites/aaaaaaaaaaaaaaaaaaaaaaaa/mesh-summary",
                 "site_mesh_summary"),
                ("/v1/sites/aaaaaaaaaaaaaaaaaaaaaaaa/multicast-rate-limit-summary",
                 "site_multicast_rate_limit_summary"),
                ("/v1/msp/msp-id_safe/cloud-access", "msp_cloud_access_status"),
                ("/v1/msp/msp-id_safe/privacy-policy", "msp_privacy_policy"),
                ("/v1/msp/msp-id_safe/settings/audit-notification", "msp_audit_notification"),
                ("/v1/msp/msp-id_safe/customers/customer-1/sites/aaaaaaaaaaaaaaaaaaaaaaaa/devices/bbbbbbbbbbbbbbbbbbbbbbbb/link-topology",
                 "msp_device_link_topology"),
                ("/v1/msp/msp-id_safe/device-tags-summary", "msp_device_tags"),
                ("/v1/msp/msp-id_safe/settings/mfa-status", "msp_mfa_status"),
                ("/v1/msp/msp-id_safe/settings/license-auto-active", "msp_license_auto_active"),
                ("/v1/msp/msp-id_safe/customer-roles-summary", "msp_customer_roles"),
                ("/v1/msp/msp-id_safe/dst-info", "msp_dst_info"),
                ("/v1/msp/msp-id_safe/settings/remote-logging", "msp_remote_logging"),
                ("/v1/msp/msp-id_safe/settings/mail-server", "msp_mail_server"),
                ("/v1/msp/msp-id_safe/settings/general", "msp_general_settings"),
                ("/v1/msp/msp-id_safe/settings/log-notifications",
                 "msp_log_notification_settings"),
                ("/v1/msp/msp-id_safe/settings/retention", "msp_data_retention"),
                ("/v1/msp/msp-id_safe/settings/ui-interface", "msp_ui_interface"),
                ("/v1/msp/msp-id_safe/settings/user-interface", "msp_user_interface"),
                ("/v1/msp/msp-id_safe/roles/available-summary", "msp_available_roles"),
                ("/v1/msp/msp-id_safe/roles/customer/available-summary",
                 "msp_available_customer_roles"),
                ("/v1/msp/msp-id_safe/dashboard/client-summary",
                 "msp_dashboard_overall"),
                ("/v1/msp/msp-id_safe/cluster/nodes/summary",
                 "msp_cluster_nodes"),
                ("/v1/msp/msp-id_safe/devices/adoption-summary",
                 "msp_adopt_tip"),
                ("/v1/msp/msp-id_safe/roles/summary", "msp_role_summary"),
                ("/v1/sites/aaaaaaaaaaaaaaaaaaaaaaaa/switches/qos-mode",
                 "site_switch_qos_mode"),
                ("/v1/sites/aaaaaaaaaaaaaaaaaaaaaaaa/switches/qos/scheduler-summary",
                 "site_switch_qos_scheduler_summary"),
                ("/v1/sites/aaaaaaaaaaaaaaaaaaaaaaaa/switches/qos/dscp-summary",
                 "site_switch_qos_dscp_summary")):
            with self.subTest(path=path):
                op, bindings = REGISTRY.match("GET", path)
                self.assertEqual(op.operation_id, operation_id)
                expected = (
                    (("msp_ref", "msp-id_safe"), ("customer_ref", "customer-1"),
                     ("site_ref", "a" * 24), ("device_ref", "b" * 24))
                    if operation_id == "msp_device_link_topology" else
                    (("msp_ref", "msp-id_safe"),) if operation_id.startswith("msp_") else
                    (("site_ref", "a" * 24), ("family_id", "17")) if operation_id in {"site_category_application_summary", "site_category_client_summary"} else
                    (("site_ref", "a" * 24),) if operation_id.startswith("site_switch_qos_") or operation_id in {"site_iot_aging_time", "site_iot_radio_summary", "site_mesh_summary", "site_multicast_rate_limit_summary", "site_beacon_control_summary", "site_iot_transmit_power_summary", "site_remember_setting_summary", "site_client_connection_summary", "site_poe_usage_summary", "site_device_counts_summary", "site_ipsec_tunnel_summary", "site_client_association_time_summary", "site_network_activity_summary", "site_client_rssi_distribution_summary", "site_ap_rssi_density_summary", "site_client_attachment_distribution_summary", "site_client_frequency_distribution_summary", "site_device_traffic_summary", "site_past_client_summary", "site_current_client_summary", "site_gateway_isp_summary", "site_top_ap_retry_drop_summary", "site_active_ap_summary", "site_active_switch_summary", "site_device_memory_summary", "site_switch_dashboard_summary", "site_ap_interference_summary", "site_application_category_summary"} else ())
                self.assertEqual(bindings, expected)
        op, bindings = REGISTRY.match("GET", "/v1/controller/devices/statistics")
        self.assertEqual(op.operation_id, "controller_device_statistics")
        self.assertEqual(bindings, ())
        op, bindings = REGISTRY.match("GET", "/v1/controller/settings/client-active-timeout")
        self.assertEqual(op.operation_id, "controller_client_active_timeout")
        self.assertEqual(bindings, ())
        op, bindings = REGISTRY.match("GET", "/v1/controller/settings/ui-interface")
        self.assertEqual(op.operation_id, "controller_ui_interface")
        self.assertEqual(bindings, ())
        self.assertEqual(bindings, ())
        op, bindings = REGISTRY.match("GET", "/v1/sites/0123456789abcdef01234567/health/summary")
        self.assertEqual(op.operation_id, "site_overview")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match("GET", "/v1/sites/0123456789abcdef01234567/topology")
        self.assertEqual(op.operation_id, "site_topology")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/health/client/timeline")
        self.assertEqual(op.operation_id, "site_client_health_timeline")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/summary")
        self.assertEqual(op.operation_id, "site_wifi_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/6ghz-ap-presence")
        self.assertEqual(op.operation_id, "site_6ghz_ap_presence")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/settings/existence")
        self.assertEqual(op.operation_id, "site_setting_existence")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/aps/abcdef0123456789abcdef01/scan-status")
        self.assertEqual(op.operation_id, "ap_scan_status")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("device_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/gateways/abcdef0123456789abcdef01/ports")
        self.assertEqual(op.operation_id, "gateway_ports")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("device_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/gateways/abcdef0123456789abcdef01/speed-test-results")
        self.assertEqual(op.operation_id, "gateway_speed_test_results")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("device_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/gateways/abcdef0123456789abcdef01/internet-info")
        self.assertEqual(op.operation_id, "gateway_internet_info")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("device_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/gateways/abcdef0123456789abcdef01/dhcp/leases")
        self.assertEqual(op.operation_id, "gateway_dhcp_leases")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("gateway_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/gateways/abcdef0123456789abcdef01/lan-status")
        self.assertEqual(op.operation_id, "gateway_lan_status")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("device_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/aps/abcdef0123456789abcdef01/wired-downlink")
        self.assertEqual(op.operation_id, "ap_wired_downlink")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("device_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/aps/abcdef0123456789abcdef01/speed-test-results")
        self.assertEqual(op.operation_id, "ap_speed_test_results")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("device_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/aps/abcdef0123456789abcdef01/wifi-neighbors")
        self.assertEqual(op.operation_id, "ap_wifi_interference")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("device_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/history")
        self.assertEqual(op.operation_id, "experience_index")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/status")
        self.assertEqual(op.operation_id, "rf_planning_result")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/dashboard")
        self.assertEqual(op.operation_id, "rf_planning_dashboard")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/dashboard/current")
        self.assertEqual(op.operation_id, "rf_planning_dashboard_current")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/detail")
        self.assertEqual(op.operation_id, "rf_planning_detail")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/history/records")
        self.assertEqual(op.operation_id, "rf_planning_history")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/history/records/abcdef0123456789abcdef01")
        self.assertEqual(op.operation_id, "rf_planning_history_detail")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),
                                    ("history_ref", "abcdef0123456789abcdef01")))
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wifi/optimization/history/recent")
        self.assertEqual(op.operation_id, "rf_planning_recent_history")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        op, bindings = REGISTRY.match("GET", "/v1/sites/0123456789abcdef01234567/wifi/health/timeline")
        self.assertEqual(op.operation_id, "wifi_health")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))

    def test_registry_is_immutable_tuple_of_frozen_entries(self):
        self.assertIsInstance(REGISTRY.entries, tuple)
        with self.assertRaises((AttributeError, TypeError)):
            REGISTRY.entries[0].operation_id = "changed"
        with self.assertRaises((AttributeError, TypeError)):
            REGISTRY._entries = ()

    def test_duplicate_ids_and_normalized_route_collisions_rejected(self):
        a = Operation("one", "GET", "/v1/sites/{site_ref}/devices", "GET", "/up/{site_id}", (("site_id", "site_ref"),))
        with self.assertRaisesRegex(RegistryError, "duplicate operation id"):
            OperationRegistry((a, Operation("one", "GET", "/x", "GET", "/y")))
        b = Operation("two", "GET", "/V1/SITES/{other}/DEVICES", "GET", "/up/{site_id}", (("site_id", "site_ref"),))
        # Alternate public reference names are rejected too; normalized literal collision is checked first.
        with self.assertRaisesRegex(RegistryError, "normalized route collision"):
            OperationRegistry((a, b))

    def test_method_binding_and_limit_validation(self):
        with self.assertRaisesRegex(RegistryError, "unsupported method"):
            OperationRegistry((Operation("x", "POST", "/x", "GET", "/y"),))
        with self.assertRaisesRegex(RegistryError, "unbound upstream"):
            OperationRegistry((Operation("x", "GET", "/x/{site_ref}", "GET", "/y/{site_id}"),))
        with self.assertRaisesRegex(RegistryError, "reference-bound"):
            OperationRegistry((Operation("x", "GET", "/x/{site_ref}", "GET", "/y/{site_id}", (("site_id", "arbitrary"),)),))
        with self.assertRaisesRegex(RegistryError, "incident context"):
            OperationRegistry((Operation(
                "unsafe", "GET", "/v1/sites/{site_ref}/devices", "GET",
                "/openapi/v1/{mac}/devices", (("mac", "$incident_context_mac"),)),))
        with self.assertRaisesRegex(RegistryError, "response limit"):
            OperationRegistry((Operation("x", "GET", "/x", "GET", "/y", max_response_bytes=0),))
        with self.assertRaisesRegex(RegistryError, "item limit"):
            OperationRegistry((Operation("x", "GET", "/x", "GET", "/y", max_items=0),))

    def test_upstream_templates_are_fixed_and_no_write_entries_exist(self):
        self.assertEqual([e.operation_id for e in REGISTRY.entries], [
            "sites", "devices", "ap_overview", "clients", "site_client_identity_match", "networks", "network_dhcp_server_capabilities", "network_dhcp_server_info", "ssids", "site_mac_auth_ssid_inventory", "controller_health", "controller_threat_severity_summary", "controller_scenarios", "controller_scenario_differences", "site_threat_window_summary", "controller_gateway_wan_status_summary",
            "controller_client_recognition",
            "controller_device_statistics",
            "controller_client_active_timeout",
            "controller_client_history_retention",
            "controller_audit_notification",
            "controller_ui_interface",
            "controller_retention",
            "controller_dst_info",
            "controller_experience_improvement",
            "controller_client_detail_info",
            "controller_general_settings",
            "controller_device_access",
            "controller_backup_schedule",
            "controller_cloud_access",
            "controller_device_management",
            "controller_remote_binding",
            "controller_backup_result",
            "controller_restore_result",
            "controller_privacy_policy",
            "controller_mail_status",
            "controller_global_mfa_status",
            "msp_cloud_access_status",
            "msp_privacy_policy",
            "msp_client_detail_info",
            "msp_audit_notification",
            "msp_device_link_topology",
            "msp_device_tags",
            "msp_mfa_status",
            "msp_license_auto_active",
            "msp_customer_roles",
            "msp_dst_info",
            "msp_remote_logging",
            "msp_mail_server",
            "msp_general_settings",
            "msp_log_notification_settings",
            "msp_data_retention",
            "msp_ui_interface",
            "msp_user_interface",
            "msp_available_roles",
            "msp_available_customer_roles",
            "msp_dashboard_overall",
            "msp_cluster_nodes",
            "msp_adopt_tip",
            "msp_role_summary",
            "controller_remote_logging",
            "controller_remote_logging_tip",
            "controller_radius_proxy",
            "controller_radius_server",
            "controller_upgrade_port",
            "controller_portal_port_settings",
            "controller_port_settings",
            "controller_status",
            "controller_logging",
            "controller_certificate",
            "controller_roles",
            "controller_available_roles",
            "controller_known_devices",
            "controller_unknown_devices",
            "controller_device_batch_adopt_summary",
            "site_pending_devices_summary",
            "site_radius_user_summary",
            "site_templates",
            "site_template_upnp_summary",
            "site_template_igmp_summary",
            "site_template_ssh_summary",
            "site_template_iptv_summary",
            "site_template_iptv_settings_summary",
            "site_entity_summary",
            "site_switch_qos_mode",
            "site_switch_qos_scheduler_summary",
            "site_switch_qos_dscp_summary",
            "site_upnp_summary",
            "site_iot_aging_time",
            "site_iot_radio_summary",
            "site_mesh_summary",
            "site_multicast_rate_limit_summary",
            "site_beacon_control_summary",
            "site_iot_transmit_power_summary",
            "site_remember_setting_summary",
            "site_client_connection_summary",
            "site_poe_usage_summary",
            "site_device_counts_summary",
            "site_ipsec_tunnel_summary",
            "site_client_association_time_summary",
            "site_network_activity_summary",
            "site_client_rssi_distribution_summary",
            "site_ap_rssi_density_summary",
            "site_client_attachment_distribution_summary",
            "site_client_frequency_distribution_summary",
            "site_device_traffic_summary",
            "site_past_client_summary",
            "site_current_client_summary",
            "site_gateway_isp_summary",
            "site_top_ap_retry_drop_summary",
            "site_active_ap_summary",
            "site_active_ap_v2_summary",
            "site_hotspot_statistics_summary",
            "site_dashboard_all_tabs_summary",
            "site_dashboard_non_overall_tabs_summary",
            "site_allowed_application_summary",
            "site_blocked_application_summary",
            "site_specific_app_traffic_summary",
            "site_specific_client_traffic_summary",
            "site_application_traffic_summary",
            "site_wan_lan_status_summary",
            "site_arp_detect_status_summary",
            "site_disaster_mode_status",
            "site_specification_summary",
            "site_portal_logout_domain",
            "site_wids_config",
            "site_wips_config",
            "site_acl_config_mode",
            "site_attack_defense_summary",
            "site_attack_defense_defaults_summary",
            "site_alg_config",
            "site_firewall_settings",
            "site_firewall_defaults",
            "site_bandwidth_control",
            "site_wan_ports_summary",
            "site_vlan_network_summary",
            "site_lan_network_detail_summary",
            "site_lan_network_config_summary",
            "site_lan_network_inventory",
            "site_internet_load_balance_summary",
            "site_internet_basic_port_summary",
            "site_internet_summary",
            "site_vpn_session_summary",
            "site_dhcp_candidate_summary",
            "site_network_reservation_summary",
            "site_dhcp_reservation_summary",
            "site_dhcp_snooping_status",
            "site_dhcp_snoops_summary",
            "site_mdns_rule_summary",
            "site_ddns_summary",
            "site_snmp_settings_summary",
            "site_active_switch_summary",
            "site_device_memory_summary",
            "site_switch_dashboard_summary",
            "site_ap_interference_summary",
            "site_application_category_summary",
            "site_category_application_summary",
            "site_category_client_summary",
            "site_active_application_summary",
            "site_active_client_summary",
            "site_cpu_usage_summary",
            "site_client_bubble_summary",
            "site_traffic_activity_summary",
            "site_isp_load_summary",
            "site_vpn_tunnel_summary",
            "site_open_vpn_tunnel_summary",
            "site_client_activity_summary",
            "site_client_association_activity_summary",
            "site_client_traffic_summary",
            "site_gre_tunnel_summary",
            "site_ssl_vpn_summary",
            "site_ssh_summary",
            "site_mld_summary",
            "site_igmp_summary",
            "site_iptv_summary",
            "site_device_tag_summary",
            "site_overview", "site_health_timeline", "site_longest_client_uptime_summary",
            "site_topology",
            "site_stack_connections_summary",
            "site_client_health_timeline",
            "site_wifi_summary",
            "site_6ghz_ap_presence",
            "site_setting_existence",
            "site_capabilities",
            "site_duplicate_ssid_summary",
            "ssid_ap_groups",
            "site_topology_network_summary",
            "site_topology_vlan_summary",
            "site_unresolved_incident_count",
            "site_incident_overview",
            "site_incident_distribution",
            "site_incident_category_counts",
            "site_incident_list",
            "site_batch_interference_history",
            "site_batch_interference_ap_summary",
            "site_batch_wifi_interference_summary",
            "site_batch_channel_load_summary",
            "site_batch_interference_result_summary",
            "site_batch_interference_status_summary",
            "site_ap_full_channel_detect_status",
            "ap_interference_result_summary",
            "ap_channel_load_summary",
            "device_health_incidents",
            "client_health_incidents",
            "site_incident_detail",
            "site_incident_notification",
            "site_anomaly_event_settings",
            "site_incident_influencing_clients",
            "site_incident_influencing_devices",
            "site_wlan_group_capacity",
            "site_ap_group_capacity",
            "site_ap_group_summary",
            "site_ap_oui_vlan_rules_summary",
            "site_vlan_ssid_usage_summary",
            "site_vlan_device_usage_summary",
            "site_wifi_calling_profiles_summary",
            "site_client_filter_options_summary",
            "site_eap_dot1x_candidates_summary",
            "site_switch_dot1x_candidates_summary",
            "site_switch_support",
            "experience_index",
            "rf_planning_result",
            "rf_planning_dashboard",
            "rf_planning_dashboard_current",
            "rf_planning_detail",
            "rf_planning_history",
            "rf_planning_history_detail",
            "rf_planning_recent_history",
            "rf_planning_dashboard_history",
            "rf_excluded_aps",
            "rf_deploy_history",
            "wifi_health", "wifi_subhealth", "site_dashboard_channels",
            "site_client_signal_distribution",
            "band_steering", "rrm_settings", "roaming_settings", "site_led",
            "site_lldp", "site_dpi", "gateway_voip", "gateway_tag_qos",
            "ap_available_channels",
            "ap_available_channels_summary",
            "ap_speed_test_results",
            "ap_wired_downlink",
            "ap_ports",
            "ap_wired_uplink",
            "ap_radio_config",
            "ap_health",
            "msp_ap_health_detail",
            "msp_ap_health_timeline",
            "msp_ap_mesh_statistics",
            "ap_health_timeline",
            "ap_retry_drop",
            "ap_afc",
            "ap_radios",
            "ap_scan_status",
            "ap_channel_load",
            "ap_rf_scan",
            "ap_rf_scan_v2",
            "ap_lan_traffic",
            "ap_afc_status",
            "ap_mesh_statistics",
            "ap_channel_limit", "ap_ofdma", "ap_qos", "ap_lag", "ap_lag_config", "ap_load_balance",
            "ap_antenna", "ap_antenna_gain", "ap_power_saving", "ap_vlan",
            "ap_wifi_interference",
            "gateway_lan_status",
            "gateway_ports",
            "gateway_speed_test_results",
            "gateway_dhcp_leases",
            "gateway_internet_info",
            "gateway_wan_status",
            "gateway_wan_health",
            "gateway_health",
            "msp_gateway_health_detail",
            "msp_gateway_health_timeline",
            "gateway_health_timeline",
            "gateway_ipv6_ip_passthrough",
            "switch_ports",
            "switch_port_counters",
            "switch_port_poe_info",
            "switch_vlans",
            "switch_lldp_neighbors",
            "switch_health",
            "msp_switch_health_detail",
            "msp_switch_health_timeline",
            "switch_health_timeline",
            "site_switch_health_history",
            "switch_sdm_usage",
            "switch_cable_test_logs",
            "switch_cable_test_full_results",
            "switch_cable_test_increment_results",
            "switch_cable_test_ports",
            "switch_dhcp_users",
            "switch_ospf_neighbors",
            "switch_port_networks",
            "switch_exist_networks",
            "switch_networks",
            "switch_interfaces",
            "switch_routing_table",
            "switch_static_routes",
            "switch_vrfs",
            "switch_vlan_interfaces",
            "switch_statistics",
            "switch_port_tags",
            "switch_port_poe_mode",
            "switch_port_status",
            "gateway_firewall_rules",
            "switch_firewall_rules",
            "ap_firewall_rules",
            "site_channel_limit",
            "rrm_incompatible",
            "site_events",
            "site_events_window_summary",
            "site_alerts",
            "site_alerts_window_summary",
            "site_rogue_ap_results",
            "site_wids_summary",
            "site_wids_blacklist_summary",
            "site_speed_test_settings",
            "ap_uplink_config",
            "ap_lldp_config",
            "ap_port_vlans",
            "ap_bridge_config",
            "ap_mesh_candidates",
            "ap_general_config",
            "ap_ip_setting",
            "ap_ipv6_setting",
            "ap_p2p_info",
            "ap_l3_access",
            "ap_paring_window",
            "ap_management_ssid",
            "ap_snmp_config",
            "ap_vlan_v1",
            "ap_wlan_overrides",
            "device_firmware",
            "device_adopt_result",
            "device_mac_type",
            "device_link_topology",
            "device_radsec_support",
            "device_upgrade_result",
            "device_timeline",
            "device_inventory_summary",
            "olt_detail_summary",
            "olt_ports_summary",
            "msp_olt_detail_summary",
            "msp_olt_eth_config_summary",
            "msp_olt_site_ports_summary",
            "msp_olt_pon_port_config_summary",
            "olt_onu_global_status",
            "olt_onu_isolation_status",
            "olt_eth_config_summary",
            "olt_lag_config_summary",
            "olt_auto_refresh_summary",
            "olt_pon_information_summary",
            "olt_pon_port_config_summary",
            "olt_service_port_profiles_summary",
            "olt_onu_auto_auth_status",
            "olt_onu_autofind_summary",
            "olt_pon_port_config_page_summary",
            "olt_onu_autofind_inventory_summary",
            "olt_onu_inventory_summary",
            "olt_onu_reboot_status_summary",
            "olt_system_info",
            "olt_system_info_msp",
            "olt_management_interfaces",
            "client_detail",
            "wlan_groups",
            "site_wlan_group_detail_summary",
            "site_lock_to_ap_brief_inventory",
            "site_ineligible_interference_ap_summary",
            "site_interference_scan_eligible_summary",
            "site_wlan_group_summary",
            "site_wlan_group_ssids_summary",
            "ssid_configuration",
            "dhcp_leases",
            "dns_cache_settings",
            "dns_proxy_settings",
            "lan_dns_records",
            "client_connection_history",
            "client_history",
            "client_health",
            "client_health_timeline",
            "client_timeline_connect",
            "client_timeline_association",
            "client_timeline_roaming",
            "client_timeline_disconnect",
            "client_outage_timeline",
        ])
        self.assertTrue(all(e.public_method == "GET" and e.evidence == "unknown" for e in REGISTRY.entries))
        self.assertEqual([e.operation_id for e in REGISTRY.entries if e.upstream_method == "POST"],
                         ["site_batch_interference_status_summary"])
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", "/v1/sites")

    def test_site_radius_user_summary_uses_only_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/radius-users/summary")
        self.assertEqual(operation.operation_id, "site_radius_user_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))
        with self.assertRaises(RegistryError):
            REGISTRY.match("GET", f"/v1/sites/{site_ref}/radius-users/summary?username=admin")

    def test_site_arp_detect_status_uses_only_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/arp-detect-status-summary")
        self.assertEqual(operation.operation_id, "site_arp_detect_status_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))
        with self.assertRaises(RegistryError):
            REGISTRY.match("GET", f"/v1/sites/{site_ref}/arp-detect-status-summary?site_id=private")

    def test_site_disaster_mode_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/disaster-mode-status")
        self.assertEqual(operation.operation_id, "site_disaster_mode_status")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_specification_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/specification-summary")
        self.assertEqual(operation.operation_id, "site_specification_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_portal_logout_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/portal-logout-domain")
        self.assertEqual(operation.operation_id, "site_portal_logout_domain")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_wids_config_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wireless-ids-config")
        self.assertEqual(operation.operation_id, "site_wids_config")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_wips_config_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wireless-ips-config")
        self.assertEqual(operation.operation_id, "site_wips_config")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_acl_config_mode_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/acl-config-mode")
        self.assertEqual(operation.operation_id, "site_acl_config_mode")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_attack_defense_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/attack-defense-summary")
        self.assertEqual(operation.operation_id, "site_attack_defense_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_attack_defense_defaults_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/attack-defense/default-summary")
        self.assertEqual(operation.operation_id,
                         "site_attack_defense_defaults_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_alg_config_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/alg-config")
        self.assertEqual(operation.operation_id, "site_alg_config")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_firewall_settings_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/firewall-settings")
        self.assertEqual(operation.operation_id, "site_firewall_settings")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_firewall_defaults_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/firewall-defaults")
        self.assertEqual(operation.operation_id, "site_firewall_defaults")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_bandwidth_control_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/bandwidth-control")
        self.assertEqual(operation.operation_id, "site_bandwidth_control")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_wan_ports_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wan-ports-summary")
        self.assertEqual(operation.operation_id, "site_wan_ports_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_vlan_network_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/vlan-network-summary")
        self.assertEqual(operation.operation_id, "site_vlan_network_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_lan_network_config_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/lan-network-config-summary")
        self.assertEqual(operation.operation_id, "site_lan_network_config_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_lan_network_inventory_uses_opaque_site_reference(self):
        site_ref = "8" * 24
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/lan-networks/inventory")
        self.assertEqual(operation.operation_id, "site_lan_network_inventory")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_longest_client_uptime_uses_opaque_site_reference(self):
        site_ref = "8" * 24
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/dashboard/longest-client-uptime-summary")
        self.assertEqual(operation.operation_id, "site_longest_client_uptime_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_internet_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/internet-summary")
        self.assertEqual(operation.operation_id, "site_internet_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_internet_load_balance_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/internet/load-balance-summary")
        self.assertEqual(operation.operation_id, "site_internet_load_balance_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_internet_basic_port_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/internet/basic-port-summary")
        self.assertEqual(operation.operation_id, "site_internet_basic_port_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_wlan_group_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wlan-group-summary")
        self.assertEqual(operation.operation_id, "site_wlan_group_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_wlan_group_ssids_summary_requires_opaque_group_reference(self):
        site_ref = "0123456789abcdef01234567"
        group_ref = "89abcdef0123456789abcdef"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wlan-groups/{group_ref}/ssids-summary")
        self.assertEqual(operation.operation_id, "site_wlan_group_ssids_summary")
        self.assertEqual(bindings, (("site_ref", site_ref), ("wlan_group_ref", group_ref)))

    def test_site_wlan_group_detail_requires_opaque_group_reference(self):
        site_ref = "0123456789abcdef01234567"
        group_ref = "89abcdef0123456789abcdef"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wlan-groups/{group_ref}/detail")
        self.assertEqual(operation.operation_id, "site_wlan_group_detail_summary")
        self.assertEqual(bindings, (("site_ref", site_ref), ("wlan_group_ref", group_ref)))

    def test_site_lock_to_ap_brief_inventory_route_uses_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/lock-to-ap/ap-inventory")
        self.assertEqual(operation.operation_id, "site_lock_to_ap_brief_inventory")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_ineligible_interference_ap_summary_route_uses_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wifi/interference-ineligible-ap-summary")
        self.assertEqual(operation.operation_id,
                         "site_ineligible_interference_ap_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_batch_interference_ap_summary_route_uses_opaque_history_reference(self):
        site_ref = "a" * 24
        history_ref = "b" * 24
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wifi/interference-history/{history_ref}/ap-summary")
        self.assertEqual(operation.operation_id, "site_batch_interference_ap_summary")
        self.assertEqual(bindings, (("site_ref", site_ref), ("history_ref", history_ref)))

    def test_batch_wifi_interference_route_uses_opaque_history_reference(self):
        site_ref, history_ref = "a" * 24, "b" * 24
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wifi/interference-history/"
            f"{history_ref}/wifi-interference-summary")
        self.assertEqual(operation.operation_id, "site_batch_wifi_interference_summary")
        self.assertEqual(bindings, (("site_ref", site_ref), ("history_ref", history_ref)))

    def test_interference_scan_eligible_summary_route_uses_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/wifi/interference-scan-eligible-summary")
        self.assertEqual(operation.operation_id, "site_interference_scan_eligible_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_vpn_session_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/vpn-session-summary")
        self.assertEqual(operation.operation_id, "site_vpn_session_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_dhcp_candidate_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/dhcp-server-candidates")
        self.assertEqual(operation.operation_id, "site_dhcp_candidate_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_network_reservation_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/dhcp-reservation-summary")
        self.assertEqual(operation.operation_id, "site_network_reservation_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_dhcp_reservation_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/dhcp-reservations-summary")
        self.assertEqual(operation.operation_id, "site_dhcp_reservation_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_dhcp_snooping_status_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/dhcp-snooping-status")
        self.assertEqual(operation.operation_id, "site_dhcp_snooping_status")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_dhcp_snoops_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/dhcp-snoops-summary")
        self.assertEqual(operation.operation_id, "site_dhcp_snoops_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_mdns_rule_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/mdns-rule-summary")
        self.assertEqual(operation.operation_id, "site_mdns_rule_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_ddns_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/ddns-summary")
        self.assertEqual(operation.operation_id, "site_ddns_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_site_snmp_summary_route_uses_opaque_site_reference(self):
        site_ref = "0123456789abcdef01234567"
        operation, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{site_ref}/snmp-summary")
        self.assertEqual(operation.operation_id, "site_snmp_settings_summary")
        self.assertEqual(bindings, (("site_ref", site_ref),))

    def test_switch_port_read_routes_accept_only_bounded_numeric_indexes(self):
        site_ref, switch_ref = "a" * 24, "b" * 24
        for port in ("0", "1", "4096"):
            for suffix, operation_id in (("poe", "switch_port_poe_mode"),
                                         ("status", "switch_port_status")):
                path = f"/v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/{suffix}"
                self.assertEqual(REGISTRY.match("GET", path)[0].operation_id, operation_id)
        for port in ("4097", "9999", "-1", "0001"):
            with self.assertRaises(RegistryError):
                REGISTRY.match("GET", f"/v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/status")


if __name__ == "__main__":
    unittest.main()
