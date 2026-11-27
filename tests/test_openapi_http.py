from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from unittest.mock import patch

from app import main
from app.controller_system_status import project_controller_client_correction_options
from app.change_journal import ChangePlanJournal, derive_controller_binding
from app.device_upgrade_result import DeviceUpgradeResultError, project_device_upgrade_result
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_setting_existence import FIELDS
from app.site_capabilities import FIELDS as SITE_CAPABILITY_FIELDS
from app.site_switch_support import FIELDS as SITE_SWITCH_SUPPORT_FIELDS
from tests.test_wifi_diagnose import FIXED_DIAGNOSTIC_ROUTES, _complete_payloads
from tests.test_wifi_diagnose_ap import (
    AP_REF, OTHER_AP_REF, _ap_health_payload, _ap_radio_config_payload, _ap_rf_scan_payload,
    _ap_timeline_payload, _device,
)
from tests.test_wifi_diagnose_ap_lan_traffic import _lan_traffic_payload
from tests.test_incident_report_comparison import report as _incident_report


class FakeOpenApiClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.diagnostic_payloads = _complete_payloads("a" * 24)
        self.correction_options_result: dict[str, object] | None = None
        self.controller_scenarios_result: dict[str, object] | None = None
        self.session_limit_rule_coverage_source: dict[str, object] = {
            "totalRows": 0, "currentPage": 0, "currentSize": 0,
            "data": [], "supportIpAddress": False,
        }
        self.filter_inventory_total: int | None = None
        self.voucher_group_options_source: dict[str, object] = {
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}
        self.voucher_group_inventory_source: dict[str, object] = {
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}

    def list_sites(self) -> dict[str, object]:
        self.calls.append(("sites", None))
        return {"status": "ok", "resource": "sites", "count": 1,
                "items": [{"site_ref": "a" * 24}]}

    def read_controller_health(self) -> dict[str, object]:
        self.calls.append(("controller_health", None))
        return {"status": "ok", "resource": "controller_health", "data": {}}

    def read_controller_scenarios(self) -> dict[str, object]:
        self.calls.append(("controller_scenarios", None))
        if self.controller_scenarios_result is not None:
            return self.controller_scenarios_result
        return {"status": "ok", "resource": "controller_scenarios",
                "scenario_count": 2, "items": ["Wireless", "Switching"],
                "partial": False}

    def read_controller_scenario_differences(self) -> dict[str, object]:
        self.calls.append(("controller_scenario_differences", None))
        return {"status": "ok", "resource": "controller_scenario_differences",
                "scenario_count": 1, "returned_count": 1, "default_count": 1,
                "items": [{"name": "Default", "is_default": True}],
                "partial": False}

    def read_controller_threat_severity_summary(self, start_ms: int,
                                                end_ms: int) -> dict[str, object]:
        self.calls.append(("controller_threat_severity_summary", start_ms, end_ms))
        return {"status": "ok", "resource": "controller_threat_severity_summary",
                "counts": {"critical": 0, "major": 1, "moderate": 2,
                           "minor": 3, "low": 4}, "partial": False}

    def read_site_threat_window_summary(self, site_ref: str, start_ms: int,
                                        end_ms: int, archived: bool = False) -> dict[str, object]:
        self.calls.append(("site_threat_window_summary", site_ref, start_ms, end_ms, archived))
        return {"status": "ok", "resource": "site_threat_window_summary",
                "site_ref": site_ref, "counts": {"critical": 1},
                "partial": False}

    def read_controller_gateway_wan_status_summary(self, page_number: int,
                                                  page_size: int) -> dict[str, object]:
        self.calls.append(("controller_gateway_wan_status_summary", page_number, page_size))
        return {"status": "ok", "resource": "controller_gateway_wan_status_summary",
                "page_number": page_number, "page_size": page_size,
                "data": {"gateway_count": 1, "wan_port_count": 1}, "partial": False}

    def read_controller_client_recognition(self) -> dict[str, object]:
        self.calls.append(("controller_client_recognition", None))
        return {"status": "ok", "resource": "controller_client_recognition",
                "data": {"enabled": True, "present_count": 1, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}


    def read_controller_device_statistics(self) -> dict[str, object]:
        self.calls.append(("controller_device_statistics", None))
        return {"status": "ok", "resource": "controller_device_statistics",
                "data": {"counts": {"total_devices": 4}, "health_counts": {}, "present_count": 1,
                         "missing_count": 13, "invalid_count": 0,
                         "omitted_variant_field_count": 0, "unknown_field_count": 0},
                "partial": True}

    def read_controller_client_active_timeout(self) -> dict[str, object]:
        self.calls.append(("controller_client_active_timeout", None))
        return {"status": "ok", "resource": "controller_client_active_timeout",
                "data": {"active_timeout_minutes": 5, "present_count": 1,
                         "missing_count": 0, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_controller_client_history_retention(self) -> dict[str, object]:
        self.calls.append(("controller_client_history_retention", None))
        return {"status": "ok", "resource": "controller_client_history_retention",
                "data": {"client_history_enabled": True, "client_trend_enabled": False,
                         "present_count": 2, "missing_count": 0, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_controller_audit_notification(self) -> dict[str, object]:
        self.calls.append(("controller_audit_notification", None))
        return {"status": "ok", "resource": "controller_audit_notification",
                "data": {"webhook": {"enabled": True, "webhook_id_present": True},
                         "category_count": 2, "enabled_category_count": 1,
                         "omitted_label_count": 2, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_controller_ui_interface(self) -> dict[str, object]:
        self.calls.append(("controller_ui_interface", None))
        return {"status": "ok", "resource": "controller_ui_interface",
                "data": {"settings": {"time_zone_code": 1}, "redacted_presence": {},
                         "present_count": 1, "redacted_field_count": 0,
                         "missing_count": 6, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": True}

    def read_controller_retention(self) -> dict[str, object]:
        self.calls.append(("controller_retention", None))
        return {"status": "ok", "resource": "controller_retention",
                "data": {"flags": {"clients_data_enable": True},
                         "retention_values": {"known_client": 31},
                         "present_count": 2, "missing_count": 22,
                         "required_missing_count": 0, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": True}

    def read_controller_dst_info(self) -> dict[str, object]:
        self.calls.append(("controller_dst_info", None))
        return {"status": "ok", "resource": "controller_dst_info",
                "data": {"settings": {"enabled": False}, "time_rules": {},
                         "timestamps_ms": {}, "present_count": 1,
                         "missing_count": 12, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_site_dst_info(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_dst_info", site_ref))
        return {"status": "ok", "resource": "site_dst_info", "site_ref": site_ref,
                "data": {"settings": {"enabled": False}, "time_rules": {},
                         "timestamps_ms": {"nextStart": 456},
                         "timestamps_unit_unspecified": {"startTime": 123},
                         "present_count": 2,
                         "missing_count": 12, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_controller_experience_improvement(self) -> dict[str, object]:
        self.calls.append(("controller_experience_improvement", None))
        return {"status": "ok", "resource": "controller_experience_improvement",
                "data": {"experience_improvement_enabled": False, "present_count": 1,
                         "missing_count": 0, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_controller_firmware_email_reminder_status(self) -> dict[str, object]:
        self.calls.append(("controller_firmware_email_reminder_status", None))
        return {"status": "ok", "resource": "controller_firmware_email_reminder_status",
                "data": {"firmware_email_reminder_enabled": False, "present_count": 1,
                         "missing_count": 0, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_controller_client_detail_info(self) -> dict[str, object]:
        self.calls.append(("controller_client_detail_info", None))
        return {"status": "ok", "resource": "controller_client_detail_info",
                "data": {"settings": {"client_history_enable": True},
                         "present_count": 1, "missing_count": 4,
                         "invalid_count": 0, "unknown_field_count": 0},
                "partial": True}

    def read_controller_general_settings(self) -> dict[str, object]:
        self.calls.append(("controller_general_settings", None))
        return {"status": "ok", "resource": "controller_general_settings",
                "data": {"settings": {"time_zone": "Europe/Berlin"}, "dst": None,
                         "present_count": 1, "missing_count": 2,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": True}

    def read_controller_device_access(self) -> dict[str, object]:
        self.calls.append(("controller_device_access", None))
        return {"status": "ok", "resource": "controller_device_access",
                "data": {"settings": {"web_control_http": False,
                                        "web_control_https": True,
                                        "app_discovery": True},
                         "present_count": 3, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_controller_device_adoption_tip_summary(self) -> dict[str, object]:
        self.calls.append(("controller_device_adoption_tip_summary", None))
        return {"status": "ok", "resource": "controller_device_adoption_tip_summary",
                "data": {"adopted_device_count": 0, "recommended_device_count": 2},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_controller_placed_site_position_coverage(self) -> dict[str, object]:
        self.calls.append(("controller_placed_site_position_coverage", None))
        return {"status": "ok", "resource": "controller_placed_site_position_coverage",
                "source_state": "present", "placed_site_row_count": 2,
                "documented_field_count": 6, "documented_field_observed_count": 10,
                "documented_field_presence_count": 10,
                "documented_field_missing_count": 2,
                "documented_field_type_valid_count": 10,
                "documented_field_type_invalid_count": 0,
                "rows_with_all_documented_fields_count": 1,
                "unknown_field_count": 0, "coordinate_number_value_count": 4,
                "coordinate_object_shape_count": 0,
                "coordinate_invalid_shape_count": 0, "empty": False,
                "partial": True, "server_completeness_established": False}

    def read_controller_unplaced_site_position_coverage(self) -> dict[str, object]:
        self.calls.append(("controller_unplaced_site_position_coverage", None))
        return {"status": "ok", "resource": "controller_unplaced_site_position_coverage",
                "source_state": "present", "returned_count": 1,
                "reported_total_rows": 1, "reported_unplaced_num": 1,
                "omitted_count": 0, "page_truncated": False,
                "documented_field_coverage": {}, "partial": False}

    def read_controller_client_correction_options_summary(self) -> dict[str, object]:
        self.calls.append(("controller_client_correction_options_summary", None))
        if self.correction_options_result is not None:
            return self.correction_options_result
        return {"status": "ok", "resource": "controller_client_correction_options_summary",
                "data": {"type_options": [{"key": "type-a", "label": "Type A"}],
                         "vendor_options": [], "type_option_count": 1,
                         "vendor_option_count": 0, "ambiguous_option_count": 0},
                "partial": False}

    def read_controller_backup_schedule(self) -> dict[str, object]:
        self.calls.append(("controller_backup_schedule", None))
        return {"status": "ok", "resource": "controller_backup_schedule",
                "data": {"enabled": True, "retention_days": 30}, "partial": False}

    def read_controller_cloud_access(self) -> dict[str, object]:
        self.calls.append(("controller_cloud_access", None))
        return {"status": "ok", "resource": "controller_cloud_access",
                "data": {"enabled": True, "connection": "connected"}, "partial": False}

    def read_controller_device_management(self) -> dict[str, object]:
        self.calls.append(("controller_device_management", None))
        return {"status": "ok", "resource": "controller_device_management",
                "data": {"settings": {"web_control_http": True}}, "partial": False}

    def read_controller_remote_binding(self) -> dict[str, object]:
        self.calls.append(("controller_remote_binding", None))
        return {"status": "ok", "resource": "controller_remote_binding",
                "data": {"enabled": True}, "partial": False}

    def read_controller_backup_result(self) -> dict[str, object]:
        self.calls.append(("controller_backup_result", None))
        return {"status": "ok", "resource": "controller_backup_result",
                "data": {"status": "idle_or_finished"}, "partial": False}

    def read_controller_restore_result(self) -> dict[str, object]:
        self.calls.append(("controller_restore_result", None))
        return {"status": "ok", "resource": "controller_restore_result",
                "data": {"status": "prepared"}, "partial": False}

    def read_controller_privacy_policy(self) -> dict[str, object]:
        self.calls.append(("controller_privacy_policy", None))
        return {"status": "ok", "resource": "controller_privacy_policy",
                "data": {"enabled": True}, "partial": False}

    def read_controller_mail_status(self) -> dict[str, object]:
        self.calls.append(("controller_mail_status", None))
        return {"status": "ok", "resource": "controller_mail_status",
                "data": {"sender_configured": True, "authentication_enabled": True},
                "partial": False}

    def read_controller_global_mfa_status(self) -> dict[str, object]:
        self.calls.append(("controller_global_mfa_status", None))
        return {"status": "ok", "resource": "controller_global_mfa_status",
                "data": {"enabled": True}, "partial": False}

    def read_msp_cloud_access_status(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_cloud_access_status", msp_id))
        return {"status": "ok", "resource": "msp_cloud_access_status",
                "data": {"enabled": True, "connection": "connected"}, "partial": False}

    def read_msp_privacy_policy(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_privacy_policy", msp_id))
        return {"status": "ok", "resource": "msp_privacy_policy",
                "data": {"enabled": True}, "partial": False}

    def read_msp_client_detail_info(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_client_detail_info", msp_id))
        return {"status": "ok", "resource": "msp_client_detail_info",
                "data": {"settings": {"client_health_enable": True}}, "partial": True}

    def read_msp_audit_notification(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_audit_notification", msp_id))
        return {"status": "ok", "resource": "msp_audit_notification",
                "data": {"category_count": 2, "enabled_category_count": 1,
                         "webhook": {"enabled": True, "webhook_id_present": True}},
                "partial": False}

    def read_msp_device_link_topology(self, msp_ref: str, customer_ref: str,
                                      site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("msp_device_link_topology",
                           (msp_ref, customer_ref, site_ref, device_ref)))
        return {"status": "ok", "resource": "msp_device_link_topology",
                "data": {"node_count": 1, "edge_count": 0}, "partial": True}

    def read_msp_device_tags(self, msp_ref: str) -> dict[str, object]:
        self.calls.append(("msp_device_tags", msp_ref))
        return {"status": "ok", "resource": "msp_device_tags",
                "data": {"tag_count": 2, "tag_id_present_count": 2}, "partial": False}

    def read_msp_mfa_status(self, msp_ref: str) -> dict[str, object]:
        self.calls.append(("msp_mfa_status", msp_ref))
        return {"status": "ok", "resource": "msp_mfa_status",
                "data": {"enabled": True, "invalid_count": 0, "unknown_field_count": 0},
                "partial": False}

    def read_msp_license_auto_active(self, msp_ref: str) -> dict[str, object]:
        self.calls.append(("msp_license_auto_active", msp_ref))
        return {"status": "ok", "resource": "msp_license_auto_active",
                "data": {"enabled": False, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_msp_customer_roles(self, msp_ref: str) -> dict[str, object]:
        self.calls.append(("msp_customer_roles", msp_ref))
        return {"status": "ok", "resource": "msp_customer_roles",
                "data": {"role_count": 2, "default_role_count": 1}, "partial": False}

    def read_msp_dst_info(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_dst_info", msp_id))
        return {"status": "ok", "resource": "msp_dst_info",
                "data": {"settings": {"enabled": True, "time_zone": "UTC"}},
                "partial": False}

    def read_msp_remote_logging(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_remote_logging", msp_id))
        return {"status": "ok", "resource": "msp_remote_logging",
                "data": {"settings": {"enabled": True, "host_present": True,
                                          "port_present": True}}, "partial": False}

    def read_msp_mail_server(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_mail_server", msp_id))
        return {"status": "ok", "resource": "msp_mail_server",
                "data": {"settings": {"server_configured": True,
                                          "password_configured": True}},
                "partial": False}

    def read_msp_general_settings(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_general_settings", msp_id))
        return {"status": "ok", "resource": "msp_general_settings",
                "data": {"settings": {"name_configured": True,
                                          "time_zone": "UTC"}}, "partial": False}

    def read_msp_log_notification_settings(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_log_notification_settings", msp_id))
        return {"status": "ok", "resource": "msp_log_notification_settings",
                "data": {"settings": {"notification_count": 2,
                                          "email_enabled_count": 1}},
                "partial": False}

    def read_msp_data_retention(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_data_retention", msp_id))
        return {"status": "ok", "resource": "msp_data_retention",
                "data": {"flags": {"clients_data_enable": True},
                         "retention_values": {"known_client": 7}}, "partial": False}

    def read_msp_ui_interface(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_ui_interface", msp_id))
        return {"status": "ok", "resource": "msp_ui_interface",
                "data": {"settings": {"language_code": 4,
                                          "private_labeling_url_present": True}},
                "partial": False}

    def read_msp_user_interface(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_user_interface", msp_id))
        return {"status": "ok", "resource": "msp_user_interface",
                "data": {"settings": {"refresh_rate_code": 4}}, "partial": False}

    def read_msp_available_roles(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_available_roles", msp_id))
        return {"status": "ok", "resource": "msp_available_roles",
                "data": {"role_count": 3, "msp_created_role_count": 1}, "partial": False}

    def read_msp_available_customer_roles(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_available_customer_roles", msp_id))
        return {"status": "ok", "resource": "msp_available_customer_roles",
                "data": {"role_count": 2}, "partial": False}

    def read_msp_dashboard_overall(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_dashboard_overall", msp_id))
        return {"status": "ok", "resource": "msp_dashboard_overall",
                "data": {"total": 4, "wireless": 4}, "partial": False}

    def read_msp_cluster_nodes(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_cluster_nodes", msp_id))
        return {"status": "ok", "resource": "msp_cluster_nodes",
                "data": {"node_count": 2, "managed_sites": 4}, "partial": False}

    def read_msp_adopt_tip(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_adopt_tip", msp_id))
        return {"status": "ok", "resource": "msp_adopt_tip",
                "data": {"adopted_device_count": 4,
                         "recommended_device_count": 2}, "partial": False}

    def read_msp_role_summary(self, msp_id: str) -> dict[str, object]:
        self.calls.append(("msp_role_summary", msp_id))
        return {"status": "ok", "resource": "msp_role_summary",
                "data": {"role_count": 2, "roles_with_privileges": 2},
                "partial": False}

    def read_controller_remote_logging(self) -> dict[str, object]:
        self.calls.append(("controller_remote_logging", None))
        return {"status": "ok", "resource": "controller_remote_logging",
                "data": {"settings": {"enabled": True, "host_present": True,
                                        "port_present": True},
                         "present_count": 3, "missing_required_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_controller_remote_logging_tip(self) -> dict[str, object]:
        self.calls.append(("controller_remote_logging_tip", None))
        return {"status": "ok", "resource": "controller_remote_logging_tip",
                "data": {"settings": {"enabled": True, "host_present": True,
                                        "port_present": True},
                         "present_count": 3, "missing_required_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_controller_radius_proxy(self) -> dict[str, object]:
        self.calls.append(("controller_radius_proxy", None))
        return {"status": "ok", "resource": "controller_radius_proxy",
                "data": {"settings": {"enabled": False, "running": False,
                                        "port": 0, "failure_reason_present": True},
                         "present_count": 4, "missing_required_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_controller_upgrade_port(self) -> dict[str, object]:
        self.calls.append(("controller_upgrade_port", None))
        return {"status": "ok", "resource": "controller_upgrade_port",
                "data": {"settings": {"upgrade_https_port": 10443},
                         "present_count": 1, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_controller_portal_port_settings(self) -> dict[str, object]:
        self.calls.append(("controller_portal_port_settings", None))
        return {"status": "ok", "resource": "controller_portal_port_settings",
                "data": {"settings": {"http_port": 80, "https_port": 10443,
                                         "portal_host_present": True,
                                         "auto_portal_ip_enabled": True,
                                         "https_redirect_enabled": False},
                         "present_count": 5, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_controller_port_settings(self) -> dict[str, object]:
        self.calls.append(("controller_port_settings", None))
        return {"status": "ok", "resource": "controller_port_settings",
                "data": {"settings": {"http_port": 80, "https_port": 443,
                                         "host_name_present": True, "auto_refresh": False},
                         "present_count": 4, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_controller_status(self) -> dict[str, object]:
        self.calls.append(("controller_status", None))
        return {"status": "ok", "resource": "controller_status",
                "data": {"status": {"controller_version": "6.3.0", "uptime_seconds": 600},
                         "presence": {"macAddress": True}, "present_count": 3,
                         "missing_count": 0, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_controller_logging(self) -> dict[str, object]:
        self.calls.append(("controller_logging", None))
        return {"status": "ok", "resource": "controller_logging",
                "data": {"levels": {"type": "AUTO", "systemModule": "WARN"},
                         "present_count": 2, "missing_count": 6, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": True}

    def read_controller_certificate(self) -> dict[str, object]:
        self.calls.append(("controller_certificate", None))
        return {"status": "ok", "resource": "controller_certificate",
                "data": {"enabled": True, "field_presence": {"cerId": True,
                         "keyPassword": True}, "present_count": 3, "missing_count": 6,
                         "required_missing_count": 0, "invalid_count": 0,
                         "unknown_field_count": 0}, "partial": True}

    def read_controller_roles(self) -> dict[str, object]:
        self.calls.append(("controller_roles", None))
        return {"status": "ok", "resource": "controller_roles",
                "data": {"role_count": 2, "default_role_count": 1}, "partial": False}

    def read_controller_available_roles(self) -> dict[str, object]:
        self.calls.append(("controller_available_roles", None))
        return {"status": "ok", "resource": "controller_available_roles",
                "data": {"role_count": 1, "default_role_count": 1}, "partial": False}

    def read_controller_known_devices(self) -> dict[str, object]:
        self.calls.append(("controller_known_devices", None))
        return {"status": "ok", "resource": "controller_known_devices",
                "data": {"device_count": 4, "sampled_count": 4}, "partial": False}

    def read_controller_unknown_devices(self) -> dict[str, object]:
        self.calls.append(("controller_unknown_devices", None))
        return {"status": "ok", "resource": "controller_unknown_devices",
                "data": {"device_count": 1, "sampled_count": 1}, "partial": False}

    def read_controller_device_batch_adopt_summary(self) -> dict[str, object]:
        self.calls.append(("controller_device_batch_adopt_summary", None))
        return {"status": "ok", "resource": "controller_device_batch_adopt_summary",
                "data": {"sampled_count": 1}, "partial": False}

    def read_site_pending_devices_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_pending_devices_summary", site_ref))
        return {"status": "ok", "resource": "site_pending_devices_summary",
                "site_ref": site_ref, "data": {"device_count": 1, "sampled_count": 1},
                "partial": False}

    def read_device_adopt_result(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("device_adopt_result", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "device_adopt_result", "device_ref": device_ref,
                "data": {"adopt_error_code": 0, "credentials_required": False}}

    def read_device_mac_type(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("device_mac_type", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "device_mac_type", "device_ref": device_ref,
                "data": {"is_device": True, "device_type": "switch"}}

    def read_device_link_topology(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("device_link_topology", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "device_link_topology", "device_ref": device_ref,
                "data": {"node_count": 1, "edge_count": 0}}

    def read_device_radsec_support(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("device_radsec_support", site_ref))
        return {"status": "ok", "resource": "device_radsec_support",
                "data": {"unsupported_devices_exist": False}}

    def read_device_upgrade_result(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("device_upgrade_result", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "device_upgrade_result", "device_ref": device_ref,
                "data": {"finished": True, "success": False}}

    def read_device_timeline(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("device_timeline", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "device_timeline", "device_ref": device_ref,
                "window_seconds": 86400, "data": {"interval_count": 1,
                                                        "online_duration_ms": 1000}}

    def read_device_inventory_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("device_inventory_summary", site_ref))
        return {"status": "ok", "resource": "device_inventory_summary",
                "data": {"device_count": 2, "type_counts": {"access_point": 1,
                         "gateway": 0, "switch": 1, "other": 0},
                         "status_counts": [{"code": 1, "count": 2}]}, "partial": False}

    def read_olt_detail_summary(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_detail_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_detail_summary", "site_ref": site_ref,
                "device_ref": device_ref, "data": {"status_code": 14}, "partial": False}

    def read_olt_ports_summary(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_ports_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_ports_summary", "site_ref": site_ref,
                "device_ref": device_ref,
                "data": {"ethernet_port_count": 1, "pon_port_count": 1}, "partial": False}

    def read_olt_onu_global_status(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_onu_global_status", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_onu_global_status", "site_ref": site_ref,
                "device_ref": device_ref, "data": {"onu_isolation_enabled": True},
                "partial": False}

    def read_olt_onu_isolation_status(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_onu_isolation_status", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_onu_isolation_status", "site_ref": site_ref,
                "device_ref": device_ref, "data": {"vlan_list_configured": True},
                "partial": False}

    def read_olt_eth_config_summary(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_eth_config_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_eth_config_summary", "site_ref": site_ref,
                "device_ref": device_ref, "data": {"item_count": 1}, "partial": False}

    def read_olt_lag_config_summary(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_lag_config_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_lag_config_summary", "site_ref": site_ref,
                "device_ref": device_ref, "data": {"lag_count": 1}, "partial": False}

    def read_olt_auto_refresh_summary(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_auto_refresh_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_auto_refresh_summary", "site_ref": site_ref,
                "device_ref": device_ref, "data": {"auto_refresh_enabled": True}, "partial": False}

    def read_olt_pon_information_summary(self, site_ref: str,
                                         device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_pon_information_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_pon_information_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"pon_port_count": 1}, "partial": False}

    def read_olt_service_port_profiles_summary(self, site_ref: str,
                                               device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_service_port_profiles_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_service_port_profiles_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"profile_count": 1}, "partial": False}

    def read_olt_pon_port_config_page_summary(self, site_ref: str, device_ref: str,
                                              page_number: str, page_size: str) -> dict[str, object]:
        self.calls.append(("olt_pon_port_config_page_summary", page_number + ":" + page_size))
        return {"status": "ok", "resource": "olt_pon_port_config_page_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"pon_port_count": 1}, "page": {"page_number": int(page_number)},
                "partial": False}

    def read_olt_pon_port_config_summary(self, site_ref: str,
                                         device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_pon_port_config_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_pon_port_config_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"pon_port_count": 1}, "partial": False}

    def read_olt_onu_auto_auth_status(self, site_ref: str,
                                      device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_onu_auto_auth_status", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_onu_auto_auth_status",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"auto_authentication_enabled": False}, "partial": False}

    def read_olt_onu_autofind_summary(self, site_ref: str,
                                      device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_onu_autofind_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_onu_autofind_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"pon_port_scope_configured": True}, "partial": False}

    def read_olt_onu_autofind_inventory_summary(self, site_ref: str, device_ref: str,
                                                 pon_port: str, page_number: str,
                                                 page_size: str) -> dict[str, object]:
        self.calls.append(("olt_onu_autofind_inventory_summary", pon_port + ":" + page_number + ":" + page_size))
        return {"status": "ok", "resource": "olt_onu_autofind_inventory_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"discovered_onu_count": 1}, "partial": False}

    def read_olt_onu_inventory_summary(self, site_ref: str, device_ref: str,
                                       pon_port: str) -> dict[str, object]:
        self.calls.append(("olt_onu_inventory_summary", site_ref + ":" + device_ref + ":" + pon_port))
        return {"status": "ok", "resource": "olt_onu_inventory_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"onu_count": 1}, "partial": False}

    def read_olt_onu_reboot_status_summary(self, site_ref: str,
                                           device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_onu_reboot_status_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_onu_reboot_status_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"onu_count": 1}, "partial": False}

    def read_olt_system_info(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_system_info", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_system_info", "device_ref": device_ref,
                "data": {"uptime_seconds": 100, "ssh_enabled": True}}

    def read_olt_detail_summary(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_detail_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_detail_summary", "site_ref": site_ref,
                "device_ref": device_ref, "data": {"status_code": 14}, "partial": False}

    def read_olt_system_info_msp(self, msp_ref: str, customer_ref: str,
                                 site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_system_info_msp", ":".join((msp_ref, customer_ref, site_ref, device_ref))))
        return {"status": "ok", "resource": "olt_system_info_msp", "device_ref": device_ref,
                "data": {"uptime_seconds": 100, "ssh_enabled": True}}

    def read_msp_ap_health_detail(self, msp_ref: str, customer_ref: str,
                                  site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("msp_ap_health_detail", ":".join((msp_ref, customer_ref, site_ref, device_ref))))
        return {"status": "ok", "resource": "msp_ap_health_detail", "data": {"score": 80}}

    def read_msp_ap_mesh_statistics(self, msp_ref: str, customer_ref: str,
                                    site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("msp_ap_mesh_statistics", ":".join((msp_ref, customer_ref, site_ref, device_ref))))
        return {"status": "ok", "resource": "msp_ap_mesh_statistics", "data": {"wireless_linked": True}}

    def read_msp_olt_detail_summary(self, msp_ref, customer_ref, site_ref, device_ref):
        self.calls.append(("msp_olt_detail_summary", ":".join((msp_ref, customer_ref, site_ref, device_ref))))
        return {"status": "ok", "resource": "msp_olt_detail_summary"}

    def read_msp_olt_eth_config_summary(self, msp_ref, customer_ref, site_ref, device_ref):
        self.calls.append(("msp_olt_eth_config_summary", ":".join((msp_ref, customer_ref, site_ref, device_ref))))
        return {"status": "ok", "resource": "msp_olt_eth_config_summary"}

    def read_msp_olt_site_ports_summary(self, msp_ref, customer_ref, site_ref):
        self.calls.append(("msp_olt_site_ports_summary", ":".join((msp_ref, customer_ref, site_ref))))
        return {"status": "ok", "resource": "msp_olt_site_ports_summary"}

    def read_msp_olt_pon_port_config_summary(self, msp_ref, customer_ref, site_ref, device_ref):
        self.calls.append(("msp_olt_pon_port_config_summary", ":".join((msp_ref, customer_ref, site_ref, device_ref))))
        return {"status": "ok", "resource": "msp_olt_pon_port_config_summary"}

    def read_msp_gateway_health_detail(self, msp_ref: str, customer_ref: str,
                                       site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("msp_gateway_health_detail", ":".join((msp_ref, customer_ref, site_ref, gateway_ref))))
        return {"status": "ok", "resource": "msp_gateway_health_detail", "data": {"score": 80}}

    def read_msp_switch_health_detail(self, msp_ref: str, customer_ref: str,
                                      site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("msp_switch_health_detail", ":".join((msp_ref, customer_ref, site_ref, switch_ref))))
        return {"status": "ok", "resource": "msp_switch_health_detail", "data": {"score": 80}}

    def read_msp_ap_health_timeline(self, msp_ref: str, customer_ref: str,
                                    site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("msp_ap_health_timeline", ":".join((msp_ref, customer_ref, site_ref, device_ref))))
        return {"status": "ok", "resource": "msp_ap_health_timeline", "data": {"score_count": 1}}

    def read_msp_gateway_health_timeline(self, msp_ref: str, customer_ref: str,
                                         site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("msp_gateway_health_timeline", ":".join((msp_ref, customer_ref, site_ref, gateway_ref))))
        return {"status": "ok", "resource": "msp_gateway_health_timeline", "data": {"score_count": 1}}

    def read_msp_switch_health_timeline(self, msp_ref: str, customer_ref: str,
                                        site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("msp_switch_health_timeline", ":".join((msp_ref, customer_ref, site_ref, switch_ref))))
        return {"status": "ok", "resource": "msp_switch_health_timeline", "data": {"score_count": 1}}

    def read_olt_management_interfaces(self, site_ref: str,
                                       device_ref: str) -> dict[str, object]:
        self.calls.append(("olt_management_interfaces", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "olt_management_interfaces",
                "device_ref": device_ref,
                "data": {"interface_count": 1, "type_counts": {"MANAGEMENT": 1}}}


    def capabilities(self) -> dict[str, object]:
        self.calls.append(("capability_catalog", None))
        return {"status": "ok", "catalog_scope": "instrumented_openapi_operations",
                "catalog_complete": False, "items": [{
                    "operation": "devices", "route": "/v1/sites/{site_ref}/devices",
                    "support_state": "unknown", "implementation_state": "implemented",
                    "controller_response_evidence_count": 1,
                    "runtime_evidence": [{"target_ref": "private-reference",
                                           "controller_response_observed": True,
                                           "response_shape_state": "response_shape_supported",
                                           "support_state": "live_verified_supported",
                                           "permission_state": "allowed"}],
                }]}

    def read_site_topology(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_topology", site_ref))
        return {"status": "ok", "resource": "site_topology", "nodes": [], "edges": []}

    def read_site_topology_snapshot_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_topology_snapshot_summary", site_ref))
        return {"status": "ok", "resource": "site_topology_snapshot_summary",
                "site_ref": site_ref, "partial": False, "node_count": 0,
                "edge_count": 0}

    def read_site_gateway_qos_service_profiles_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_gateway_qos_service_profiles_summary", site_ref))
        return {"status": "ok", "resource": "site_gateway_qos_service_profiles_summary",
                "site_ref": site_ref, "partial": False, "profile_count": 0}

    def read_site_gateway_qos_service_reference_inventory(
            self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_gateway_qos_service_reference_inventory", site_ref))
        return {"status": "ok", "resource": "site_gateway_qos_service_reference_inventory",
                "partial": False, "source_scope": "single_unpaginated_response",
                "server_completeness_established": False, "row_count": 2, "empty": False,
                "id_present_count": 2, "id_missing_count": 0, "id_invalid_count": 0,
                "id_valid_count": 2, "id_unique_count": 2,
                "duplicate_reference_count": 0, "name_present_count": 2,
                "name_missing_count": 0, "name_invalid_count": 0,
                "name_valid_count": 2, "unknown_field_count": 0}

    def read_site_reboot_schedule_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_reboot_schedule_summary", site_ref))
        return {"status": "ok", "resource": "site_reboot_schedule_summary",
                "site_ref": site_ref, "schedules": [], "partial": False}

    def read_site_topology_network_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_topology_network_summary", site_ref))
        return {"status": "ok", "resource": "site_topology_network_summary",
                "site_ref": site_ref, "partial": False,
                "data": {"unknown_field_count": 0, "split_network_count": 2,
                         "default_network_count": 1, "configuring_network_count": 0,
                         "unknown_network_field_count": 0, "ssid_count": 3,
                         "ssid_vlan_enabled_count": 1, "ssid_configuring_count": 0,
                         "ssid_client_count_sum": 6, "ssid_vlan_id_count": 2,
                         "unknown_ssid_field_count": 0, "partial": False}}

    def read_gateway_wan_status(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_wan_status", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "gateway_wan_status", "device_ref": device_ref,
                "count": 1, "items": [{"port": 1, "link_status": 1, "latency_ms": 12}]}

    def read_gateway_info_summary(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_info_summary", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "gateway_info_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"model": "Gateway Model X", "firmware_version": "1.2.3",
                         "last_seen_source_value": 1_790_000_000_000},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_bridge_device_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_bridge_device_summary", site_ref))
        return {"status": "ok", "resource": "site_bridge_device_summary", "site_ref": site_ref,
                "adopted": {"source_total_rows": 1, "returned_rows": 1,
                            "coverage_complete": True, "by_source_status_code": {"2": 1},
                            "by_source_detail_status_code": {"1": 1},
                            "stack_groups": {"group_count": 1, "by_status_code": {"2": 1}},
                            "invalid_row_count": 0, "partial": False},
                "pending": {"source_total_rows": 0, "returned_rows": 0,
                            "coverage_complete": True, "by_source_status_code": {},
                            "by_source_detail_status_code": {},
                            "stack_groups": None, "invalid_row_count": 0, "partial": False},
                "partial": False, "identifiers_returned": False,
                "scope": "documented adopted/pending bridge-device grid reads only"}

    def compare_site_upnp_with_template(self, site_ref: str,
                                        site_template_ref: str) -> dict[str, object]:
        self.calls.append(("site_upnp_template_comparison", site_ref, site_template_ref))
        return {"status": "ok", "resource": "site_upnp_template_comparison",
                "site_ref": site_ref, "site_template_ref": site_template_ref,
                "compared_fields": ["enabled", "wan_port_count", "network_count",
                                    "supports_ds_lite_or_map_e"],
                "by_field": {"enabled": "same", "wan_port_count": "different",
                             "network_count": "same", "supports_ds_lite_or_map_e": "unknown"},
                "same_count": 2, "different_count": 1, "unknown_count": 1,
                "partial": True, "selection": "selected references only"}

    def read_site_wan_qos_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wan_qos_summary", site_ref))
        return {"status": "ok", "resource": "site_wan_qos_summary", "site_ref": site_ref,
                "wan_count": 1, "by_configured": {"true": 1}, "rule_count": 1,
                "rules_by_enabled_status": {"true": 1},
                "rules_by_direction": {"both": 1},
                "rules_by_exact_wan_match_and_configuration": {"true": {"true": 1}},
                "rules_with_exact_wan_match": 1, "rules_without_unique_wan_match": 0,
                "invalid_wan_rows": 0, "invalid_rule_fields_or_values": 0,
                "unknown_field_count": 0, "bandwidth_units": "not specified",
                "partial": False, "traffic_state": "configuration only"}

    def read_site_remote_access_tunnel_status_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_remote_access_tunnel_status_summary", site_ref))
        return {"status": "ok", "resource": "site_remote_access_tunnel_status_summary",
                "site_ref": site_ref, "reported_tunnel_count": 2,
                "by_documented_connection_status": {"connected": 1, "expired": 1},
                "by_documented_open_status": {"open": 1, "closed": 1, "unreported": 0},
                "identity_fields_returned": False}

    def read_site_ids_ips_config_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ids_ips_config_summary", site_ref))
        return {"status": "ok", "resource": "site_ids_ips_config_summary",
                "site_ref": site_ref,
                "enable": True, "ips_mode": 1, "dp_level": 2,
                "geo_enable": False,
                "custom_category_count": 2,
                "configuration_only": True}

    def read_site_wan_unsupported_function_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wan_unsupported_function_summary", site_ref))
        return {"status": "ok", "resource": "site_wan_unsupported_function_summary",
                "site_ref": site_ref, "result_state": "empty",
                "reported_limitation_entry_count": 0, "truncated": False}

    def read_site_vpn_server_status_summary(self, site_ref: str,
                                            vpn_type: int) -> dict[str, object]:
        self.calls.append(("site_vpn_server_status_summary", site_ref, vpn_type))
        return {"status": "ok", "resource": "site_vpn_server_status_summary",
                "site_ref": site_ref, "protocol": "ssl_vpn", "server_row_count": 2,
                "by_source_status_code": {"2": 2}, "missing_status_count": 0,
                "unknown_field_count": 0, "invalid_row_count": 0,
                "partial": False, "identity_fields_returned": False}

    def read_site_vpn_client_status_summary(self, site_ref: str,
                                            vpn_type: int) -> dict[str, object]:
        self.calls.append(("site_vpn_client_status_summary", site_ref, vpn_type))
        return {"status": "ok", "resource": "site_vpn_client_status_summary",
                "site_ref": site_ref, "protocol": "wireguard", "client_row_count": 2,
                "by_source_status_code": {"2": 2}, "missing_status_count": 0,
                "unknown_field_count": 0, "invalid_row_count": 0,
                "partial": False, "identity_fields_returned": False}

    def read_site_vpn_s2s_status_summary(self, site_ref: str,
                                         vpn_type: int) -> dict[str, object]:
        self.calls.append(("site_vpn_s2s_status_summary", site_ref, vpn_type))
        return {"status": "ok", "resource": "site_vpn_s2s_status_summary",
                "site_ref": site_ref, "vpn_type": vpn_type,
                "status_code_counts": {"0": 1}, "partial": False}

    def list_site_s2s_vpn_inventory_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_s2s_vpn_inventory_summary", site_ref))
        return {"status": "ok", "resource": "site_s2s_vpn_inventory_summary",
                "site_ref": site_ref, "reported_vpn_count": 1,
                "returned_vpn_count": 1, "items": [{"vpn_ref": "b" * 24}]}

    def read_site_vpn_server_config_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_vpn_server_config_summary", site_ref))
        return {"status": "ok", "resource": "site_vpn_server_config_summary",
                "site_ref": site_ref, "reported_server_total": 3,
                "by_documented_protocol": {"ipsec": 2, "wireguard": 1},
                "by_reported_activation_flag": {
                    "enabled": 2, "disabled": 1, "unreported": 0},
                "activation_semantics": "documented VPN status flag; not tunnel connectivity"}

    def read_site_vpn_client_config_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_vpn_client_config_summary", site_ref))
        return {"status": "ok", "resource": "site_vpn_client_config_summary",
                "site_ref": site_ref, "reported_client_total": 3,
                "by_documented_protocol": {"l2tp": 1, "wireguard": 2},
                "by_reported_configuration_flag": {
                    "true": 2, "false": 1, "unreported": 0},
                "configuration_flag_semantics":
                    "documented boolean VPN status flag; not tunnel connectivity"}

    def read_site_gateway_webfilter_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_gateway_webfilter_summary", site_ref))
        return {"status": "ok", "resource": "site_gateway_webfilter_summary",
                "site_ref": site_ref, "summarized_rule_count": 3,
                "by_documented_rule_type": {"gateway": 3, "ap": 0},
                "enabled_status_count": 2, "disabled_status_count": 1,
                "configuration_only": True}

    def read_site_ap_webfilter_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_webfilter_summary", site_ref))
        return {"status": "ok", "resource": "site_ap_webfilter_summary",
                "site_ref": site_ref, "reported_rule_total": 1,
                "by_documented_endpoint_rule_type": {"ap": 1, "gateway": 0, "unknown": 0},
                "raw_rules_urls_keywords_categories_schedules_and_sources_returned": False,
                "enforcement_inferred": False}

    def read_site_url_filter_general_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_url_filter_general_summary", site_ref))
        return {"status": "ok", "resource": "site_url_filter_general_summary",
                "site_ref": site_ref,
                "reported_settings": {"safeSearch": "enabled", "blockPage": "disabled"},
                "block_page_message_returned": False, "enforcement_inferred": False}

    def read_site_lan_interface_isolation_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lan_interface_isolation_summary", site_ref))
        return {"status": "ok", "resource": "site_lan_interface_isolation_summary",
                "site_ref": site_ref, "reported_interface_count": 2,
                "reported_isolation": {"isolated": 1, "not_isolated": 1,
                                        "unknown": 0, "missing": 0},
                "network_separation_inferred": False}

    def read_site_ospf_interface_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ospf_interface_summary", site_ref))
        return {"status": "ok", "resource": "site_ospf_interface_summary",
                "site_ref": site_ref, "reported_interface_total": 1,
                "by_documented_network_type": {"broadcast": 1},
                "ospf_neighbor_state_inferred": False}

    def read_site_switch_qos_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_qos_summary", site_ref))
        return {"status": "ok", "resource": "site_switch_qos_summary",
                "site_ref": site_ref, "reported_rule_total": 2,
                "by_documented_rule_type": {"network": 1, "port": 1, "custom": 0},
                "traffic_behavior_inferred": False}

    def read_site_switch_ddm_summary(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_ddm_summary", site_ref, device_ref))
        return {"status": "ok", "resource": "site_switch_ddm_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "reported_optical_module_count": 1,
                "device_health_inferred": False}

    def read_site_gateway_qos_class_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_gateway_qos_class_summary", site_ref))
        return {"status": "ok", "resource": "site_gateway_qos_class_summary",
                "site_ref": site_ref, "summarized_rule_count": 2,
                "enabled_state_counts": {"enabled": 1, "disabled": 1},
                "documented_ip_version_counts": {"0": 1, "1": 1},
                "documented_class_counts": {"1": 1, "3": 1},
                "traffic_state": "configuration only"}

    def read_site_s2s_vpn_v2_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_s2s_vpn_v2_summary", site_ref))
        return {"status": "ok", "resource": "site_s2s_vpn_v2_summary",
                "site_ref": site_ref, "reported_vpn_count": 2,
                "status_scope": "documented_vpn_boolean_not_tunnel_connectivity",
                "partial": False}

    def read_site_s2s_peer_status_summary(self, site_ref: str,
                                         vpn_ref: str) -> dict[str, object]:
        self.calls.append(("site_s2s_peer_status_summary", site_ref, vpn_ref))
        return {"status": "ok", "resource": "site_s2s_peer_status_summary",
                "site_ref": site_ref, "vpn_ref": vpn_ref, "reported_peer_count": 2,
                "peer_status_counts": {"connected": 1, "disconnected": 1, "unknown": 0}}

    def read_site_ssid_client_count_summary(self, site_ref: str,
                                            ssid_ref: str) -> dict[str, object]:
        self.calls.append(("site_ssid_client_count_summary", site_ref, ssid_ref))
        return {"status": "ok", "resource": "site_ssid_client_count_summary",
                "site_ref": site_ref, "ssid_ref": ssid_ref, "client_count": 12,
                "sampled_client_count": 12, "sample_page": 1, "sample_page_size": 100,
                "coverage_complete": True, "client_details_returned": False,
                "online_status_provided": False}

    def read_site_ssid_topology_device_summary(self, site_ref: str,
                                               ssid_ref: str) -> dict[str, object]:
        self.calls.append(("site_ssid_topology_device_summary", site_ref, ssid_ref))
        return {"status": "ok", "resource": "site_ssid_topology_device_summary",
                "site_ref": site_ref, "ssid_ref": ssid_ref,
                "device_class_counts": {"ap": 1, "gateway": 0, "switch": 0, "olt": 0},
                "partial": False}

    def read_site_ssid_topology_reference_count(self, site_ref: str,
                                                ssid_ref: str) -> dict[str, object]:
        self.calls.append(("site_ssid_topology_reference_count", site_ref, ssid_ref))
        return {"status": "ok", "resource": "site_ssid_topology_reference_count",
                "site_ref": site_ref, "ssid_ref": ssid_ref, "reference_count": 2,
                "reference_semantics": "opaque_string"}

    def read_site_vlan_topology_reference_count(self, site_ref: str, network_ref: str,
                                                vlan_id: int) -> dict[str, object]:
        self.calls.append(("site_vlan_topology_reference_count", site_ref, network_ref, vlan_id))
        return {"status": "ok", "resource": "site_vlan_topology_reference_count",
                "site_ref": site_ref, "network_ref": network_ref, "vlan_id": vlan_id,
                "reference_count": 1, "reference_semantics": "opaque_string"}

    def read_site_ap_topology_clients_summary(self, site_ref: str,
                                              device_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_topology_clients_summary", site_ref, device_ref))
        return {"status": "ok", "resource": "site_ap_topology_clients_summary",
                "site_ref": site_ref, "device_ref": device_ref,
                "topology_client_count": 2,
                "by_connection": {"wireless": 1, "wired": 1, "unknown": 0}}

    def read_site_network_delivery_summary(self, site_ref: str,
                                           network_ref: str) -> dict[str, object]:
        self.calls.append(("site_network_delivery_summary", site_ref, network_ref))
        return {"status": "ok", "resource": "site_network_delivery_summary",
                "site_ref": site_ref, "network_ref": network_ref,
                "state": "delivering", "done_device_count": 1,
                "total_device_count": 2,
                "device_counts": {"succeeded": 1, "failed": 0, "delivering": 1}}

    def read_site_lan_port_profiles_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lan_port_profiles_summary", site_ref))
        return {"status": "ok", "resource": "site_lan_port_profiles_summary",
                "site_ref": site_ref, "profile_count": 2,
                "profile_enum_counts": {"type": {"2": 2}},
                "profile_names_and_ids_returned": False}

    def read_site_lan_switch_profile_assignments_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lan_switch_profile_assignments_summary", site_ref))
        return {"status": "ok", "resource": "site_lan_switch_profile_assignments_summary",
                "site_ref": site_ref, "device_rows": 2, "profile_assignment_count": 3,
                "identifiers_returned": False}

    def read_controller_upgrade_plans_summary(self) -> dict[str, object]:
        self.calls.append(("controller_upgrade_plans_summary",))
        return {"status": "ok", "resource": "controller_upgrade_plans_summary",
                "plan_count": 1, "total_count": 1,
                "field_presence": {"scheduled_time": {"present": 1, "missing": 0}},
                "scheduled_time_interpreted": False}

    def read_controller_try_beta_settings_summary(self) -> dict[str, object]:
        self.calls.append(("controller_try_beta_settings_summary",))
        return {"status": "ok", "resource": "controller_try_beta_settings_summary",
                "preview_firmware_enabled": None, "preview_firmware_channel": "unknown",
                "partial": True}

    def read_controller_auto_check_upgrade_summary(self) -> dict[str, object]:
        self.calls.append(("controller_auto_check_upgrade_summary",))
        return {"status": "ok", "resource": "controller_auto_check_upgrade_summary",
                "plan_count": 0, "channel_counts": {}, "site_association_count": 0,
                "partial": False}

    def read_controller_firmware_pool_channel_counts(self) -> dict[str, object]:
        self.calls.append(("controller_firmware_pool_channel_counts",))
        return {"status": "ok", "resource": "controller_firmware_pool_channel_counts",
                "channel_counts": {"stable": 0, "release_candidate": 2, "beta": 3},
                "partial": False}

    def read_controller_firmware_inventory_summary(self) -> dict[str, object]:
        self.calls.append(("controller_firmware_inventory_summary",))
        return {"status": "ok", "resource": "controller_firmware_inventory_summary",
                "firmware_entry_count": 0, "partial": False}

    def read_site_agile_switch_general_config_summary(
            self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("site_agile_switch_general_config_summary", site_ref, switch_ref))
        return {"status": "ok", "resource": "site_agile_switch_general_config_summary",
                "site_ref": site_ref, "switch_ref": switch_ref, "partial": False}

    def read_controller_try_beta_settings_summary(self) -> dict[str, object]:
        self.calls.append(("controller_try_beta_settings_summary",))
        return {"status": "ok", "resource": "controller_try_beta_settings_summary",
                "preview_firmware_enabled": None, "preview_firmware_channel": "unknown",
                "partial": True}

    def read_controller_auto_check_upgrade_summary(self) -> dict[str, object]:
        self.calls.append(("controller_auto_check_upgrade_summary",))
        return {"status": "ok", "resource": "controller_auto_check_upgrade_summary",
                "plan_count": 0, "channel_counts": {}, "site_association_count": 0,
                "partial": False}

    def read_controller_global_log_notification_summary(self) -> dict[str, object]:
        self.calls.append(("controller_global_log_notification_summary",))
        return {"status": "ok", "resource": "controller_global_log_notification_summary",
                "notification_category_count": 2,
                "channel_switch_counts": {"alert": {"enabled": 1, "disabled": 1,
                                                       "missing": 0}}}

    def read_controller_upgrade_model_list_summary(self) -> dict[str, object]:
        self.calls.append(("controller_upgrade_model_list_summary",))
        return {"status": "ok", "resource": "controller_upgrade_model_list_summary",
                "reported_model_count": 2, "returned_model_count": 2,
                "upgrade_status_counts": {"up_to_date": 1,
                                           "new_version_available": 1, "unknown": 0}}

    def read_site_lan_multicast_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lan_multicast_summary", site_ref))
        return {"status": "ok", "resource": "site_lan_multicast_summary",
                "site_ref": site_ref, "configuration_count": 1,
                "protocol_counts": {"igmp": 1, "mld": 0, "unknown": 0},
                "configuration_only_no_multicast_traffic_inferred": True}

    def read_site_hotspot_rate_limit_profiles_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_hotspot_rate_limit_profiles_summary", site_ref))
        return {"status": "ok", "resource": "site_hotspot_rate_limit_profiles_summary",
                "profile_count": 1,
                "directional_coverage": {"downstream": {"enabled_limit_kbps": {
                    "count": 1, "sum": 256, "min": 256, "max": 256}}},
                "partial": False}

    def read_site_rate_limit_profiles_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_rate_limit_profiles_summary", site_ref))
        return {"status": "ok", "resource": "site_rate_limit_profiles_summary",
                "site_ref": site_ref, "profile_count": 2,
                "directional_coverage": {
                    "downstream": {"enabled_limit_kbps": {
                        "count": 1, "sum": 20000000, "min": 20000000, "max": 20000000}},
                    "upstream": {"enabled_limit_kbps": {
                        "count": 1, "sum": 3000000, "min": 3000000, "max": 3000000}}},
                "partial": False}

    def read_site_bandwidth_rules_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_bandwidth_rules_summary", site_ref))
        return {"status": "ok", "resource": "site_bandwidth_rules_summary",
                "site_ref": site_ref, "rule_count": 2,
                "activation_counts": {"enabled": 1, "disabled": 1, "unknown": 0},
                "bandwidth_unit_counts": {"upstream": {"kbps": 1, "mbps": 1,
                                                            "unknown": 0}},
                "actual_traffic_inferred": False}

    def read_site_log_notification_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_log_notification_summary", site_ref))
        return {"status": "ok", "resource": "site_log_notification_summary",
                "site_ref": site_ref, "notification_category_count": 3,
                "channel_enablement_counts": {"alert": {"enabled": 1, "disabled": 2,
                                                            "unknown": 0}},
                "external_destination_or_delivery_inferred": False}

    def read_site_voucher_all_time_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_voucher_all_time_summary", site_ref))
        return {"status": "ok", "resource": "site_voucher_all_time_summary",
                "site_ref": site_ref, "voucher_counts": {},
                "voucher_durations_minutes": {},
                "voucher_traffic_statistics_supported": None,
                "missing_fields": [], "invalid_fields": [], "partial": False}

    def read_site_voucher_currency_options(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_voucher_currency_options", site_ref))
        return {"status": "ok", "resource": "site_voucher_currency_options",
                "site_ref": site_ref,
                "data": {"currency_codes": ["X1"], "currency_code_count": 1,
                         "currency_list_present": True, "currency_list_row_count": 1,
                         "selected_currency_field_present": True,
                         "selected_currency_code": "Y2", "missing_field_count": 0,
                         "invalid_value_count": 0, "duplicate_currency_code_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_site_hotspot_voucher_group_options_coverage(self, site_ref: str) -> dict[str, object]:
        from app.site_hotspot_voucher_group_options_coverage import (
            SiteHotspotVoucherGroupOptionsCoverageError,
            project_site_hotspot_voucher_group_options_coverage,
        )

        self.calls.append(("site_hotspot_voucher_group_options_coverage", site_ref))
        try:
            projected = project_site_hotspot_voucher_group_options_coverage(
                self.voucher_group_options_source)
        except SiteHotspotVoucherGroupOptionsCoverageError:
            raise OpenApiError("openapi_response_invalid") from None
        return {"status": "ok", "resource": "site_hotspot_voucher_group_options_coverage",
                "site_ref": site_ref,
                **projected}

    def read_site_hotspot_voucher_group_inventory_coverage(self, site_ref: str) -> dict[str, object]:
        from app.site_hotspot_voucher_group_inventory_coverage import (
            SiteVoucherGroupInventoryCoverageError,
            project_site_voucher_group_inventory_coverage,
        )

        self.calls.append(("site_hotspot_voucher_group_inventory_coverage", site_ref))
        try:
            projected = project_site_voucher_group_inventory_coverage(
                self.voucher_group_inventory_source)
        except SiteVoucherGroupInventoryCoverageError:
            raise OpenApiError("openapi_response_invalid") from None
        return {"status": "ok", "resource": "site_hotspot_voucher_group_inventory_coverage",
                "site_ref": site_ref, **projected}

    def read_site_lan_network_interface_summary(self, site_ref: str,
                                                interface_type: int | None = None) -> dict[str, object]:
        self.calls.append(("site_lan_network_interface_summary", site_ref, interface_type))
        return {"status": "ok", "resource": "site_lan_network_interface_summary",
                "site_ref": site_ref, "network_count": 2,
                "purpose_counts": {"vlan": 1, "interface": 1, "unknown": 0},
                "interface_vlan_type_counts": {"single": 1, "multiple": 0, "unknown": 0},
                "router_or_vlan_mapping_inferred_from_interface_ids": False}

    def read_site_remote_logging_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_remote_logging_summary", site_ref))
        return {"status": "ok", "resource": "site_remote_logging_summary",
                "site_ref": site_ref, "enabled": True, "client_logs_enabled": False,
                "resource_source": "template", "destination_host_configured": True,
                "destination_port_configured": True, "destination_values_returned": False,
                "partial": False, "delivery_success": "not assessed"}

    def read_controller_upgrade_log_summary(self) -> dict[str, object]:
        self.calls.append(("controller_upgrade_log_summary", None))
        return {"status": "ok", "resource": "controller_upgrade_log_summary",
                "source_total_rows": 1, "sampled_log_count": 1,
                "sample_page": 1, "sample_page_size": 100, "coverage_complete": True,
                "rollbacked_counts": {"true": 0, "false": 1},
                "logs_with_failed_devices_count": 0, "partial": False,
                "identities_and_versions_returned": False}

    def read_controller_upgrade_log_inventory(self, page_number: int,
                                              page_size: int) -> dict[str, object]:
        self.calls.append(("controller_upgrade_log_inventory", page_number, page_size))
        return {"status": "ok", "resource": "controller_upgrade_log_inventory",
                "page_number": page_number, "page_size": page_size,
                "upgrade_log_refs": [], "reported_log_count": 0}

    def read_controller_upgrade_failed_devices_summary(self,
                                                        upgrade_log_ref: str) -> dict[str, object]:
        self.calls.append(("controller_upgrade_failed_devices_summary", upgrade_log_ref))
        return {"status": "ok", "resource": "controller_upgrade_failed_devices_summary",
                "upgrade_log_ref": upgrade_log_ref, "failed_device_count": 0}

    def read_controller_sdwan_group_summary(self) -> dict[str, object]:
        self.calls.append(("controller_sdwan_group_summary", None))
        return {"status": "ok", "resource": "controller_sdwan_group_summary",
                "returned_group_count": 2,
                "reported_group_device_membership_sum": 8,
                "partial": False}

    def read_controller_sdwan_group_devices_summary(self, group_ref: str) -> dict[str, object]:
        self.calls.append(("controller_sdwan_group_devices_summary", group_ref))
        return {"status": "ok", "resource": "controller_sdwan_group_devices_summary",
                "group_ref": group_ref, "reported_device_count": 2,
                "by_reported_sdwan_nat_capability": {
                    "true": 1, "false": 1, "unreported": 0},
                "device_identities_and_addresses_returned": False}

    def read_site_ipsec_sa_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ipsec_sa_summary", site_ref))
        return {"status": "ok", "resource": "site_ipsec_sa_summary",
                "site_ref": site_ref, "security_association_count": 2,
                "by_direction": {"in": 1, "out": 1},
                "missing_direction_count": 0, "invalid_row_count": 0,
                "invalid_field_count": 0, "unknown_field_count": 0,
                "partial": False,
                "connection_status": "not provided by the source contract; tunnel state is unknown"}

    def read_site_policy_route_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_policy_route_summary", site_ref))
        return {"status": "ok", "resource": "site_policy_route_summary",
                "site_ref": site_ref, "count": 1,
                "summary": {"by_source_type": {"network": 1},
                            "by_destination_type": {"ip_group": 1},
                            "by_interface_type": {"wan": 1},
                            "by_enabled": {"true": 1},
                            "reference_occurrences": {"source": 1},
                            "index_count": 1, "indices_unique": True,
                            "unknown_fields": 0, "invalid_fields": 0,
                            "invalid_rows": 0}, "partial": False,
                "ordering": "indices observed without precedence inference"}

    def read_site_static_route_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_static_route_summary", site_ref))
        return {"status": "ok", "resource": "site_static_route_summary",
                "site_ref": site_ref, "count": 2,
                "summary": {"by_type": {"interface": 1, "next_hop": 1},
                            "by_status": {"true": 2},
                            "reference_occurrences": {"interface": 1},
                            "unknown_rows": 0}, "partial": False}

    def read_site_static_route_interface_options_summary(
            self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_static_route_interface_options_summary", site_ref))
        return {"status": "ok", "resource": "site_static_route_interface_options_summary",
                "site_ref": site_ref, "scope": "static_route_selection_options",
                "available_interface_option_count": 2}

    def read_site_wlan_group_ssid_config_summary(
            self, site_ref: str, wlan_group_ref: str, ssid_ref: str) -> dict[str, object]:
        self.calls.append(("site_wlan_group_ssid_config_summary", site_ref,
                           wlan_group_ref, ssid_ref))
        return {"status": "ok", "resource": "site_wlan_group_ssid_config_summary",
                "site_ref": site_ref, "wlan_group_ref": wlan_group_ref,
                "ssid_ref": ssid_ref,
                "ssid_enabled": True,
                "band_enabled": {"2.4ghz": True, "5ghz": True, "6ghz": False},
                "device_type_enabled": {"eap": True, "gateway": True},
                "partial": False}

    def read_gateway_wan_health(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_wan_health", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "gateway_wan_health", "device_ref": device_ref,
                "wan_details": [], "count": 0, "partial": False}

    def read_gateway_health(self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_health", site_ref + ":" + gateway_ref))
        return {"status": "ok", "resource": "gateway_health", "site_ref": site_ref,
                "gateway_ref": gateway_ref, "data": {"score": 80},
                "window_start_ms": 100, "window_end_ms": 200}

    def read_gateway_health_timeline(self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_health_timeline", site_ref + ":" + gateway_ref))
        return {"status": "ok", "resource": "gateway_health_timeline", "site_ref": site_ref,
                "gateway_ref": gateway_ref, "data": {"scores": []}, "partial": False}

    def read_gateway_lan_status(self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_lan_status", site_ref + ":" + gateway_ref))
        return {"status": "ok", "resource": "gateway_lan_status", "site_ref": site_ref,
                "device_ref": gateway_ref, "count": 0, "source_count": 0, "items": [],
                "partial": False, "omitted_count": 0, "unknown_field_count": 0,
                "redacted_field_count": 0}

    def read_gateway_ports(self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_ports", site_ref + ":" + gateway_ref))
        return {"status": "ok", "resource": "gateway_ports", "site_ref": site_ref,
                "device_ref": gateway_ref, "count": 0, "source_count": 0, "items": [],
                "partial": False, "omitted_count": 0, "unknown_field_count": 0,
                "redacted_field_count": 0}

    def read_site_ipsec_failover_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ipsec_failover_summary", site_ref))
        return {"status": "ok", "resource": "site_ipsec_failover_summary",
                "site_ref": site_ref, "rule_count": 1, "reported_rule_count": 1,
                "primary_reference_count": 1, "primary_reference_unknown_count": 0,
                "candidate_reference_count": 2, "candidate_list_unknown_count": 0,
                "failback_enabled_count": 1, "failback_disabled_count": 0,
                "failback_unknown_count": 0, "failback_time_field_present_count": 1,
                "failback_time_field_missing_count": 0, "partial": False,
                "identifier_values_returned": False, "tunnel_status_returned": False,
                "failback_time_values_returned": False, "deprecated_source_endpoint": True}

    def read_site_gateway_sim_sms_support_summary(
            self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("site_gateway_sim_sms_support_summary", site_ref + ":" + gateway_ref))
        return {"status": "ok", "resource": "site_gateway_sim_sms_support_summary",
                "site_ref": site_ref, "gateway_ref": gateway_ref,
                "sim_sms_supported": None, "lte_supported": True,
                "dual_sms_supported_sim_count": 0, "dual_sms_state": "known",
                "dual_sim_capability": "unknown", "dual_sim_source_value_present": False}

    def read_gateway_internet_info(self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_internet_info", site_ref + ":" + gateway_ref))
        return {"status": "ok", "resource": "gateway_internet_info", "site_ref": site_ref,
                "device_ref": gateway_ref, "data": {"support": {}, "settings": {},
                "online_detection_code_counts": {}, "partial": False,
                "unknown_field_count": 0, "redacted_field_count": 0}}

    def list_gateway_dhcp_leases(self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_dhcp_leases", site_ref + ":" + gateway_ref))
        return {"status": "ok", "resource": "gateway_dhcp_leases", "site_ref": site_ref,
                "device_ref": gateway_ref, "count": 0, "items": [],
                "summary": {"total": 0, "devices": 0, "clients": 0, "dynamic": 0, "static": 0}}

    def read_gateway_speed_test_results(self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("gateway_speed_test_results", site_ref + ":" + gateway_ref))
        return {"status": "ok", "resource": "gateway_speed_test_results", "site_ref": site_ref,
                "device_ref": gateway_ref, "data": {"status_code": 0, "count": 0,
                "source_count": 0, "items": [], "partial": False, "omitted_count": 0,
                "unknown_field_count": 0, "redacted_field_count": 0}}

    def read_site_speed_test_settings(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_speed_test_settings", site_ref))
        return {"status": "ok", "resource": "speed_test_settings", "site_ref": site_ref,
                "data": {"auto_speed_test": False, "timing_type": 1}, "partial": False,
                "omitted_field_count": 0, "omitted_fields": []}

    def read_ap_uplink_config(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("ap_uplink_config", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "ap_uplink_config", "site_ref": site_ref,
                "device_ref": device_ref, "count": 1, "items": [{"auto": True, "port": "1"}],
                "partial": False, "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0}

    def read_ap_lldp_config(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("ap_lldp_config", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "ap_lldp_config", "site_ref": site_ref,
                "device_ref": device_ref,
                "data": {"setting_code": 2, "setting": "site_default", "supported": True},
                "partial": False, "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0}

    def read_site_client_health_timeline(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_health_timeline", site_ref))
        return {"status": "ok", "resource": "site_client_health_timeline", "site_ref": site_ref,
                "data": {"scores": []}}

    def read_site_wifi_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wifi_summary", site_ref))
        return {"status": "ok", "resource": "site_wifi_summary", "site_ref": site_ref,
                "data": {"connectedApNum": 2, "clients": 12,
                         "channelUtilization": 34, "totalTraffic": 567.0},
                "partial": False}

    def read_site_6ghz_ap_presence(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_6ghz_ap_presence", site_ref))
        return {"status": "ok", "resource": "site_6ghz_ap_presence", "site_ref": site_ref,
                "data": {"has_6ghz_ap": True}}

    def read_site_rogue_ap_results(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_rogue_ap_results", site_ref))
        return {"status": "ok", "resource": "site_rogue_ap_results", "site_ref": site_ref,
                "count": 0, "summary": {"by_radio_id": {}, "by_channel": {},
                    "by_security_code": {}, "by_mode_code": {}, "signal_dbm": {"sample_count": 0},
                    "unknown_radio_count": 0, "unknown_security_count": 0,
                    "unknown_mode_count": 0, "unknown_row_count": 0,
                    "invalid_field_count": 0, "unknown_field_count": 0},
                "partial": False, "data_age": "unknown_stored_scan"}

    def read_site_wids_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wids_summary", site_ref))
        return {"status": "ok", "resource": "site_wids_summary", "site_ref": site_ref,
                "count": 0, "total_rows": 0,
                "summary": {"by_level_code": {}, "by_type_code": {},
                    "by_band_code": {}, "by_channel": {}, "unknown_level_count": 0,
                    "unknown_band_count": 0, "invalid_field_count": 0,
                    "unknown_field_count": 0, "unknown_row_count": 0}, "partial": False}

    def read_site_wids_blacklist_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wids_blacklist_summary", site_ref))
        return {"status": "ok", "resource": "site_wids_blacklist_summary",
                "site_ref": site_ref, "count": 0, "total_rows": 0,
                "summary": {"invalid_field_count": 0, "unknown_field_count": 0,
                            "unknown_row_count": 0}, "partial": False}

    def read_site_setting_existence(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_setting_existence", site_ref))
        return {"status": "ok", "resource": "site_setting_existence", "site_ref": site_ref,
                "data": {"settings": {key: False for key in FIELDS.values()},
                         "present_count": len(FIELDS), "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_site_session_limit_enable_state(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_session_limit_enable_state", site_ref))
        return {"status": "ok", "resource": "site_session_limit_enable_state",
                "site_ref": site_ref, "data": {"enabled": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_session_limit_rule_coverage(self, site_ref: str) -> dict[str, object]:
        from app.site_session_limit_rule_coverage import project_site_session_limit_rule_coverage

        self.calls.append(("site_session_limit_rule_coverage", site_ref))
        projected = project_site_session_limit_rule_coverage(
            self.session_limit_rule_coverage_source)
        return {"status": "ok", "resource": "site_session_limit_rule_coverage",
                **projected}

    def read_site_mac_filtering_general_state(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_mac_filtering_general_state", site_ref))
        return {"status": "ok", "resource": "site_mac_filtering_general_state",
                "site_ref": site_ref,
                "data": {"direction_present": False, "enabled": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "direction_invalid_field_count": 0,
                "direction_unknown_field_count": 0, "partial": False}

    def read_site_access_control_policy_coverage(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_access_control_policy_coverage", site_ref))
        return {"status": "ok", "resource": "site_access_control_policy_coverage",
                "source_state": "present",
                "data": {"pre_auth_access_enabled": False,
                         "free_auth_client_enabled": True},
                "flag_coverage": {},
                "policy_list_coverage": {
                    "pre_auth_access_policies": {
                        "present": True, "form_valid": True, "entry_count": 0,
                        "state": "empty"},
                    "free_auth_client_policies": {
                        "present": True, "form_valid": True, "entry_count": 2,
                        "state": "nonempty"}},
                "missing_field_count": 0, "invalid_field_count": 0,
                "over_limit_field_count": 0, "unknown_field_count": 0,
                "partial": False, "policy_contents_inspected": False}

    def read_site_device_model_whitelist_coverage(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_device_model_whitelist_coverage", site_ref))
        return {"status": "ok", "resource": "site_device_model_whitelist_coverage",
                "site_ref": site_ref, "data": {
                    "record_count": 0, "empty": True,
                    "known_fields_complete_count": 0,
                    "model_coverage": {"valid_count": 0, "missing_count": 0,
                                       "invalid_count": 0, "uninspected_record_count": 0},
                    "hardware_version_coverage": {
                        "valid_count": 0, "missing_count": 0,
                        "invalid_count": 0, "uninspected_record_count": 0},
                    "unreadable_record_count": 0, "unknown_field_count": 0,
                    "truncation_status": "not_reported_by_contract",
                }, "partial": False}

    def read_site_portal_inventory_coverage(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_portal_inventory_coverage", site_ref))
        empty_coverage = {"present_count": 0, "missing_count": 0,
                          "invalid_count": 0, "empty_count": 0,
                          "entry_count": 0, "uninspected_portal_count": 0}
        return {"status": "ok", "resource": "site_portal_inventory_coverage",
                "site_ref": site_ref, "data": {
                    "portal_count": 0, "empty": True,
                    "activation_coverage": {
                        "true_count": 0, "false_count": 0, "missing_count": 0,
                        "invalid_count": 0, "uninspected_portal_count": 0},
                    "ssid_list_coverage": dict(empty_coverage),
                    "network_list_coverage": dict(empty_coverage),
                    "unreadable_portal_count": 0,
                    "truncation_status": "not_reported_by_contract",
                }, "partial": False}

    def read_site_capabilities(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_capabilities", site_ref))
        return {"status": "ok", "resource": "site_capabilities", "site_ref": site_ref,
                "data": {"capabilities": {key: False for key in SITE_CAPABILITY_FIELDS.values()},
                         "present_count": len(SITE_CAPABILITY_FIELDS), "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_site_unresolved_incident_count(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_unresolved_incident_count", site_ref))
        return {"status": "ok", "resource": "site_unresolved_incident_count", "site_ref": site_ref,
                "data": {"unresolved_count": 2, "present": True, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_site_incident_overview(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_incident_overview", site_ref))
        return {"status": "ok", "resource": "site_incident_overview", "site_ref": site_ref,
                "window_start_ms": 100, "window_end_ms": 200,
                "data": {"counts": {"all_status": 3}, "category_counts": [],
                         "present_count": 1, "missing_count": 21,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": True}

    def read_site_incident_distribution(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_incident_distribution", site_ref))
        return {"status": "ok", "resource": "site_incident_distribution", "site_ref": site_ref,
                "window_start_ms": 100, "window_end_ms": 200,
                "data": {"points": [], "point_count": 0, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_site_incident_category_counts(self, site_ref: str, category: int) -> dict[str, object]:
        self.calls.append(("site_incident_category_counts", site_ref, category))
        return {"status": "ok", "resource": "site_incident_category_counts", "site_ref": site_ref,
                "category": category, "window_start_ms": 100, "window_end_ms": 200,
                "data": {"categories": [], "category_count": 0, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_site_incident_list(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_incident_list", site_ref))
        return {"status": "ok", "resource": "site_incident_list", "site_ref": site_ref,
                "window_start_ms": 100, "window_end_ms": 200,
                "data": {"incidents": [], "returned_count": 0, "has_more": False,
                         "missing_count": 0, "invalid_count": 0, "unknown_field_count": 0},
                "partial": False}

    def read_site_batch_interference_history(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_batch_interference_history", site_ref))
        return {"status": "ok", "resource": "site_batch_interference_history",
                "site_ref": site_ref,
                "data": {"history_count": 2, "scanning_count": 1,
                         "finished_count": 1, "has_more": False,
                         "history_refs": ["d" * 24], "partial": False}}

    def read_site_batch_interference_ap_summary(self, site_ref: str,
                                                history_ref: str) -> dict[str, object]:
        self.calls.append(("site_batch_interference_ap_summary", site_ref + ":" + history_ref))
        return {"status": "ok", "resource": "site_batch_interference_ap_summary",
                "site_ref": site_ref, "history_ref": history_ref,
                "data": {"reported_scan_ap_count": 1, "valid_device_count": 1,
                         "truncated": False}, "partial": False}

    def read_site_batch_wifi_interference_summary(self, site_ref: str,
                                                  history_ref: str) -> dict[str, object]:
        self.calls.append(("site_batch_wifi_interference_summary",
                           site_ref + ":" + history_ref))
        return {"status": "ok", "resource": "site_batch_wifi_interference_summary",
                "site_ref": site_ref, "history_ref": history_ref,
                "data": {"total_rows": 1, "returned_interference_count": 1,
                         "radio_id_counts": {"0": 1}, "has_more": False,
                         "coverage_unknown": False, "truncated": False},
                "partial": False}

    def read_site_batch_channel_load_summary(self, site_ref: str,
                                             history_ref: str,
                                             device_ref: str) -> dict[str, object]:
        self.calls.append(("site_batch_channel_load_summary",
                           site_ref + ":" + history_ref + ":" + device_ref))
        return {"status": "ok", "resource": "site_batch_channel_load_summary",
                "site_ref": site_ref, "history_ref": history_ref,
                "device_ref": device_ref, "data": {"bands": {"2g": {
                    "returned_channel_count": 1, "minimum_load": 10,
                    "maximum_load": 10, "average_load": 10.0}}}, "partial": False}

    def read_site_batch_interference_result_summary(self, site_ref: str,
                                                    history_ref: str) -> dict[str, object]:
        self.calls.append(("site_batch_interference_result_summary", site_ref + ":" + history_ref))
        return {"status": "ok", "resource": "site_batch_interference_result_summary",
                "site_ref": site_ref, "history_ref": history_ref,
                "data": {"band_entry_counts": {"2g": 1, "5g": 0, "6g": 0},
                         "coverage_unknown": True}, "partial": True}

    def read_site_batch_interference_status_summary(self, site_ref: str,
                                                    history_ref: str) -> dict[str, object]:
        self.calls.append(("site_batch_interference_status_summary", site_ref + ":" + history_ref))
        return {"status": "ok", "resource": "site_batch_interference_status_summary",
                "site_ref": site_ref, "history_ref": history_ref,
                "data": {"result_count": 1, "items": [{"status": "finished"}]},
                "partial": False}

    def read_ap_full_channel_detect_status(self, site_ref: str,
                                           device_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_full_channel_detect_status", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "site_ap_full_channel_detect_status",
                "site_ref": site_ref, "device_ref": device_ref,
                "data": {"statuses": {"full_channel_detection": "scanning"}},
                "partial": False}

    def read_device_health_incidents(self, site_ref: str, device_ref: str) -> dict[str, object]:
        self.calls.append(("device_health_incidents", site_ref + ":" + device_ref))
        return {"status": "ok", "resource": "device_health_incidents",
                "site_ref": site_ref, "count": 1,
                "items": [{"incident_ref": "c" * 24, "anomaly_code": "A1"}]}

    def read_client_health_incidents(self, site_ref: str, client_ref: str) -> dict[str, object]:
        self.calls.append(("client_health_incidents", site_ref + ":" + client_ref))
        return {"status": "ok", "resource": "client_health_incidents",
                "site_ref": site_ref, "count": 1,
                "items": [{"incident_ref": "c" * 24, "anomaly_code": "A1"}]}

    def read_site_incident_detail(self, site_ref: str, incident_ref: str) -> dict[str, object]:
        self.calls.append(("site_incident_detail", site_ref + ":" + incident_ref))
        return {"status": "ok", "resource": "site_incident_detail",
                "site_ref": site_ref, "incident_ref": incident_ref,
                "data": {"anomaly_code": "A1"}, "partial": True}

    def read_site_incident_notification(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_incident_notification", site_ref))
        return {"status": "ok", "resource": "site_incident_notification",
                "site_ref": site_ref, "data": {"recipient_count": 2}}

    def read_site_anomaly_event_settings(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_anomaly_event_settings", site_ref))
        return {"status": "ok", "resource": "site_anomaly_event_settings",
                "site_ref": site_ref, "data": {"returned_count": 1}}

    def read_site_incident_influencing_clients(self, site_ref: str,
                                               incident_ref: str) -> dict[str, object]:
        self.calls.append(("site_incident_influencing_clients", site_ref + ":" + incident_ref))
        return {"status": "ok", "resource": "site_incident_influencing_clients",
                "site_ref": site_ref, "incident_ref": incident_ref, "data": {"items": []}}

    def read_site_incident_influencing_devices(self, site_ref: str,
                                               incident_ref: str) -> dict[str, object]:
        self.calls.append(("site_incident_influencing_devices", site_ref + ":" + incident_ref))
        return {"status": "ok", "resource": "site_incident_influencing_devices",
                "site_ref": site_ref, "incident_ref": incident_ref, "data": {"items": []}}

    def read_site_wlan_group_capacity(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wlan_group_capacity", site_ref))
        return {"status": "ok", "resource": "site_wlan_group_capacity",
                "site_ref": site_ref, "data": {"group_count": 2}}

    def read_site_ap_group_capacity(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_group_capacity", site_ref))
        return {"status": "ok", "resource": "site_ap_group_capacity",
                "site_ref": site_ref, "data": {"group_count": 2}}

    def read_site_ap_group_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_group_summary", site_ref))
        return {"status": "ok", "resource": "site_ap_group_summary",
                "total_groups": 2, "primary_groups": 1, "non_primary_groups": 1,
                "ap_count_total": 3, "partial": False}

    def read_site_ap_group_assignment_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_group_assignment_summary", site_ref))
        return {"status": "ok", "resource": "site_ap_group_assignment_summary",
                "ap_rows": 2, "with_reported_group_assignment": 1,
                "without_reported_group_assignment": 1}

    def read_site_ap_group_info_summary(
            self, site_ref: str, group_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_group_info_summary", site_ref, group_ref))
        return {"status": "ok", "resource": "site_ap_group_info_summary",
                "site_ref": site_ref, "group_ref": group_ref, "primary": True,
                "ap_count": 2}

    def read_site_ap_oui_vlan_rules_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_oui_vlan_rules_summary", site_ref))
        return {"status": "ok", "resource": "site_ap_oui_vlan_rules_summary",
                "total_rules": 1, "enabled_rules": 1, "vlan_assignment_count": 2,
                "partial": False}

    def read_site_oui_profile_list_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_oui_profile_list_summary", site_ref))
        return {"status": "ok", "resource": "site_oui_profile_list_summary",
                "profile_count": 1, "omitted_profile_count": 2, "partial": True}

    def read_site_group_profiles_coverage(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_group_profiles_coverage", site_ref))
        return {"status": "ok", "resource": "site_group_profiles_coverage",
                "source_state": "empty", "row_count": 0, "partial": False}

    def read_site_vlan_ssid_usage_summary(self, site_ref: str, network_ref: str,
                                          vlan_id: int) -> dict[str, object]:
        self.calls.append(("site_vlan_ssid_usage_summary", site_ref, network_ref, vlan_id))
        return {"status": "ok", "resource": "site_vlan_ssid_usage_summary",
                "ssid_count": 2, "wlan_group_count": 1, "partial": False}

    def read_site_vlan_device_usage_summary(self, site_ref: str, network_ref: str,
                                            vlan_id: int) -> dict[str, object]:
        self.calls.append(("site_vlan_device_usage_summary", site_ref, network_ref, vlan_id))
        return {"status": "ok", "resource": "site_vlan_device_usage_summary",
                "device_count": 3, "partial": False}

    def read_site_vlan_port_support_summary(self, site_ref: str, network_ref: str,
                                            vlan_id: int) -> dict[str, object]:
        self.calls.append(("site_vlan_port_support_summary", site_ref, network_ref, vlan_id))
        return {"status": "ok", "resource": "site_vlan_port_support_summary",
                "supported_port_count": 2, "unsupported_port_count": 1, "partial": False}

    def read_site_vlan_affected_ports_summary(self, site_ref: str, network_ref: str,
                                              vlan_id: int, page_number: int,
                                              page_size: int) -> dict[str, object]:
        self.calls.append(("site_vlan_affected_ports_summary", site_ref, network_ref,
                           vlan_id, page_number, page_size))
        return {"status": "ok", "resource": "site_vlan_affected_ports_summary",
                "reported_affected_device_count": 3, "sampled_device_count": 2,
                "partial": True}

    def read_site_wifi_calling_profiles_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wifi_calling_profiles_summary", site_ref))
        return {"status": "ok", "resource": "site_wifi_calling_profiles_summary",
                "profile_count": 2, "carrier_count": 1, "partial": False}

    def read_site_wifi_calling_top_ssid_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wifi_calling_top_ssid_summary", site_ref))
        return {"status": "ok", "resource": "site_wifi_calling_top_ssid_summary",
                "top_ssid_source_state": "present", "top_ssid_row_count": 1,
                "documented_field_observed_count": 19, "partial": False}

    def read_site_client_filter_options_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_filter_options_summary", site_ref))
        return {"status": "ok", "resource": "site_client_filter_options_summary",
                "vendors": 2, "ssids": 1, "partial": False}

    def read_site_eap_dot1x_candidates_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_eap_dot1x_candidates_summary", site_ref))
        return {"status": "ok", "resource": "site_eap_dot1x_candidates_summary",
                "site_ref": site_ref, "returned_device_count": 1, "partial": False}

    def read_site_switch_dot1x_candidates_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_dot1x_candidates_summary", site_ref))
        return {"status": "ok", "resource": "site_switch_dot1x_candidates_summary",
                "site_ref": site_ref, "returned_switch_count": 1, "partial": False}

    def read_site_switch_support(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_support", site_ref))
        return {"status": "ok", "resource": "site_switch_support", "site_ref": site_ref,
                "data": {"switch_support": {key: False for key in SITE_SWITCH_SUPPORT_FIELDS.values()},
                         "present_count": len(SITE_SWITCH_SUPPORT_FIELDS), "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_experience_index(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("experience_index", site_ref))
        return {"status": "ok", "resource": "experience_index", "site_ref": site_ref,
                "data": {"last_scan": []}}

    def read_rf_planning_result(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_planning_result", site_ref))
        return {"status": "ok", "resource": "rf_planning_result", "site_ref": site_ref,
                "data": {"status": 1}}

    def read_rf_planning_dashboard(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_planning_dashboard", site_ref))
        return {"status": "ok", "resource": "rf_planning_dashboard", "site_ref": site_ref,
                "data": {"bands": {}}}

    def read_rf_planning_dashboard_current(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_planning_dashboard_current", site_ref))
        return {"status": "ok", "resource": "rf_planning_dashboard_current",
                "site_ref": site_ref, "data": {"bands": {}}, "partial": False}

    def read_rf_planning_dashboard_history(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_planning_dashboard_history", site_ref))
        return {"status": "ok", "resource": "rf_planning_dashboard_history",
                "site_ref": site_ref, "data": {"bands": {}}, "partial": False}

    def read_rf_planning_detail(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_planning_detail", site_ref))
        return {"status": "ok", "resource": "rf_planning_detail", "site_ref": site_ref,
                "data": {"aps": [], "ap_count": 0}}

    def read_rf_planning_history(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_planning_history", site_ref))
        return {"status": "ok", "resource": "rf_planning_history", "site_ref": site_ref,
                "data": {"items": [], "count": 0}, "truncated": False}

    def read_rf_planning_history_detail(self, site_ref: str, history_ref: str) -> dict[str, object]:
        self.calls.append(("rf_planning_history_detail", site_ref + ":" + history_ref))
        return {"status": "ok", "resource": "rf_planning_history_detail",
                "site_ref": site_ref, "history_ref": history_ref,
                "data": {"aps": [], "ap_count": 0}, "partial": False}

    def read_rf_planning_recent_history(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_planning_recent_history", site_ref))
        return {"status": "ok", "resource": "rf_planning_recent_history",
                "site_ref": site_ref, "data": {"items": [], "count": 0},
                "truncated": False}

    def read_rf_excluded_aps(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_excluded_aps", site_ref))
        return {"status": "ok", "resource": "rf_excluded_aps", "site_ref": site_ref,
                "count": 0, "items": [], "partial": False}

    def read_rf_deploy_history(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("rf_deploy_history", site_ref))
        return {"status": "ok", "resource": "rf_deploy_history", "site_ref": site_ref,
                "data": {"first_deployment": True}, "partial": False}

    def read_wifi_health(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("wifi_health", site_ref))
        return self.diagnostic_payloads[FIXED_DIAGNOSTIC_ROUTES[0]]

    def read_wifi_subhealth(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("wifi_subhealth", site_ref))
        return self.diagnostic_payloads[FIXED_DIAGNOSTIC_ROUTES[1]]

    def read_site_dashboard_channels(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("wifi_channels", site_ref))
        return self.diagnostic_payloads[FIXED_DIAGNOSTIC_ROUTES[2]]

    def read_site_client_signal_distribution(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("client_signal_distribution", site_ref))
        return self.diagnostic_payloads[FIXED_DIAGNOSTIC_ROUTES[3]]

    def list_devices(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("devices", site_ref))
        return {"status": "ok", "resource": "devices", "count": 1,
                "items": [_device()]}

    def read_switch_health(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_health", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_health", "site_ref": site_ref,
                "switch_ref": switch_ref, "data": {"dimensions": {}}, "partial": False}

    def read_switch_health_timeline(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_health_timeline", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_health_timeline",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "data": {"scores": []}, "partial": False}

    def read_switch_sdm_usage(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_sdm_usage", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_sdm_usage",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "data": {"category": 0, "num": 24}, "partial": False}

    def read_switch_cable_test_logs(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_cable_test_logs", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_cable_test_logs",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "count": 0, "data": {"logs": []}, "partial": False}

    def read_switch_cable_test_full_results(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_cable_test_full_results", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_cable_test_full_results",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "data": {"status_code": 0, "ports": []}, "partial": False}

    def read_switch_cable_test_increment_results(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_cable_test_increment_results", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_cable_test_increment_results",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "data": {"status_code": 0, "ports": []}, "partial": False}

    def read_switch_cable_test_ports(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_cable_test_ports", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_cable_test_ports",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "count": 0, "data": {"ports": []}, "partial": False}

    def list_switch_dhcp_users(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_dhcp_users", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_dhcp_users",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "count": 0, "items": [], "summary": {"total": 0}, "partial": False}

    def list_switch_ospf_neighbors(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_ospf_neighbors", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_ospf_neighbors",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "count": 0, "summary": {"by_state": {}, "unknown_state_rows": 0},
                "partial": False}

    def list_switch_port_networks(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_port_networks", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_port_networks",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "count": 0, "summary": {"vlans": [], "unknown_vlan_rows": 0},
                "partial": False}

    def list_switch_exist_networks(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_exist_networks", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_exist_networks",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "count": 0, "summary": {"by_vlan": {}, "by_vlan_type": {}},
                "partial": False}

    def list_switch_networks(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_networks", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_networks",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "count": 0, "summary": {"by_vlan": {}, "by_status_code": {},
                                          "by_dhcp_mode_code": {}, "unknown_rows": 0},
                "partial": False}

    def list_switch_interfaces(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_interfaces", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_interfaces",
                "site_ref": site_ref, "switch_ref": switch_ref, "count": 0,
                "summary": {"by_type_code": {}, "unknown_rows": 0}, "partial": False}

    def list_switch_routing_table(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_routing_table", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_routing_table",
                "site_ref": site_ref, "switch_ref": switch_ref, "count": 0,
                "summary": {"by_type": {}, "by_distance": {}, "by_metric": {},
                            "unknown_rows": 0}, "partial": False}

    def list_switch_static_routes(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_static_routes", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_static_routes",
                "site_ref": site_ref, "switch_ref": switch_ref, "count": 0,
                "summary": {"by_status": {}, "by_ip_version": {}, "by_distance": {},
                            "by_resource_code": {}, "by_destination_count": {},
                            "support_ipv6_static_routing": None, "unknown_rows": 0},
                "partial": False}

    def list_switch_vrfs(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_vrfs", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_vrfs", "site_ref": site_ref,
                "switch_ref": switch_ref, "count": 0,
                "summary": {"by_ipv4_enabled": {}, "by_ipv6_enabled": {},
                            "default_count": 0, "by_resource_code": {}, "unknown_rows": 0},
                "partial": False}

    def list_switch_vlan_interfaces(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_vlan_interfaces", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_vlan_interfaces", "site_ref": site_ref,
                "switch_ref": switch_ref, "count": 0,
                "summary": {"unique_vlan_count": 0, "unknown_rows": 0}, "partial": False}

    def read_switch_statistics(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_statistics", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_statistics",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "data": {"port_count": 0, "by_link_status_code": {},
                         "unknown_port_rows": 0}, "partial": False}

    def list_switch_port_tags(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("switch_port_tags", site_ref))
        return {"status": "ok", "resource": "switch_port_tags", "site_ref": site_ref,
                "count": 2, "summary": {"by_resource_code": {0: 1, 1: 1},
                                          "unknown_rows": 0}, "partial": False}

    def read_switch_ports(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_ports", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_ports", "site_ref": site_ref,
                "device_ref": switch_ref, "count": 1, "items": [{"port": 1}]}

    def read_switch_port_counters(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_port_counters", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_port_counters", "site_ref": site_ref,
                "switch_ref": switch_ref, "data": {"ports": []}}

    def read_switch_port_poe_info(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_port_poe_info", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_port_poe_info", "site_ref": site_ref,
                "switch_ref": switch_ref, "data": {"ports": []}}

    def read_switch_vlans(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_vlans", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_vlans", "site_ref": site_ref,
                "switch_ref": switch_ref, "count": 0, "items": []}

    def read_switch_lldp_neighbors(self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("switch_lldp_neighbors", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "switch_lldp_neighbors", "site_ref": site_ref,
                "switch_ref": switch_ref, "data": {"neighbor_count": 0}}

    def read_ap_health(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_health", site_ref + ":" + ap_ref))
        return _ap_health_payload(site_ref, ap_ref)

    def read_ap_channel_load_summary(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_channel_load_summary", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_channel_load_summary", "device_ref": ap_ref,
                "data": {"bands": {"2g": {"returned_channel_count": 2,
                    "minimum_load": 20, "maximum_load": 80, "average_load": 50.0},
                    "5g": {"returned_channel_count": 0, "minimum_load": None,
                    "maximum_load": None, "average_load": None},
                    "6g": {"returned_channel_count": 0, "minimum_load": None,
                    "maximum_load": None, "average_load": None}},
                    "returned_result_count": 1, "omitted_value_count": 0,
                    "unknown_field_count": 0}, "partial": False}

    def read_ap_interference_result_summary(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_interference_result_summary", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_interference_result_summary", "device_ref": ap_ref,
                "data": {"band_entry_counts": {"2g": 4, "5g": 2, "6g": 0},
                    "returned_result_count": 1, "visited_object_count": 7,
                    "omitted_value_count": 0, "unknown_field_count": 0, "page": 1,
                    "page_size": 100, "coverage_scope": "first_page_only",
                    "coverage_unknown": True}, "partial": True}

    def read_ap_available_channels_summary(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_available_channels_summary", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_available_channels_summary", "device_ref": ap_ref,
                "data": {"radios": [{"band": "2_4ghz", "radio_id": 0,
                    "channels": [[1, 2412, 1, [20, 40]], [2, 2437, 2, [20]]],
                    "omitted_channel_count": 0}], "omitted_value_count": 0,
                    "unknown_radio_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_ap_available_channels(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_available_channels", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_available_channels", "device_ref": ap_ref,
                "data": {"radios": [{"radio_id": 0, "band": "2.4GHz", "channels": [
                    {"channel_index": 1, "channel": 1, "frequency_mhz": 2412,
                     "available_widths_mhz": [20, 40]}]}]}}

    def read_ap_health_timeline(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_health_timeline", site_ref + ":" + ap_ref))
        return _ap_timeline_payload(site_ref, ap_ref)

    def read_ap_radio_config(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_radio_config", site_ref + ":" + ap_ref))
        return {**_ap_radio_config_payload(), "site_ref": site_ref, "device_ref": ap_ref}

    def read_ap_radio_part(self, site_ref: str, ap_ref: str,
                           part: str) -> dict[str, object]:
        self.calls.append((part, site_ref + ":" + ap_ref))
        if part == "radio_config":
            return _ap_radio_config_payload()
        return {"status": "ok", "resource": part, "device_ref": ap_ref, "data": {}}

    def read_ap_wifi_neighbors(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_wifi_neighbors", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_wifi_neighbors", "device_ref": ap_ref,
                "count": 0, "items": []}

    def read_ap_speed_test_results(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_speed_test_results", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_speed_test_results",
                "site_ref": site_ref, "device_ref": ap_ref,
                "data": {"main_testing": False, "results": [],
                         "source_ap_ref": ap_ref, "target_ap_ref": "c" * 24},
                "partial": False}

    def read_ap_ssid_override_audit_summary(self, site_ref: str,
                                            ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_ssid_override_audit_summary", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_ssid_override_audit_summary",
                "site_ref": site_ref, "device_ref": ap_ref,
                "data": {"reported_total_row_count": 2, "returned_row_count": 2,
                         "password_modified_count": 1, "ssid_name_modified_count": 1,
                         "vlan_id_modified_count": 1}, "partial": False}

    def read_ap_wired_downlink(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_wired_downlink", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_wired_downlink", "site_ref": site_ref,
                "device_ref": ap_ref, "count": 0, "source_count": 0, "items": [],
                "partial": False, "omitted_count": 0, "unknown_field_count": 0,
                "redacted_field_count": 0}

    def list_ap_ports(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_ports", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_ports", "site_ref": site_ref,
                "device_ref": ap_ref, "count": 0,
                "summary": {"by_link_status_code": {}, "by_link_speed_code": {},
                            "by_port_type_code": {}, "duplex_code_counts": {},
                            "poe_supported_ports": 0, "poe_output_enabled_ports": 0,
                            "uplink_ports": 0, "logical_uplink_ports": 0,
                            "vlan_supported_ports": 0, "local_vlan_enabled_ports": 0,
                            "poe_state_code_counts": {}, "poe_input_mode_code_counts": {},
                            "unknown_row_count": 0, "invalid_field_count": 0,
                            "unknown_field_count": 0}, "partial": False}

    def read_controller_radius_server(self) -> dict[str, object]:
        self.calls.append(("controller_radius_server", None))
        return {"status": "ok", "resource": "controller_radius_server",
                "data": {"settings": {"enabled": True, "auth_server_port": 1812},
                         "redacted_presence": {"secret": True,
                                               "certificate_configured": True},
                         "present_count": 4, "missing_required_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_site_radius_user_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_radius_user_summary", site_ref))
        return {"status": "ok", "resource": "site_radius_user_summary",
                "site_ref": site_ref, "data": {"user_count": 2,
                "user_type_code_counts": {"1": 2}, "username_present": 2,
                "password_present": 2, "vlan_id_field_present": 1,
                "session_timeout_field_present": 2, "upload_rate_limit_field_present": 0,
                "download_rate_limit_field_present": 0, "upload_traffic_limit_field_present": 0,
                "download_traffic_limit_field_present": 0, "invalid_field_count": 0,
                "unknown_field_count": 0}, "partial": False}

    def read_site_entity_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_entity_summary", site_ref))
        return {"status": "ok", "resource": "site_entity_summary",
                "site_ref": site_ref, "data": {"site_tier": "basic",
                "ntp_enabled": True, "ntp_server_count": 2,
                "timezone_configured": True, "dst_enabled": False,
                "location_configured": True, "supports_agile_switches": True,
                "supports_non_agile_switches": False}, "partial": False}

    def read_site_switch_qos_mode(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_qos_mode", site_ref))
        return {"status": "ok", "resource": "site_switch_qos_mode",
                "site_ref": site_ref,
                "data": {"mode": "rules_based", "transition_completed": True},
                "partial": False}

    def read_site_switch_qos_scheduler_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_qos_scheduler_summary", site_ref))
        return {"status": "ok", "resource": "site_switch_qos_scheduler_summary",
                "site_ref": site_ref, "data": {"mapping_count": 2}, "partial": False}

    def read_site_switch_qos_dscp_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_qos_dscp_summary", site_ref))
        return {"status": "ok", "resource": "site_switch_qos_dscp_summary",
                "site_ref": site_ref, "data": {"queue_count": 2}, "partial": False}

    def read_site_iptv_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_iptv_summary", site_ref))
        return {"status": "ok", "resource": "site_iptv_summary", "site_ref": site_ref,
                "data": {"enabled": True, "mode": "custom", "wan_port_configured": True,
                         "custom_vlan_configured": True, "dsl_configured": False,
                         "port_type_counts": {"internet": 1, "iptv": 1, "ip_phone": 0},
                         "port_count": 2, "feature_description_count": None}, "partial": False}

    def list_site_templates(self) -> dict[str, object]:
        self.calls.append(("site_templates", None))
        return {"status": "ok", "resource": "site_templates", "count": 1,
                "items": [{"site_template_ref": "b" * 24, "template_type": "basic",
                           "bound_site_count": 1, "settings_count": 2}],
                "partial": False}

    def read_site_template_upnp_summary(self, site_template_ref: str) -> dict[str, object]:
        self.calls.append(("site_template_upnp_summary", site_template_ref))
        return {"status": "ok", "resource": "site_template_upnp_summary",
                "site_template_ref": site_template_ref,
                "data": {"enabled": True, "wan_port_count": 1, "network_count": 2,
                         "supports_ds_lite_or_map_e": False}, "partial": False}

    def read_site_template_igmp_summary(self, site_template_ref: str) -> dict[str, object]:
        self.calls.append(("site_template_igmp_summary", site_template_ref))
        return {"status": "ok", "resource": "site_template_igmp_summary",
                "site_template_ref": site_template_ref,
                "data": {"enabled": True, "version": 2, "wan_port_configured": True},
                "partial": False}

    def read_site_template_ssh_summary(self, site_template_ref: str) -> dict[str, object]:
        self.calls.append(("site_template_ssh_summary", site_template_ref))
        return {"status": "ok", "resource": "site_template_ssh_summary",
                "site_template_ref": site_template_ref,
                "data": {"enabled": True, "layer3_access_enabled": False,
                         "server_port": 22}, "partial": False}

    def read_site_template_iptv_summary(self, site_template_ref: str) -> dict[str, object]:
        self.calls.append(("site_template_iptv_summary", site_template_ref))
        return {"status": "ok", "resource": "site_template_iptv_summary",
                "site_template_ref": site_template_ref,
                "data": {"enabled": True, "mode": "bridge", "wan_port_configured": True,
                         "custom_vlan_configured": False, "dsl_configured": False,
                         "feature_description_count": 0,
                         "port_type_counts": {"internet": 1, "iptv": 0, "ip_phone": 0},
                         "port_count": 1}, "partial": False}

    def read_site_template_iptv_settings_summary(self, site_template_ref: str) -> dict[str, object]:
        self.calls.append(("site_template_iptv_settings_summary", site_template_ref))
        return {"status": "ok", "resource": "site_template_iptv_settings_summary",
                "site_template_ref": site_template_ref,
                "data": {"igmp": {"enabled": True, "version": 2,
                                   "wan_port_configured": True},
                         "iptv": {"enabled": True, "mode": "bridge",
                                  "wan_port_configured": True,
                                  "port_count": 1},
                         "igmp_settings_present": True,
                         "iptv_settings_present": True}, "partial": False}

    def read_site_igmp_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_igmp_summary", site_ref))
        return {"status": "ok", "resource": "site_igmp_summary", "site_ref": site_ref,
                "data": {"enabled": True, "version": 3, "wan_port_configured": True,
                         "virtual_wan_configured": False,
                         "feature_description_count": None}, "partial": False}

    def read_site_mld_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_mld_summary", site_ref))
        return {"status": "ok", "resource": "site_mld_summary", "site_ref": site_ref,
                "data": {"enabled": True, "version": 2, "wan_port_configured": True,
                         "feature_description_count": None}, "partial": False}

    def read_site_ssh_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ssh_summary", site_ref))
        return {"status": "ok", "resource": "site_ssh_summary", "site_ref": site_ref,
                "data": {"enabled": True, "layer3_access_enabled": False,
                         "server_port": 22}, "partial": False}

    def read_site_ssl_vpn_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ssl_vpn_summary", site_ref))
        return {"status": "ok", "resource": "site_ssl_vpn_summary", "site_ref": site_ref,
                "data": {"enabled": True, "service_port": 443,
                         "authentication_mode": "local", "idle_disconnect_enabled": False,
                         "idle_disconnect_seconds": None, "all_traffic_through_vpn": True,
                         "radius_supported": True, "radius_configured": False,
                         "ldap_supported": False, "ldap_configured": False,
                         "supported_on_ds_lite_or_map_e": True,
                         "radius_config_details_present": None, "ldap_config_details_present": None,
                         "name_lock_enabled": True, "ip_lock_enabled": False}, "partial": False}

    def read_site_gre_tunnel_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_gre_tunnel_summary", site_ref))
        return {"status": "ok", "resource": "site_gre_tunnel_summary", "site_ref": site_ref,
                "data": {"enabled": True, "tunnel_mtu": 1400,
                         "keepalive_interval_seconds": 30, "keepalive_miss_limit": 5,
                         "primary_endpoint_configured": True,
                         "secondary_endpoint_configured": False}, "partial": False}

    def read_site_upnp_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_upnp_summary", site_ref))
        return {"status": "ok", "resource": "site_upnp_summary", "site_ref": site_ref,
                "data": {"enabled": True, "wan_port_count": 1, "network_count": 2,
                         "supports_ds_lite_or_map_e": False}, "partial": False}

    def read_site_iot_aging_time(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_iot_aging_time", site_ref))
        return {"status": "ok", "resource": "site_iot_aging_time", "site_ref": site_ref,
                "data": {"aging_value": 3600, "unit": "seconds"}, "partial": False}

    def read_site_iot_radio_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_iot_radio_summary", site_ref))
        return {"status": "ok", "resource": "site_iot_radio_summary", "site_ref": site_ref,
                "data": {"bluetooth_enabled": True, "passcode_configured": True},
                "partial": False}

    def read_site_mesh_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_mesh_summary", site_ref))
        return {"status": "ok", "resource": "site_mesh_summary", "site_ref": site_ref,
                "data": {"mesh_enabled": True, "custom_gateway_configured": True},
                "partial": False}

    def read_site_multicast_rate_limit_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_multicast_rate_limit_summary", site_ref))
        return {"status": "ok", "resource": "site_multicast_rate_limit_summary",
                "site_ref": site_ref,
                "data": {"enabled": True, "igmp_enabled": True,
                         "igmp_packets_per_second": 120}, "partial": False}

    def read_site_beacon_control_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_beacon_control_summary", site_ref))
        return {"status": "ok", "resource": "site_beacon_control_summary",
                "site_ref": site_ref,
                "data": {"beacon_interval_2g": 100,
                         "airtime_fairness_enabled_2g": True}, "partial": False}

    def read_site_iot_transmit_power_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_iot_transmit_power_summary", site_ref))
        return {"status": "ok", "resource": "site_iot_transmit_power_summary",
                "site_ref": site_ref,
                "data": {"observed_row_count": 2,
                         "transmit_power_device_counts_dbm": {"5": 2}}, "partial": False}

    def read_site_bluetooth_advertising_v2_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_bluetooth_advertising_v2_summary", site_ref))
        return {"status": "ok", "resource": "site_bluetooth_advertising_v2_summary",
                "site_ref": site_ref, "data": {"observed_row_count": 1}, "partial": False}

    def read_site_remember_setting_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_remember_setting_summary", site_ref))
        return {"status": "ok", "resource": "site_remember_setting_summary",
                "site_ref": site_ref,
                "data": {"remember_enabled": True}, "partial": False}

    def read_site_client_connection_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_connection_summary", site_ref))
        return {"status": "ok", "resource": "site_client_connection_summary",
                "site_ref": site_ref,
                "data": {"total_client_count": 42, "wired_client_count": 8,
                         "wireless_client_count": 34}, "partial": False}

    def read_site_poe_usage_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_poe_usage_summary", site_ref))
        return {"status": "ok", "resource": "site_poe_usage_summary",
                "site_ref": site_ref,
                "data": {"switch_count": 2, "reported_port_count": 32,
                         "total_power_used_watts": 92,
                         "rated_poe_capacity_watts": 490}, "partial": False}

    def read_site_poe_schedule_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_poe_schedule_summary", site_ref))
        return {"status": "ok", "resource": "site_poe_schedule_summary",
                "site_ref": site_ref,
                "source_contract": "detailed_feed_fields_documented_in_all_three_exports; descriptions_and_numeric_wrappers_vary",
                "data": {"switches": []}, "partial": False}

    def read_site_port_schedule_summary(self, site_ref: str, page_number: int,
                                        page_size: int) -> dict[str, object]:
        self.calls.append(("site_port_schedule_summary", site_ref, page_number, page_size))
        return {"status": "ok", "resource": "site_port_schedule_summary",
                "reported_schedule_count": 2, "sampled_schedule_count": 1,
                "partial": True}

    def read_site_routing_table_summary(self, site_ref: str, device_type: str,
                                        page_number: int, page_size: int) -> dict[str, object]:
        self.calls.append(("site_routing_table_summary", site_ref, device_type,
                           page_number, page_size))
        return {"status": "ok", "resource": "site_routing_table_summary",
                "device_type": device_type, "reported_route_count": 5,
                "sampled_route_count": 3, "partial": True}

    def read_site_device_counts_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_device_counts_summary", site_ref))
        return {"status": "ok", "resource": "site_device_counts_summary",
                "site_ref": site_ref,
                "data": {"device_category_count": 2, "total_device_count": 15,
                         "connected_device_count": 13}, "partial": False}

    def read_site_ipsec_tunnel_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ipsec_tunnel_summary", site_ref))
        return {"status": "ok", "resource": "site_ipsec_tunnel_summary",
                "site_ref": site_ref,
                "data": {"tunnel_count": 2, "enabled_tunnel_count": 1,
                         "disabled_tunnel_count": 1}, "partial": False}

    def read_site_client_association_time_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_association_time_summary", site_ref))
        return {"status": "ok", "resource": "site_client_association_time_summary",
                "site_ref": site_ref, "window_start_seconds": 1_999_913_600,
                "window_end_seconds": 2_000_000_000,
                "data": {"under_2_seconds_count": 5,
                         "failed_association_count": 1}, "partial": False}

    def read_site_network_activity_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_network_activity_summary", site_ref))
        return {"status": "ok", "resource": "site_network_activity_summary",
                "site_ref": site_ref, "data": {"total_traffic": 2000,
                "total_client_count": 3}, "partial": False}

    def read_site_client_rssi_distribution_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_rssi_distribution_summary", site_ref))
        return {"status": "ok", "resource": "site_client_rssi_distribution_summary",
                "site_ref": site_ref, "data": {"band_5_ghz": {"less_than_72": 2}},
                "partial": False}

    def read_site_ap_rssi_density_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_rssi_density_summary", site_ref))
        return {"status": "ok", "resource": "site_ap_rssi_density_summary",
                "site_ref": site_ref, "data": {"ap_count_in_buckets": 7},
                "partial": False}

    def read_site_client_attachment_distribution_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_attachment_distribution_summary", site_ref))
        return {"status": "ok", "resource": "site_client_attachment_distribution_summary",
                "site_ref": site_ref,
                "data": {"access_point_attached_client_count": 8,
                         "switch_attached_client_count": 3}, "partial": False}

    def read_site_client_frequency_distribution_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_frequency_distribution_summary", site_ref))
        return {"status": "ok", "resource": "site_client_frequency_distribution_summary",
                "site_ref": site_ref, "data": {"total_client_count": 18,
                "wired_client_count": 6, "wireless_client_count": 12}, "partial": False}

    def read_site_device_traffic_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_device_traffic_summary", site_ref))
        return {"status": "ok", "resource": "site_device_traffic_summary",
                "site_ref": site_ref, "window_start_seconds": 1_999_913_600,
                "window_end_seconds": 2_000_000_000,
                "data": {"ap_traffic_mb": 50.0, "switch_traffic_mb": 2.0},
                "partial": False}

    def read_site_past_client_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_past_client_summary", site_ref))
        return {"status": "ok", "resource": "site_past_client_summary",
                "site_ref": site_ref, "window_start_seconds": 1_999_913_600,
                "window_end_seconds": 2_000_000_000,
                "data": {"total_client_count": 32, "wired_client_count": 9,
                         "wireless_client_count": 23}, "partial": False}

    def read_site_current_client_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_current_client_summary", site_ref))
        return {"status": "ok", "resource": "site_current_client_summary",
                "site_ref": site_ref, "data": {"total_client_count": 21,
                "wired_client_count": 8, "wireless_client_count": 13}, "partial": False}

    def read_site_gateway_isp_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_gateway_isp_summary", site_ref))
        return {"status": "ok", "resource": "site_gateway_isp_summary",
                "site_ref": site_ref, "data": {"gateway_count": 1,
                "online_isp_count": 1, "maximum_download_utilization_percent": 81.25},
                "partial": False}

    def read_site_top_ap_retry_drop_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_top_ap_retry_drop_summary", site_ref))
        return {"status": "ok", "resource": "site_top_ap_retry_drop_summary",
                "site_ref": site_ref, "data": {"top_ap_by_rt_count": 2,
                "maximum_ap_by_rt_ratio_percent": 27}, "partial": False}

    def read_site_active_ap_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_active_ap_summary", site_ref))
        return {"status": "ok", "resource": "site_active_ap_summary",
                "site_ref": site_ref, "data": {"device_count": 2,
                "total_traffic_value": 3.5}, "partial": False}

    def read_site_active_ap_v2_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_active_ap_v2_summary", site_ref))
        return {"status": "ok", "resource": "site_active_ap_v2_summary",
                "site_ref": site_ref, "data": {"requested_device_count": 10,
                "active_ap_count": 2, "reported_total_traffic_value": 75},
                "partial": False}

    def read_site_hotspot_statistics_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_hotspot_statistics_summary", site_ref))
        return {"status": "ok", "resource": "site_hotspot_statistics_summary",
                "site_ref": site_ref, "data": {"last_connection_sample_count": 24,
                "total_new_authenticated_clients": 8}, "partial": False}

    def read_site_allowed_application_summary(self, site_ref: str, page_number: int,
                                              page_size: int) -> dict[str, object]:
        self.calls.append(("site_allowed_application_summary", site_ref,
                           page_number, page_size))
        return {"status": "ok", "resource": "site_allowed_application_summary",
                "site_ref": site_ref, "page_number": page_number,
                "page_size": page_size, "data": {"returned_application_count": 2},
                "partial": False}

    def read_site_blocked_application_summary(self, site_ref: str, page_number: int,
                                              page_size: int) -> dict[str, object]:
        self.calls.append(("site_blocked_application_summary", site_ref,
                           page_number, page_size))
        return {"status": "ok", "resource": "site_blocked_application_summary",
                "site_ref": site_ref, "page_number": page_number,
                "page_size": page_size, "data": {"returned_application_count": 1},
                "partial": False}

    def read_site_dashboard_all_tabs_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_dashboard_all_tabs_summary", site_ref))
        return {"status": "ok", "resource": "site_dashboard_all_tabs_summary",
                "site_ref": site_ref, "data": {"tab_count": 3}, "partial": False}

    def read_site_dashboard_non_overall_tabs_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_dashboard_non_overall_tabs_summary", site_ref))
        return {"status": "ok", "resource": "site_dashboard_non_overall_tabs_summary",
                "site_ref": site_ref, "data": {"tab_count": 2}, "partial": False}

    def read_site_specific_app_traffic_summary(self, site_ref: str,
                                               application_id: str) -> dict[str, object]:
        self.calls.append(("site_specific_app_traffic_summary", site_ref, application_id))
        return {"status": "ok", "resource": "site_specific_app_traffic_summary",
                "site_ref": site_ref, "application_id": application_id,
                "data": {"client_row_count": 4, "traffic_total": 99}, "partial": False}

    def read_site_specific_client_traffic_summary(self, site_ref: str,
                                                  client_ref: str) -> dict[str, object]:
        self.calls.append(("site_specific_client_traffic_summary", site_ref, client_ref))
        return {"status": "ok", "resource": "site_specific_client_traffic_summary",
                "site_ref": site_ref, "client_ref": client_ref,
                "data": {"application_row_count": 2, "traffic_total": 17},
                "partial": False}

    def read_site_application_traffic_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_application_traffic_summary", site_ref))
        return {"status": "ok", "resource": "site_application_traffic_summary",
                "site_ref": site_ref, "data": {"returned_application_count": 2},
                "partial": False}

    def read_site_wan_lan_status_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wan_lan_status_summary", site_ref))
        return {"status": "ok", "resource": "site_wan_lan_status_summary",
                "site_ref": site_ref, "data": {"wan_port_count": 1}, "partial": False}

    def read_site_arp_detect_status_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_arp_detect_status_summary", site_ref))
        return {"status": "ok", "resource": "site_arp_detect_status_summary",
                "site_ref": site_ref, "data": {"arp_detection_enabled": True,
                "snoop_for_entry_enabled": False}, "partial": False}

    def read_site_disaster_mode_status(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_disaster_mode_status", site_ref))
        return {"status": "ok", "resource": "site_disaster_mode_status",
                "site_ref": site_ref, "data": {"status_code": 2},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_specification_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_specification_summary", site_ref))
        return {"status": "ok", "resource": "site_specification_summary",
                "site_ref": site_ref,
                "data": {"supported_interface_count": 10,
                         "supported_url_filtering_count": 20,
                         "supported_mac_group_address_count": 30},
                "partial": False}

    def read_site_portal_logout_domain(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_portal_logout_domain", site_ref))
        return {"status": "ok", "resource": "site_portal_logout_domain",
                "site_ref": site_ref, "data": {"domain": ""}}

    def read_site_portal_domain_setting_state(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_portal_domain_setting_state", site_ref))
        return {"status": "ok", "resource": "site_portal_domain_setting_state",
                "site_ref": site_ref,
                "data": {"auto_refresh_enabled": False, "auto_refresh_state": "present",
                         "url_applicable": True, "url_state": "present",
                         "url_configured": True, "missing_field_count": 0,
                         "invalid_field_count": 0, "unknown_field_count": 0},
                "partial": False}

    def read_site_wids_config(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wids_config", site_ref))
        return {"status": "ok", "resource": "site_wids_config",
                "site_ref": site_ref,
                "data": {"enabled": True, "detection_level_code": 2,
                         "detection_codes_applicable": True,
                         "detection_codes": [0, 15, 17]},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_wips_config(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wips_config", site_ref))
        return {"status": "ok", "resource": "site_wips_config",
                "site_ref": site_ref,
                "data": {"enabled": True, "deauthentication_enabled": False,
                         "dynamic_blocking_enabled": True, "lock_time_seconds": 600},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_acl_config_mode(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_acl_config_mode", site_ref))
        return {"status": "ok", "resource": "site_acl_config_mode",
                "site_ref": site_ref,
                "data": {"mode_code": 1, "mode_name": "custom"},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_attack_defense_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_attack_defense_summary", site_ref))
        return {"status": "ok", "resource": "site_attack_defense_summary",
                "site_ref": site_ref,
                "data": {"tcpConnEnable": True, "tcpConnLimit": 1000},
                "missing_field_count": 27, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": True}

    def read_site_attack_defense_defaults_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_attack_defense_defaults_summary", site_ref))
        return {"status": "ok", "resource": "site_attack_defense_defaults_summary",
                "site_ref": site_ref,
                "data": {"tcpConnEnable": True, "tcpConnLimit": 1000},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_wlan_group_detail_summary(self, site_ref: str,
                                            wlan_group_ref: str) -> dict[str, object]:
        self.calls.append(("site_wlan_group_detail_summary", site_ref, wlan_group_ref))
        return {"status": "ok", "resource": "site_wlan_group_detail_summary",
                "site_ref": site_ref, "wlan_group_ref": wlan_group_ref,
                "data": {"name": "Office", "primary": True, "resource": 0},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_lock_to_ap_brief_inventory(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lock_to_ap_brief_inventory", site_ref))
        return {"status": "ok", "resource": "site_lock_to_ap_brief_inventory",
                "site_ref": site_ref,
                "data": {"reported_ap_count": 1, "valid_ap_record_count": 1,
                         "status_category_counts": {"0": 0, "1": 1, "2": 0,
                                                     "3": 0, "4": 0},
                         "status_counts": {},
                         "lock_to_ap_support_counts": {"supported_count": 1,
                                                       "unsupported_count": 0,
                                                       "unreported_count": 0}},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_ineligible_interference_ap_summary(self,
                                                    site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ineligible_interference_ap_summary", site_ref))
        return {"status": "ok", "resource": "site_ineligible_interference_ap_summary",
                "site_ref": site_ref,
                "data": {"reported_ap_count": 2, "valid_ap_count": 2,
                         "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_interference_scan_eligible_summary(self,
                                                    site_ref: str) -> dict[str, object]:
        self.calls.append(("site_interference_scan_eligible_summary", site_ref))
        return {"status": "ok", "resource": "site_interference_scan_eligible_summary",
                "site_ref": site_ref,
                "data": {"reported_ap_count": 2, "valid_ap_count": 2,
                         "scan_status_counts": {"0": 1, "2": 1},
                         "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_alg_config(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_alg_config", site_ref))
        return {"status": "ok", "resource": "site_alg_config",
                "site_ref": site_ref, "data": {"ftp": True},
                "missing_field_count": 4, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": True}

    def read_site_firewall_settings(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_firewall_settings", site_ref))
        return {"status": "ok", "resource": "site_firewall_settings",
                "site_ref": site_ref,
                "data": {"icmp": 100, "broadcastPing": True},
                "missing_field_count": 14, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": True}

    def read_site_firewall_defaults(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_firewall_defaults", site_ref))
        return {"status": "ok", "resource": "site_firewall_defaults",
                "site_ref": site_ref,
                "data": {"timeouts": {"icmp": 30, "tcpEstablished": 900},
                         "flags": {"broadcastPing": False, "synCookies": True}},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_bandwidth_control(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_bandwidth_control", site_ref))
        return {"status": "ok", "resource": "site_bandwidth_control",
                "site_ref": site_ref,
                "data": {"enabled": True, "threshold_control_enabled": False,
                         "threshold_value": None, "returned_port_count": 1,
                         "valid_port_count": 1,
                         "upstream_bandwidth_totals": {"kbps": 100, "mbps": 0},
                         "downstream_bandwidth_totals": {"kbps": 0, "mbps": 100}},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_wan_ports_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wan_ports_summary", site_ref))
        return {"status": "ok", "resource": "site_wan_ports_summary",
                "site_ref": site_ref,
                "data": {"wan_port_count": 1, "valid_wan_port_count": 1,
                         "ipv4_protocol_code_counts": {"2": 1},
                         "ipv6_enabled_port_count": 1, "ipv6_disabled_port_count": 0,
                         "dsl_mer_enabled_count": 0, "dsl_mer_disabled_count": 0,
                         "usb_lte_port_count": 0, "valid_usb_lte_port_count": 0,
                         "usb_config_type_code_counts": {},
                         "usb_connection_mode_code_counts": {}},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_virtual_wan_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_virtual_wan_summary", site_ref))
        return {"status": "ok", "resource": "site_virtual_wan_summary",
                "site_ref": site_ref, "virtual_wan_count": 1, "declared_total": 1,
                "enabled_count": 1, "disabled_count": 0,
                "missing_status_count": 0, "missing_physical_wan_id_count": 0,
                "missing_physical_wan_port_id_count": 0, "invalid_row_count": 0,
                "complete": True, "physical_join": "not_defined_by_source_contract"}

    def read_site_wan_max_speed_summary(self, site_ref: str,
                                        wan_port_ref: str) -> dict[str, object]:
        self.calls.append(("site_wan_max_speed_summary", site_ref + ":" + wan_port_ref))
        return {"status": "ok", "resource": "site_wan_max_speed_summary",
                "site_ref": site_ref, "wan_port_ref": wan_port_ref,
                "data": {"upstream": 1000, "downstream": 5000,
                         "unit": "unspecified_by_source"},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_vlan_network_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_vlan_network_summary", site_ref))
        return {"status": "ok", "resource": "site_vlan_network_summary",
                "site_ref": site_ref,
                "data": {"reported_total_row_count": 1, "returned_row_count": 1,
                         "distinct_vlan_id_count": 1, "purpose_code_counts": {"0": 1},
                         "pages_read": 1, "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_lan_network_detail_summary(self, site_ref: str, network_ref: str) -> dict[str, object]:
        self.calls.append(("site_lan_network_detail_summary", site_ref + ":" + network_ref))
        return {"status": "ok", "resource": "site_lan_network_detail_summary",
                "site_ref": site_ref, "network_ref": network_ref,
                "data": {"purpose_code": 0, "purpose_label": "vlan",
                         "vlan": 20, "dhcp": {"enabled": True, "pool_range_count": 2},
                         "isolation": False, "unknown_field_count": 0,
                         "missing_field_count": 0, "invalid_field_count": 0,
                         "redacted_field_count": 4}, "partial": False}

    def read_site_lan_network_config_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lan_network_config_summary", site_ref))
        return {"status": "ok", "resource": "site_lan_network_config_summary",
                "site_ref": site_ref, "partial": False,
                "data": {"reported_total_network_count": 2,
                         "returned_network_count": 2, "valid_network_record_count": 2,
                         "purpose_code_counts": {"0": 1, "1": 1},
                         "unknown_purpose_code_count": 0,
                         "feature_boolean_counts": {
                             "igmp_snooping": {"enabled_count": 1,
                                                "disabled_count": 0,
                                                "unreported_count": 1}},
                         "pages_read": 1, "truncated": False}}

    def read_site_lan_network_inventory(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lan_network_inventory", site_ref))
        return {"status": "ok", "resource": "site_lan_network_inventory",
                "site_ref": site_ref, "network_count": 2, "returned_count": 2,
                "purpose_counts": {"vlan": 1, "interface": 1},
                "partial": False}

    def read_site_lan_client_inventory_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lan_client_inventory_summary", site_ref))
        return {"status": "ok", "resource": "site_lan_client_inventory_summary",
                "site_ref": site_ref, "inventory_total_count": 1,
                "returned_count": 1, "coverage_complete": True, "partial": False}

    def read_site_topology_root_candidates_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_topology_root_candidates_summary", site_ref))
        return {"status": "ok", "resource": "site_topology_root_candidates_summary",
                "site_ref": site_ref, "root_candidate_count": 1,
                "node_type_counts": {"switch": 1}, "partial": False}

    def read_site_isolated_preconfig_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_isolated_preconfig_summary", site_ref))
        return {"status": "ok", "resource": "site_isolated_preconfig_summary",
                "site_ref": site_ref, "reported_total": 1,
                "categories": {"isolated": {"reported_count": 1},
                               "preconfigured": {"reported_count": 0}},
                "partial": False}

    def read_site_vlan_topology_summary(self, site_ref: str, network_ref: str,
                                        vlan_id: int) -> dict[str, object]:
        self.calls.append(("site_vlan_topology_summary",
                           f"{site_ref}:{network_ref}:{vlan_id}"))
        return {"status": "ok", "resource": "site_vlan_topology_summary",
                "site_ref": site_ref, "network_ref": network_ref,
                "vlan_id": vlan_id, "topology_device_count": 1,
                "device_class_counts": {"switch": 1}, "partial": False}

    def read_site_es_network_overview_summary(self, site_ref: str,
                                              switch_ref: str) -> dict[str, object]:
        self.calls.append(("site_es_network_overview_summary", site_ref + ":" + switch_ref))
        return {"status": "ok", "resource": "site_es_network_overview_summary",
                "site_ref": site_ref, "switch_ref": switch_ref,
                "reported_network_count": 2, "total_port_assignment_count": 5,
                "partial": False}

    def read_site_port_schedule_ports_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_port_schedule_ports_summary", site_ref))
        return {"status": "ok", "resource": "site_port_schedule_ports_summary",
                "site_ref": site_ref, "reported_device_count": 2,
                "schedule_capable_port_count": 5, "partial": False}

    def read_site_longest_client_uptime_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_longest_client_uptime_summary", site_ref))
        return {"status": "ok", "resource": "site_longest_client_uptime_summary",
                "site_ref": site_ref, "total": 12,
                "wiredClient": 3, "wirelessClient": 9,
                "partial": False}

    def read_site_internet_load_balance_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_internet_load_balance_summary", site_ref))
        return {"status": "ok", "resource": "site_internet_load_balance_summary",
                "site_ref": site_ref, "partial": False,
                "data": {"application_optimized_routing_enabled": True,
                         "link_backup_enabled": False, "weight_count": 2,
                         "primary_wan_count": 1, "valid_virtual_wan_count": 0}}

    def read_site_internet_basic_port_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_internet_basic_port_summary", site_ref))
        return {"status": "ok", "resource": "site_internet_basic_port_summary",
                "site_ref": site_ref, "partial": False,
                "data": {"reported_port_count": 2,
                         "port_mode_code_counts": {"0": 1, "1": 1},
                         "port_type_code_counts": {"0": 2, "1": 0}}}

    def read_site_wlan_group_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_wlan_group_summary", site_ref))
        return {"status": "ok", "resource": "site_wlan_group_summary",
                "site_ref": site_ref, "partial": False,
                "data": {"reported_group_count": 2,
                         "primary_group_flag_counts": {
                             "enabled_count": 1, "disabled_count": 1,
                             "unreported_count": 0},
                         "resource_code_counts": {"0": 0, "1": 2, "2": 0}}}

    def read_site_wlan_group_ssids_summary(self, site_ref: str,
                                           wlan_group_ref: str) -> dict[str, object]:
        self.calls.append(("site_wlan_group_ssids_summary", site_ref, wlan_group_ref))
        return {"status": "ok", "resource": "site_wlan_group_ssids_summary",
                "site_ref": site_ref, "wlan_group_ref": wlan_group_ref,
                "partial": False,
                "data": {"returned_ssid_count": 3,
                         "band_coverage_counts": {"2.4GHz": 3, "5GHz": 2, "6GHz": 0}}}

    def read_site_internet_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_internet_summary", site_ref))
        return {"status": "ok", "resource": "site_internet_summary",
                "site_ref": site_ref,
                "data": {"enabled": True, "configured_wan_port_count": 2,
                         "configured_usb_lte_port_count": 0,
                         "configured_lte_wan_count": 0, "gateway_wan_port_count": 2,
                         "unmatched_wan_count": 0, "wan_status_entry_count": 2,
                         "virtual_wan_status_entry_count": 0,
                         "load_balance": {"app_optimized_routing": True,
                                           "link_backup_enabled": False,
                                           "weight_entry_count": 2},
                         "support_flags": {}, "max_wan_count_supported": 4,
                         "dual_sim_support_code": 0, "interval": 60,
                         "interval_unit_code": 1, "resource_code": 1},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_lte_wan_config_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_lte_wan_config_summary", site_ref))
        return {"status": "ok", "resource": "site_lte_wan_config_summary",
                "site_ref": site_ref, "configuration_scope": "stored_lte_wan_settings",
                "status_scope": "documented_controller_modem_codes_internet_reachability_unknown",
                "reported_lte_port_config_count": 1, "partial": False}

    def read_site_nat_exception_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_nat_exception_summary", site_ref))
        return {"status": "ok", "resource": "site_nat_exception_summary",
                "site_ref": site_ref, "scope": "configured_nat_exception_rules",
                "reported_rule_count": 2, "returned_rule_count": 2,
                "enforcement_scope": "configuration_only_effective_enforcement_unknown",
                "partial": False}

    def read_site_vpn_session_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_vpn_session_summary", site_ref))
        return {"status": "ok", "resource": "site_vpn_session_summary",
                "site_ref": site_ref,
                "data": {"reported_session_count": 2, "returned_session_count": 2,
                         "vpn_type_code_counts": {"1": 2}, "server_type_code_counts": {"2": 2},
                         "downstream_bytes": 1000, "upstream_bytes": 2000,
                         "downstream_packets": 10, "upstream_packets": 20,
                         "pages_read": 1, "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_dhcp_candidate_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_dhcp_candidate_summary", site_ref))
        return {"status": "ok", "resource": "site_dhcp_candidate_summary",
                "site_ref": site_ref,
                "data": {"reported_total_candidate_count": 3,
                         "returned_candidate_count": 3,
                         "valid_candidate_record_count": 3,
                         "pages_read": 1, "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_network_reservation_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_network_reservation_summary", site_ref))
        return {"status": "ok", "resource": "site_network_reservation_summary",
                "site_ref": site_ref,
                "data": {"eligible_network_count": 1, "dhcp_server_count": 2,
                         "dhcp_enabled_server_count": 1, "auto_configured_server_count": 1,
                         "reservation_supported_server_count": 2,
                         "configured_range_count": 3},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_dhcp_reservation_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_dhcp_reservation_summary", site_ref))
        return {"status": "ok", "resource": "site_dhcp_reservation_summary",
                "site_ref": site_ref,
                "data": {"reported_total_reservation_count": 3,
                         "returned_reservation_count": 3,
                         "valid_reservation_record_count": 3,
                         "enabled_reservation_count": 2, "disabled_reservation_count": 1,
                         "device_reservation_count": 2, "client_reservation_count": 1,
                         "other_type_reservation_count": 0, "pages_read": 1,
                         "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_dhcp_snooping_status(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_dhcp_snooping_status", site_ref))
        return {"status": "ok", "resource": "site_dhcp_snooping_status",
                "site_ref": site_ref, "data": {"dhcp_snooping_enabled": True},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_dhcp_snoops_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_dhcp_snoops_summary", site_ref))
        return {"status": "ok", "resource": "site_dhcp_snoops_summary",
                "site_ref": site_ref,
                "data": {"reported_total_device_count": 2, "returned_device_count": 2,
                         "valid_device_record_count": 2,
                         "device_type_counts": {"ap": 1, "gateway": 1, "switch": 0,
                                                 "olt": 0, "other": 0},
                         "connected_status_code_counts": {"0": 1, "1": 1},
                         "pages_read": 1, "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_mdns_rule_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_mdns_rule_summary", site_ref))
        return {"status": "ok", "resource": "site_mdns_rule_summary",
                "site_ref": site_ref,
                "data": {"reported_total_rule_count": 2, "returned_rule_count": 2,
                         "valid_rule_record_count": 2, "enabled_rule_count": 1,
                         "disabled_rule_count": 1, "rule_type_code_counts": {"0": 1, "1": 1},
                         "pages_read": 1, "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_mdns_profile_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_mdns_profile_summary", site_ref))
        return {"status": "ok", "resource": "site_mdns_profile_summary",
                "site_ref": site_ref, "profile_count": 1,
                "default_profile_flags": {"true": 1, "false": 0,
                                           "unreported": 0, "invalid": 0},
                "service_entries_per_profile": {"zero": 0, "one": 1, "two": 0,
                                                  "three": 0, "unreported": 0,
                                                  "invalid": 0},
                "invalid_profile_rows": 0, "unknown_profile_field_count": 0,
                "truncated": False, "partial": False}

    def read_site_ddns_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ddns_summary", site_ref))
        return {"status": "ok", "resource": "site_ddns_summary",
                "site_ref": site_ref,
                "data": {"reported_total_ddns_count": 2,
                         "returned_ddns_count": 2, "valid_ddns_record_count": 2,
                         "enabled_ddns_count": 1, "disabled_ddns_count": 1,
                         "service_code_counts": {"0": 1, "5": 1},
                         "support_flags": {"supportCustomDdns": True},
                         "pages_read": 1, "truncated": False},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_snmp_settings_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_snmp_settings_summary", site_ref))
        return {"status": "ok", "resource": "site_snmp_settings_summary",
                "site_ref": site_ref,
                "data": {"snmp_v1_v2c_enabled": False,
                         "snmp_v3_enabled": True, "security_level_code": 2,
                         "authentication_mode_code": 2, "privacy_mode_code": 2},
                "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0, "partial": False}

    def read_site_active_switch_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_active_switch_summary", site_ref))
        return {"status": "ok", "resource": "site_active_switch_summary",
                "site_ref": site_ref, "data": {"device_count": 1,
                "total_traffic_value": 7.0}, "partial": False}

    def read_site_device_memory_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_device_memory_summary", site_ref))
        return {"status": "ok", "resource": "site_device_memory_summary",
                "site_ref": site_ref, "data": {"device_count": 2,
                "maximum_memory_usage_percent": 91}, "partial": False}

    def read_site_switch_dashboard_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_dashboard_summary", site_ref))
        return {"status": "ok", "resource": "site_switch_dashboard_summary",
                "site_ref": site_ref, "data": {"wired_client_count": 4,
                "connected_switch_count": 2, "total_traffic_bytes": 123456},
                "partial": False}

    def read_site_ap_interference_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_ap_interference_summary", site_ref))
        return {"status": "ok", "resource": "site_ap_interference_summary",
                "site_ref": site_ref, "data": {"2g_ap_count": 1,
                "2g_maximum_interference_value": 62, "total_ap_row_count": 1},
                "partial": False}

    def read_site_application_category_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_application_category_summary", site_ref))
        return {"status": "ok", "resource": "site_application_category_summary",
                "site_ref": site_ref, "data": {"category_row_count": 2,
                "total_category_count": 12, "has_more_category_rows": True},
                "partial": True}

    def read_site_application_family_inventory(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_application_family_inventory", site_ref))
        return {"status": "ok", "resource": "site_application_family_inventory",
                "site_ref": site_ref,
                "data": {"family_refs": ["0", "2147483647"],
                         "family_ref_count": 2, "family_row_count": 2,
                         "invalid_row_count": 0, "duplicate_family_id_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_site_application_control_application_catalog(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_application_control_application_catalog", site_ref))
        return {"status": "ok", "resource": "site_application_control_application_catalog",
                "site_ref": site_ref, "source_state": "empty_total_unknown",
                "page_number": 1, "page_size": 100, "page_state": "empty_total_unknown",
                "reported_total_row_count": None, "returned_row_count": 0,
                "reported_remaining_row_count": None,
                "first_page_covers_reported_total": None,
                "pagination_field_coverage": {"totalRows": {"present": 0, "type_valid": 0,
                    "missing": 1, "invalid": 0}},
                "application_id_coverage": {"present": 0, "type_valid": 0,
                    "missing": 0, "invalid": 0},
                "unique_application_id_count": 0, "duplicate_application_id_count": 0,
                "invalid_row_count": 0, "unknown_field_count": 0, "partial": True,
                "application_identifiers_and_labels_returned": False}

    def read_site_application_control_filter_inventory_coverage(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_application_control_filter_inventory_coverage", site_ref))
        total = self.filter_inventory_total
        source_state = "empty_total_unknown" if total is None else "empty"
        return {"status": "ok", "resource": "site_application_control_filter_inventory_coverage",
                "site_ref": site_ref, "source_state": source_state,
                "page_number": 1, "page_size": 100, "page_state": source_state,
                "reported_total_row_count": total, "returned_row_count": 0,
                "reported_remaining_row_count": None if total is None else total,
                "first_page_covers_reported_total": None if total is None else total == 0,
                "pagination_field_coverage": {"totalRows": {"present": int(total is not None),
                    "type_valid": int(total is not None), "missing": int(total is None), "invalid": 0}},
                "filter_field_coverage": {name: {"present": 0, "type_valid": 0,
                    "missing": 0, "invalid": 0} for name in ("filterId", "filterName", "description", "rules")},
                "invalid_row_count": 0, "unknown_field_count": 0,
                "partial": total is None,
                "filter_values_and_rule_objects_returned": False}

    def read_site_gateway_supported_model_references(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_gateway_supported_model_references", site_ref))
        return {"status": "ok", "resource": "site_gateway_supported_model_references",
                "site_ref": site_ref,
                "data": {"model_references": [{"model_id": 0, "model_name": ""}],
                         "model_reference_count": 1, "source_list_present": True,
                         "model_row_count": 1, "missing_field_count": 0,
                         "invalid_row_count": 0, "duplicate_model_id_count": 0,
                         "unknown_field_count": 0}, "partial": False}

    def read_site_category_application_summary(self, site_ref: str,
                                               family_id: str) -> dict[str, object]:
        self.calls.append(("site_category_application_summary", site_ref, family_id))
        return {"status": "ok", "resource": "site_category_application_summary",
                "site_ref": site_ref, "data": {"application_count": 2,
                "block_event_count": 1}, "partial": False}

    def read_site_category_client_summary(self, site_ref: str,
                                          family_id: str) -> dict[str, object]:
        self.calls.append(("site_category_client_summary", site_ref, family_id))
        return {"status": "ok", "resource": "site_category_client_summary",
                "site_ref": site_ref, "data": {"client_count": 3,
                "total_client_traffic_value": 500}, "partial": False}

    def read_site_active_application_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_active_application_summary", site_ref))
        return {"status": "ok", "resource": "site_active_application_summary",
                "site_ref": site_ref, "data": {"application_count": 3,
                "total_client_application_count": 8}, "partial": False}

    def read_site_active_client_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_active_client_summary", site_ref))
        return {"status": "ok", "resource": "site_active_client_summary",
                "site_ref": site_ref, "data": {"client_count": 3,
                "wireless_client_count": 2, "wired_client_count": 1,
                "total_client_traffic_value": 500}, "partial": False}

    def read_site_cpu_usage_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_cpu_usage_summary", site_ref))
        return {"status": "ok", "resource": "site_cpu_usage_summary",
                "site_ref": site_ref, "data": {"device_count": 2,
                "maximum_cpu_util_value": 70}, "partial": False}

    def read_site_client_bubble_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_bubble_summary", site_ref))
        return {"status": "ok", "resource": "site_client_bubble_summary",
                "site_ref": site_ref, "data": {"client_count": 3,
                "total_client_traffic_value": 500, "average_client_rssi_value": -60},
                "partial": False}

    def read_site_traffic_activity_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_traffic_activity_summary", site_ref))
        return {"status": "ok", "resource": "site_traffic_activity_summary",
                "site_ref": site_ref, "data": {"access_point_traffic": {
                "sample_count": 3, "mean_uplink_sample_mb_value": 2.0}},
                "partial": False}

    def read_site_isp_load_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_isp_load_summary", site_ref))
        return {"status": "ok", "resource": "site_isp_load_summary",
                "site_ref": site_ref, "data": {"port_count": 2,
                "sample_count": 10, "mean_latency_ms": 30}, "partial": False}

    def read_site_vpn_tunnel_summary(self, site_ref: str,
                                    vpn_type: int) -> dict[str, object]:
        self.calls.append(("site_vpn_tunnel_summary", site_ref, vpn_type))
        return {"status": "ok", "resource": "site_vpn_tunnel_summary",
                "site_ref": site_ref, "data": {"vpn_type": "server",
                "vpn_count": 1, "total_tunnel_count": 3, "total_tx_bytes": 400},
                "partial": False}

    def read_site_open_vpn_tunnel_summary(self, site_ref: str,
                                         vpn_type: int) -> dict[str, object]:
        self.calls.append(("site_open_vpn_tunnel_summary", site_ref, vpn_type))
        return {"status": "ok", "resource": "site_open_vpn_tunnel_summary",
                "site_ref": site_ref, "data": {"vpn_type": "client",
                "vpn_count": 1, "total_tunnel_count": 2, "total_rx_bytes": 800},
                "partial": False}

    def read_site_client_activity_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_activity_summary", site_ref))
        return {"status": "ok", "resource": "site_client_activity_summary",
                "site_ref": site_ref, "data": {"sample_count": 24,
                "total_new_eap_clients": 2}}

    def read_site_client_association_activity_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_client_association_activity_summary", site_ref))
        return {"status": "ok", "resource": "site_client_association_activity_summary",
                "site_ref": site_ref, "data": {"total_clients": 12,
                "wired_clients": 3, "wireless_clients": 9}}

    def read_site_client_traffic_summary(self, site_ref: str, page_number: int,
                                         page_size: int) -> dict[str, object]:
        self.calls.append(("site_client_traffic_summary", site_ref, page_number, page_size))
        return {"status": "ok", "resource": "site_client_traffic_summary",
                "site_ref": site_ref, "data": {"page_number": page_number,
                "page_size": page_size, "total_rows": 3, "returned_client_count": 2,
                "has_more_pages": True, "client_traffic_total": 80},
                "partial": True}

    def read_site_recent_clients_summary(self, site_ref: str, start_ms: int,
                                          end_ms: int) -> dict[str, object]:
        self.calls.append(("site_recent_clients_summary", site_ref, start_ms, end_ms))
        return {"status": "ok", "resource": "site_recent_clients_summary",
                "site_ref": site_ref, "reported_client_count": 7,
                "sampled_row_count": 5, "partial": True}

    def read_site_device_tag_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_device_tag_summary", site_ref))
        return {"status": "ok", "resource": "site_device_tag_summary",
                "site_ref": site_ref,
                "data": {"tag_count": 2, "tag_id_present_count": 2,
                         "tag_name_present_count": 2, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0},
                "partial": False}

    def read_ap_wired_uplink(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_wired_uplink", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_wired_uplink", "site_ref": site_ref,
                "device_ref": ap_ref,
                "data": {"wiredUplink": {"duplex": 2, "linkSpeed": 1000}},
                "partial": False, "missing_fields": [], "invalid_fields": [],
                "unknown_field_count": 0, "redacted_field_count": 9}

    def read_ap_lldp_config(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_lldp_config", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_lldp_config", "site_ref": site_ref,
                "device_ref": ap_ref,
                "data": {"setting_code": 2, "setting": "site_default", "supported": True},
                "partial": False, "missing_field_count": 0, "invalid_field_count": 0,
                "unknown_field_count": 0}

    def read_ap_port_vlans(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_port_vlans", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_port_vlans", "site_ref": site_ref,
                "device_ref": ap_ref, "count": 0, "total_rows": 0,
                "vlan_id_counts": {},
                "port_counts": {"nativePort": 0, "tagPort": 0, "untagPort": 0},
                "redacted_field_count": 0, "unknown_field_count": 0,
                "invalid_row_or_field_count": 0, "partial": False}

    def read_ap_bridge_config(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_bridge_config", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_bridge_config", "site_ref": site_ref,
                "device_ref": ap_ref, "data": {"hw_switch_code": 1,
                "tdma_status_code": 0, "tdma_client_count": 0,
                "tdma_unsupported_client_count": 0,
                "client_priority_counts": {0: 0, 1: 0, 2: 0}},
                "redacted_field_count": 3, "unknown_field_count": 0,
                "invalid_field_count": 0, "partial": False}

    def read_ap_mesh_candidates(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_mesh_candidates", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_mesh_candidates", "site_ref": site_ref,
                "device_ref": ap_ref, "count": 0, "total_rows": 0,
                "link_status_counts": {}, "hop_counts": {}, "child_ap_total": 0,
                "recommended_count": 0, "not_recommended_count": 0,
                "recommended_radio_id_counts": {}, "radio_id_counts": {},
                "channel_counts": {}, "rssi_value_counts": {},
                "redacted_field_count": 0, "unknown_field_count": 0,
                "invalid_field_count": 0, "missing_field_count": 0,
                "partial": False}

    def read_ap_general_config(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_general_config", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_general_config", "site_ref": site_ref,
                "device_ref": ap_ref, "ledSetting": 0, "tag_count": 0,
                "location_configured": False, "rssi_led_setting_count": 0,
                "rssi_threshold_counts": {}, "redacted_field_count": 0,
                "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False}

    def read_ap_ip_setting(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_ip_setting", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_ip_setting", "site_ref": site_ref,
                "device_ref": ap_ref, "mode": "DHCP", "dhcp_setting_present": True,
                "static_setting_present": False, "fallback_enabled": False,
                "reserved_address_enabled": None, "redacted_value_count": 0,
                "redacted_field_count": 0, "unknown_field_count": 0,
                "invalid_field_count": 0, "missing_field_count": 0, "partial": False}

    def read_ap_ipv6_setting(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_ipv6_setting", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_ipv6_setting", "site_ref": site_ref,
                "device_ref": ap_ref, "ipv6_enabled": True, "mode": "dynamic",
                "dynamic_setting_present": True, "static_setting_present": False,
                "dns_mode": 0, "static_prefix_length": None,
                "redacted_address_value_count": 0, "redacted_field_count": 0,
                "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False}

    def read_ap_p2p_info(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_p2p_info", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_p2p_info", "site_ref": site_ref,
                "device_ref": ap_ref, "main_ap_present": False, "child_ap_count": 0,
                "redacted_identity_field_count": 0, "redacted_field_count": 0,
                "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False}

    def read_ap_l3_access(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_l3_access", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_l3_access", "site_ref": site_ref,
                "device_ref": ap_ref, "enabled": False, "supported": True,
                "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False}

    def read_ap_paring_window(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_paring_window", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_paring_window", "site_ref": site_ref,
                "device_ref": ap_ref, "client_ap_count": 0,
                "client_status_counts": {}, "rssi_value_counts": {},
                "redacted_identity_field_count": 0, "redacted_field_count": 0,
                "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False}

    def read_ap_lag_config(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_lag_config", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_lag_config", "site_ref": site_ref,
                "device_ref": ap_ref, "supported": True, "enabled": False,
                "mode": None, "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False}

    def read_ap_rf_scan(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_rf_scan", site_ref + ":" + ap_ref))
        return {**_ap_rf_scan_payload(), "site_ref": site_ref, "device_ref": ap_ref}

    def read_ap_rf_scan_v2(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_rf_scan_v2", site_ref + ":" + ap_ref))
        return {**_ap_rf_scan_payload(), "resource": "ap_rf_scan_v2",
                "site_ref": site_ref, "device_ref": ap_ref}

    def read_ap_management_ssid(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_management_ssid", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_management_ssid",
                "site_ref": site_ref, "device_ref": ap_ref,
                "enabled": True, "broadcast_enabled": True,
                "security_mode_code": 3, "personal_settings_present": True,
                "enterprise_settings_present": False, "vlan_mode_code": 0,
                "custom_vlan_mode_code": None, "vlan_id_present": False,
                "bridge_vlan_present": False, "network_binding_present": False,
                "redacted_field_count": 2, "unknown_field_count": 0,
                "invalid_field_count": 0, "missing_field_count": 0,
                "partial": False}

    def read_ap_snmp_config(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_snmp_config", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_snmp_config",
                "site_ref": site_ref, "device_ref": ap_ref,
                "type_code": 1, "location_present": True,
                "contact_present": True, "redacted_field_count": 2,
                "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False}

    def read_ap_vlan_v1(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_vlan_v1", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_vlan_v1",
                "site_ref": site_ref, "device_ref": ap_ref,
                "mode_code": 1, "bridge_vlan_present": True,
                "network_binding_present": True, "redacted_field_count": 1,
                "unknown_field_count": 0, "invalid_field_count": 0,
                "missing_field_count": 0, "partial": False}

    def read_ap_wlan_overrides(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_wlan_overrides", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_wlan_overrides",
                "site_ref": site_ref, "device_ref": ap_ref,
                "entry_count": 2, "included_entry_count": 2,
                "truncated_entry_count": 0, "enabled_count": 1,
                "disabled_count": 1, "unknown_enabled_state_count": 0,
                "vlan_enabled_count": 1, "vlan_disabled_count": 1,
                "unknown_vlan_state_count": 0, "password_present_count": 1,
                "vlan_id_present_count": 1, "vlan_pool_present_count": 0,
                "by_band_code": {1: 2}, "by_security_code": {3: 2},
                "ap_group_assigned": True, "redacted_field_count": 8,
                "invalid_row_count": 0, "unknown_field_count": 0,
                "invalid_field_count": 0, "missing_field_count": 0,
                "partial": False}

    def read_ap_lan_traffic(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_lan_traffic", site_ref + ":" + ap_ref))
        return _lan_traffic_payload(site_ref=site_ref, device_ref=ap_ref)

    def read_ap_afc_status(self, site_ref: str, ap_ref: str) -> dict[str, object]:
        self.calls.append(("ap_afc_status", site_ref + ":" + ap_ref))
        return {"status": "ok", "resource": "ap_afc_status", "site_ref": site_ref,
                "device_ref": ap_ref, "data": {"enabled": True}, "partial": False,
                "missing_fields": [], "invalid_fields": [], "unknown_field_count": 0}

    def list_clients(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("clients", site_ref))
        return {"status": "ok", "resource": "clients", "count": 0, "items": []}

    def current_client_diagnostic_inventory(self, site_ref: str) -> dict[str, object]:
        return {
            "sites": {"status": "ok", "resource": "sites", "count": 1,
                      "items": [{"site_ref": site_ref}]},
            "clients": {"status": "ok", "resource": "clients", "count": 1,
                        "items": [{"client_ref": "c" * 24, "wireless": True,
                                   "channel": 36}]},
        }

    def list_networks(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("networks", site_ref))
        return {"status": "ok", "resource": "networks", "count": 0, "items": []}

    def read_network_dhcp_server_capabilities(
        self, site_ref: str, network_ref: str,
    ) -> dict[str, object]:
        self.calls.append(("network_dhcp_server_capabilities", site_ref + ":" + network_ref))
        return {"status": "ok", "resource": "network_dhcp_server_capabilities",
                "site_ref": site_ref, "network_ref": network_ref,
                "data": {"capabilities": {"get_dhcp_client_table": True,
                                            "get_dhcp_server_info": False},
                         "present_count": 2, "missing_count": 0,
                         "invalid_count": 0, "unknown_field_count": 0}, "partial": False}

    def read_network_dhcp_server_info(
        self, site_ref: str, network_ref: str,
    ) -> dict[str, object]:
        self.calls.append(("network_dhcp_server_info", site_ref + ":" + network_ref))
        return {"status": "ok", "resource": "network_dhcp_server_info",
                "site_ref": site_ref, "network_ref": network_ref,
                "data": {"range_count": 1, "included_range_count": 1,
                         "omitted_range_count": 0, "available_ip_count": 12,
                         "available_ip_values_count": 1, "invalid_range_count": 0,
                         "unknown_field_count": 0, "missing_ranges_count": 0},
                "partial": False}

    def list_ssids(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("ssids", site_ref))
        return {"status": "ok", "resource": "ssids", "count": 0, "items": []}

    def read_site_mac_auth_ssid_inventory(self, site_ref: str,
                                          device_type: int) -> dict[str, object]:
        self.calls.append(("site_mac_auth_ssid_inventory", site_ref, device_type))
        return {"status": "ok", "resource": "site_mac_auth_ssid_inventory",
                "site_ref": site_ref, "device_type": device_type,
                "wlan_count": 1, "ssid_count": 2,
                "items": [{"wlan_name": "Office", "ssid_names": ["Staff", "Guest"]}],
                "partial": False}

    def read_site_stack_connections_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_stack_connections_summary", site_ref))
        return {"status": "ok", "resource": "site_stack_connections_summary",
                "site_ref": site_ref, "data": {"stacks": []}, "partial": False}

    def read_site_stack_network_summary(self, site_ref: str,
                                        stack_ref: str) -> dict[str, object]:
        self.calls.append(("site_stack_network_summary", site_ref, stack_ref))
        return {"status": "ok", "resource": "site_stack_network_summary",
                "site_ref": site_ref, "stack_ref": stack_ref,
                "reported_network_count": 3}

    def read_site_stack_static_routing_summary(self, site_ref: str,
                                                stack_ref: str) -> dict[str, object]:
        self.calls.append(("site_stack_static_routing_summary", site_ref, stack_ref))
        return {"status": "ok", "resource": "site_stack_static_routing_summary",
                "site_ref": site_ref, "stack_ref": stack_ref}

    def read_site_stack_ospf_neighbor_summary(self, site_ref: str,
                                               stack_ref: str) -> dict[str, object]:
        self.calls.append(("site_stack_ospf_neighbor_summary", site_ref, stack_ref))
        return {"status": "ok", "resource": "site_stack_ospf_neighbor_summary",
                "site_ref": site_ref, "stack_ref": stack_ref}

    def read_site_stack_cable_test_log_summary(self, site_ref: str,
                                               stack_ref: str) -> dict[str, object]:
        self.calls.append(("site_stack_cable_test_log_summary", site_ref, stack_ref))
        return {"status": "ok", "resource": "site_stack_cable_test_log_summary",
                "site_ref": site_ref, "stack_ref": stack_ref,
                "port_entry_counts": {"tested_port_entries": 1}}

    def read_site_intelli_recover_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_intelli_recover_summary", site_ref))
        return {"status": "ok", "resource": "site_intelli_recover_summary",
                "site_ref": site_ref}

    def read_site_port_forwarding_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_port_forwarding_summary", site_ref))
        return {"status": "ok", "resource": "site_port_forwarding_summary",
                "site_ref": site_ref}

    def read_site_stack_dhcp_user_summary(self, site_ref: str,
                                          stack_ref: str) -> dict[str, object]:
        self.calls.append(("site_stack_dhcp_user_summary", site_ref, stack_ref))
        return {"status": "ok", "resource": "site_stack_dhcp_user_summary",
                "site_ref": site_ref, "returned_user_count": 2}

    def read_site_stack_vlan_interface_summary(self, site_ref: str,
                                               stack_ref: str) -> dict[str, object]:
        self.calls.append(("site_stack_vlan_interface_summary", site_ref, stack_ref))
        return {"status": "ok", "resource": "site_stack_vlan_interface_summary",
                "site_ref": site_ref, "reported_interface_count": 0}

    def read_site_snmp_incompatible_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_snmp_incompatible_summary", site_ref))
        return {"status": "ok", "resource": "site_snmp_incompatible_summary",
                "site_ref": site_ref, "reported_incompatible_device_total": 0}

    def read_site_gateway_general_config_summary(
            self, site_ref: str, gateway_ref: str) -> dict[str, object]:
        self.calls.append(("site_gateway_general_config_summary", site_ref, gateway_ref))
        return {"status": "ok", "resource": "gateway_general_config_summary",
                "site_ref": site_ref, "gateway_ref": gateway_ref}

    def read_site_switch_general_config_summary(
            self, site_ref: str, switch_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_general_config_summary", site_ref, switch_ref))
        return {"status": "ok", "resource": "switch_general_config_summary",
                "site_ref": site_ref, "switch_ref": switch_ref}
    def read_site_switch_oui_vlan_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_switch_oui_vlan_summary", site_ref))
        return {"status": "ok", "resource": "site_switch_oui_vlan_summary",
                "site_ref": site_ref, "returned_rule_count": 1}
    def read_client_health_detail_v2(self, site_ref: str, client_ref: str) -> dict[str, object]:
        self.calls.append(("client_health_detail_v2", site_ref + ":" + client_ref))
        return {"status": "ok", "resource": "client_health_detail_v2",
                "site_ref": site_ref, "client_ref": client_ref,
                "window_start_ms": 1, "window_end_ms": 86_400_001,
                "health_version": 2, "score": 80, "dimensions": {},
                "dimension_count": 0, "partial": False,
                "series_point_coverage": {
                    "inspected_structurally_valid_count": 2,
                    "past_num_missing_count": 1,
                    "past_num_explicit_null_count": 1,
                    "past_num_present_non_null_count": 0}}

    def read_client_health(self, site_ref: str, client_ref: str) -> dict[str, object]:
        self.calls.append(("client_health", site_ref + ":" + client_ref))
        return {"status": "ok", "resource": "client_health", "site_ref": site_ref,
                "client_ref": client_ref, "partial": True,
                "unclassified_minus_one_fields": ["score"],
                "data": {"score": None}}

    def read_site_backup_inventory_summary(self, site_ref: str) -> dict[str, object]:
        self.calls.append(("site_backup_inventory_summary", site_ref))
        return {"status": "ok", "resource": "site_backup_inventory_summary",
                "site_ref": site_ref, "backup_file_count": 1}
    def read_controller_backup_inventory_summary(self) -> dict[str, object]:
        self.calls.append(("controller_backup_inventory_summary", None))
        return {"status": "ok", "resource": "controller_backup_inventory_summary",
                "backup_file_count": 2, "latest_listed_backup_time_ms": 1800000000000}

class OpenApiHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.token = "caller-secret-do-not-log-0123456789abcdef"
        self.token_path = os.path.join(self.tempdir.name, "caller-token")
        with open(self.token_path, "w", encoding="utf-8") as handle:
            handle.write(self.token + "\n")
        self.fake = FakeOpenApiClient()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.logs = io.StringIO()
        self.stdout_patch = patch("builtins.print", side_effect=lambda *a, **k: self.logs.write(" ".join(map(str, a)) + "\n"))
        self.stdout_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_path})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.fake)
        self.client_patch.start()

    def tearDown(self) -> None:
        self.client_patch.stop()
        self.env_patch.stop()
        self.stdout_patch.stop()
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.tempdir.cleanup()

    def request(self, path: str, token: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        raw_body = response.read()
        self.last_response_bytes = len(raw_body)
        self.last_response_raw = raw_body
        body = json.loads(raw_body)
        connection.close()
        return response.status, body

    def request_post(self, path: str, body: dict[str, object], token: str | None = None,
                     origin: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if origin is not None:
            headers["Origin"] = origin
        connection.request("POST", path, body=json.dumps(body), headers=headers)
        response = connection.getresponse()
        raw_body = response.read()
        self.last_response_bytes = len(raw_body)
        self.last_response_raw = raw_body
        payload = json.loads(raw_body)
        connection.close()
        return response.status, payload

    def test_webfilter_adapters_use_documented_paths_and_redacted_projections(self) -> None:
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        self.assertTrue(client._site_ap_webfilter_request_valid(
            "/openapi/v1/ctrl/sites/site_1/url-filters/eap?page=1&pageSize=100"))
        self.assertFalse(client._site_ap_webfilter_request_valid(
            "/openapi/v1/other/sites/site_1/url-filters/eap?page=1&pageSize=100"))
        self.assertFalse(client._site_ap_webfilter_request_valid(
            "/openapi/v1/ctrl/sites/site_1/url-filters/eap?page=11&pageSize=100"))
        self.assertTrue(client._site_url_filter_general_request_valid(
            "/openapi/v1/ctrl/sites/site_1/url-filters/globalUrlFilter"))
        self.assertFalse(client._site_url_filter_general_request_valid(
            "/openapi/v1/other/sites/site_1/url-filters/globalUrlFilter"))
        calls = []

        def upstream(method, path, **kwargs):
            calls.append((method, path))
            if path.startswith("/openapi/v1/ctrl/sites/site_1/url-filters/eap?"):
                return {"errorCode": 0, "result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "supportKeyword": True, "supportCategory": False,
                    "supportTimeSchedule": True,
                    "data": [{"type": "ap", "status": True, "filterMode": 0,
                              "existKeyword": False, "existCategory": True,
                              "existTimeSchedule": False, "urls": ["private.example"],
                              "sourceIds": ["private-id"]}]}}
            return {"errorCode": 0, "result": {
                "safeSearch": True, "blockPage": False,
                "blockPageMessage": "private message"}}

        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            ap = client.read_site_ap_webfilter_summary(site_ref)
            general = client.read_site_url_filter_general_summary(site_ref)
        self.assertEqual(ap["by_documented_endpoint_rule_type"]["ap"], 1)
        self.assertNotIn("private.example", json.dumps(ap))
        self.assertNotIn("private-id", json.dumps(ap))
        self.assertEqual(general["reported_settings"],
                         {"safeSearch": "enabled", "blockPage": "disabled"})
        self.assertNotIn("private message", json.dumps(general))
        self.assertEqual(calls, [
            ("GET", "/openapi/v1/ctrl/sites/site_1/url-filters/eap?page=1&pageSize=100"),
            ("GET", "/openapi/v1/ctrl/sites/site_1/url-filters/globalUrlFilter")])

    def test_lan_isolation_and_ospf_adapters_validate_and_redact(self) -> None:
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        self.assertTrue(client._site_lan_interface_isolation_request_valid(
            "/openapi/v2/ctrl/sites/site_1/lan-networks/isolate/interfaces"))
        self.assertFalse(client._site_lan_interface_isolation_request_valid(
            "/openapi/v2/ctrl/sites/site_1/lan-networks/isolate/interfaces?searchKey=x"))
        self.assertTrue(client._site_ospf_interface_request_valid(
            "/openapi/v1/ctrl/sites/site_1/ospf/interface?page=1&pageSize=100"))
        self.assertFalse(client._site_ospf_interface_request_valid(
            "/openapi/v1/ctrl/sites/site_1/ospf/interface?page=11&pageSize=100"))
        calls = []

        def upstream(method, path, **kwargs):
            calls.append((method, path))
            if "/lan-networks/isolate/interfaces" in path:
                return {"errorCode": 0, "result": [
                    {"name": "private LAN", "id": "private-id", "vlan": 10,
                     "isolation": True}, {"isolation": False}]}
            return {"errorCode": 0, "result": {
                "totalRows": 1, "currentPage": 1, "currentSize": 1,
                "data": [{"deviceName": "private-switch", "mac": "00:11:22:33:44:55",
                          "vlanId": 10, "type": 0, "networkType": 0, "cost": 10,
                          "authenticationType": 0, "simpleKey": "private-key"}]}}

        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            isolation = client.read_site_lan_interface_isolation_summary(site_ref)
            ospf = client.read_site_ospf_interface_summary(site_ref)
        self.assertEqual(isolation["reported_isolation"]["isolated"], 1)
        self.assertEqual(ospf["by_documented_network_type"]["broadcast"], 1)
        for secret in ("private LAN", "private-id", "private-switch", "00:11:22:33:44:55",
                       "private-key", "10"):
            self.assertNotIn(secret, json.dumps(isolation) + json.dumps(ospf))
        self.assertEqual(calls, [
            ("GET", "/openapi/v2/ctrl/sites/site_1/lan-networks/isolate/interfaces"),
            ("GET", "/openapi/v1/ctrl/sites/site_1/ospf/interface?page=1&pageSize=100")])

    def test_switch_qos_and_ddm_adapters_bound_reads_and_bind_fresh_switch_inventory(self) -> None:
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        mac = "00:11:22:33:44:55"
        self.assertTrue(client._site_switch_qos_rules_request_valid(
            "/openapi/v1/ctrl/sites/site_1/switch-qos/qos-rule?page=1&pageSize=100"))
        self.assertFalse(client._site_switch_qos_rules_request_valid(
            "/openapi/v1/ctrl/sites/site_1/switch-qos/qos-rule?page=1&pageSize=100&searchKey=x"))
        self.assertTrue(client._site_switch_ddm_request_valid(
            f"/openapi/v1/ctrl/sites/site_1/switches/{mac}/ddm/info"))
        self.assertFalse(client._site_switch_ddm_request_valid(
            f"/openapi/v1/other/sites/site_1/switches/{mac}/ddm/info"))
        inventory_rows = [{"deviceId": "switch-1", "mac": mac,
                           "deviceType": "switch", "name": "private switch"}]
        # Fixed synthetic key makes the expected opaque inventory reference
        # contain the same digits as the raw QoS port marker.
        client._ref_key = b"ddm-collision-40"
        device_ref = client._opaque_ref("device", "site_1:switch-1")
        self.assertIn("443", device_ref)
        calls = []

        def upstream(method, path, **kwargs):
            calls.append((method, path))
            if "/switch-qos/qos-rule?" in path:
                return {"errorCode": 0, "result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [{"type": 1, "status": True, "queue": 3,
                              "name": "private qos", "id": "private-id",
                              "sPort": 443, "dPort": 8443}]}}
            return {"errorCode": 0, "result": [
                {"port": 7, "standardPort": "1/0/7", "dataReady": 1,
                 "transmitFault": 0, "lossOfSignal": 1,
                 "rxPower": 0.42, "txPower": 0.81, "temperature": 51.5}]}

        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_pages", return_value=inventory_rows) as inventory, \
                patch.object(client, "_request_json", side_effect=upstream):
            qos = client.read_site_switch_qos_summary(site_ref)
            ddm = client.read_site_switch_ddm_summary(site_ref, device_ref)
        self.assertEqual(qos["by_documented_queue"]["3"], 1)
        self.assertEqual(ddm["reported_controller_flags"]["lossOfSignal"]["reported_loss"], 1)
        self.assertEqual(inventory.call_count, 1)
        self.assertEqual(ddm["device_ref"], device_ref)
        self.assertEqual(calls, [
            ("GET", "/openapi/v1/ctrl/sites/site_1/switch-qos/qos-rule?page=1&pageSize=100"),
            ("GET", f"/openapi/v1/ctrl/sites/site_1/switches/{mac}/ddm/info")])
        markers = ("private qos", "private-id", "443", "8443", mac,
                   "1/0/7", "0.42", "0.81", "51.5")

        def assert_redacted(qos_result, ddm_result):
            self.assertEqual(ddm_result.get("device_ref"), device_ref)
            # The opaque reference is verified separately; only that exact
            # token is excluded from raw-value marker searches.
            ddm_without_verified_ref = {
                key: value for key, value in ddm_result.items() if key != "device_ref"}
            serialized = json.dumps(qos_result) + json.dumps(ddm_without_verified_ref)
            for marker in markers:
                self.assertNotIn(marker, serialized)

        assert_redacted(qos, ddm)
        # A raw port value remains detectable even when the opaque token itself
        # contains the same digits.
        with self.assertRaises(AssertionError):
            assert_redacted(qos, {**ddm, "raw_port_marker": "443"})

    def test_switch_ddm_refuses_duplicate_fresh_inventory_match(self) -> None:
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        rows = [{"deviceId": "switch-1", "mac": "00:11:22:33:44:55",
                 "deviceType": "switch"}] * 2
        device_ref = client._opaque_ref("device", "site_1:switch-1")
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_pages", return_value=rows), \
                patch.object(client, "_request_json") as request:
            with self.assertRaises(OpenApiError) as raised:
                client.read_site_switch_ddm_summary(site_ref, device_ref)
        self.assertEqual(raised.exception.code, "device_ref_ambiguous")
        request.assert_not_called()

    def test_switch_ddm_rejects_untyped_generic_result(self) -> None:
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        device_ref = client._opaque_ref("device", "site_1:switch-1")
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_pages", return_value=[{
                    "deviceId": "switch-1", "mac": "00:11:22:33:44:55",
                    "deviceType": "switch"}]), \
                patch.object(client, "_request_json", return_value={
                    "errorCode": 0, "result": {"untyped": "payload"}}):
            with self.assertRaises(OpenApiError) as raised:
                client.read_site_switch_ddm_summary(site_ref, device_ref)
        self.assertEqual(raised.exception.code, "openapi_response_invalid")

    def test_switch_qos_rejects_untyped_generic_result(self) -> None:
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={
                    "errorCode": 0, "result": {"untyped": "payload"}}):
            with self.assertRaises(OpenApiError) as raised:
                client.read_site_switch_qos_summary(site_ref)
        self.assertEqual(raised.exception.code, "openapi_response_invalid")

    def test_http_ap_overview_uses_site_bound_reference_and_redacted_projection(self) -> None:
        site_ref, ap_ref = "a" * 24, "b" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "00-11-22-33-44-55"}
        upstream_calls = []
        def upstream(method, path, **kwargs):
            upstream_calls.append((method, path))
            return {"result": {"model": "EAP650", "firmwareVersion": "1.2.3",
                "cpuUtil": 13, "memoryUtil": 44, "uptimeLong": 123456,
                "status": 15, "statusCategory": 1, "wirelessLinked": True,
                "mac": "00-11-22-33-44-55", "ip": "192.0.2.1", "name": "Secret AP",
                "ipv6List": ["2001:db8::1"], "wireless uplink info": {"name": "private"}}}
        main._openapi_client.return_value = client
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            status, response = self.request(
                f"/v1/sites/{site_ref}/aps/{ap_ref}/summary", self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["data"], {"device_ref": ap_ref, "model": "EAP650",
                "firmware": "1.2.3", "cpu_percent": 13, "memory_percent": 44,
                "uptime_seconds": 123456, "status_code": 15, "status_category": 1,
                "wireless_linked": True})
            for secret in ("00-11-22-33-44-55", "192.0.2.1", "Secret AP", "2001:db8::1", "private"):
                self.assertNotIn(secret, json.dumps(response))
            self.assertEqual(upstream_calls, [("GET", "/openapi/v1/ctrl/sites/site_1/aps/00-11-22-33-44-55")])

            for wrong_site, wrong_ap, expected in (
                    ("c" * 24, ap_ref, "site_ref_unknown"),
                    (site_ref, "d" * 24, "device_ref_unknown")):
                status, body = self.request(
                    f"/v1/sites/{wrong_site}/aps/{wrong_ap}/summary", self.token)
                self.assertEqual(status, 502)
                self.assertEqual(body["error"], expected)
                self.assertEqual(len(upstream_calls), 1)

        status, body = self.request(f"/v1/sites/{site_ref}/aps/not-a-ref/summary", self.token)
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "not_found")
        self.assertEqual(len(upstream_calls), 1)

    def test_http_and_mcp_duplicate_ssid_summary_redact_names_and_bind_site(self) -> None:
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        upstream_calls = []
        def upstream(method, path, **kwargs):
            upstream_calls.append((method, path))
            return {"result": {"ssidNameMap": {"Sensitive WLAN": 3},
                "duplicateSsidNames": ["Sensitive WLAN"], "siteId": "site_1"}}
        main._openapi_client.return_value = client
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            status, response = self.request(
                f"/v1/sites/{site_ref}/ssids/duplicate-summary", self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["resource"], "site_duplicate_ssid_summary")
            self.assertEqual(response["data"]["duplicate_name_count"], 1)
            self.assertNotIn("Sensitive WLAN", json.dumps(response))
            rpc = {"jsonrpc": "2.0", "id": 161, "method": "tools/call",
                   "params": {"name": "omada_site_duplicate_ssid_summary",
                              "arguments": {"site_ref": site_ref}}}
            status, mcp = self.request_post("/mcp", rpc, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(mcp["result"]["structuredContent"]["resource"],
                             "site_duplicate_ssid_summary")
            self.assertNotIn("Sensitive WLAN", json.dumps(mcp))
            self.assertEqual(len(upstream_calls), 2)

            status, body = self.request(
                f"/v1/sites/{'b' * 24}/ssids/duplicate-summary", self.token)
            self.assertEqual(status, 502)
            self.assertEqual(body["error"], "site_ref_unknown")
            self.assertEqual(len(upstream_calls), 2)

    def test_http_and_mcp_ssid_ap_groups_use_current_ssid_snapshot(self) -> None:
        site_ref, ssid_ref = "a" * 24, "b" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        client._ssid_ids_by_site_ref[site_ref] = {ssid_ref: "ssid_1"}
        upstream_calls = []
        def upstream(method, path, **kwargs):
            upstream_calls.append((method, path))
            return {"result": {"apGroups": [{"id": "group-secret", "name": "Secret Group",
                "apNum": 2, "remainingBinding": {"2g": 4}}],
                "maxSsids2G": 8, "maxSsids5G": 16, "maxSsids6G": 8, "maxSsidsMlo": 4}}
        main._openapi_client.return_value = client
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            route = f"/v1/sites/{site_ref}/ssids/{ssid_ref}/ap-groups"
            status, response = self.request(route, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["resource"], "ssid_ap_groups")
            self.assertEqual(response["data"]["group_count"], 1)
            self.assertNotIn("group-secret", json.dumps(response))
            self.assertNotIn("Secret Group", json.dumps(response))
            rpc = {"jsonrpc": "2.0", "id": 162, "method": "tools/call",
                   "params": {"name": "omada_ssid_ap_groups",
                              "arguments": {"site_ref": site_ref, "ssid_ref": ssid_ref}}}
            status, mcp = self.request_post("/mcp", rpc, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(mcp["result"]["structuredContent"]["resource"], "ssid_ap_groups")
            self.assertEqual(len(upstream_calls), 2)
            for wrong_site, wrong_ssid, code in (("c" * 24, ssid_ref, "site_ref_unknown"),
                                                 (site_ref, "d" * 24, "ssid_ref_unknown")):
                status, body = self.request(
                    f"/v1/sites/{wrong_site}/ssids/{wrong_ssid}/ap-groups", self.token)
                self.assertEqual(status, 502)
                self.assertEqual(body["error"], code)
                self.assertEqual(len(upstream_calls), 2)

    def test_http_and_mcp_topology_network_summary_redact_names_and_vlan_values(self) -> None:
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        calls = []
        def upstream(method, path, **kwargs):
            calls.append((method, path))
            return {"result": {
                "splitNetworks": [{"id": "network-secret", "name": "Private LAN",
                    "vlanId": 17, "defaultNetwork": True, "configuring": False}],
                "ssids": [{"id": "ssid-secret", "name": "Private WLAN",
                    "wlanName": "Private WLAN", "vlanEnable": True, "vlanIds": [17],
                    "configuring": False, "clientNum": 4}],
            }}
        main._openapi_client.return_value = client
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            route = f"/v1/sites/{site_ref}/topology/network-summary"
            status, response = self.request(route, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["resource"], "site_topology_network_summary")
            self.assertEqual(response["data"]["ssid_client_count_sum"], 4)
            for private_value in ("network-secret", "Private LAN", "ssid-secret", "Private WLAN"):
                self.assertNotIn(private_value, json.dumps(response))
            self.assertEqual(response["data"]["ssid_vlan_id_count"], 1)
            rpc = {"jsonrpc": "2.0", "id": 163, "method": "tools/call",
                   "params": {"name": "omada_site_topology_network_summary",
                              "arguments": {"site_ref": site_ref}}}
            status, mcp = self.request_post("/mcp", rpc, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(mcp["result"]["structuredContent"]["resource"],
                             "site_topology_network_summary")
            self.assertNotIn("Private WLAN", json.dumps(mcp))
            self.assertEqual(len(calls), 2)

    def test_topology_snapshot_and_qos_service_profiles_use_fixed_redacted_reads(self) -> None:
        site_ref = "c" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        calls = []
        def upstream(method, path, **kwargs):
            calls.append((method, path))
            if path.endswith("/topology"):
                return {"errorCode": 0, "result": {
                    "topologyNodes": [{"mac": "private-mac", "name": "private-name"}],
                    "topologyEdges": [{"upLinkMac": "private-mac",
                        "downLinkMac": "missing-mac", "blocked": True,
                        "blockedVlans": "private-vlan", "port": {"name": "secret"}}],
                }}
            return {"errorCode": 0, "result": {
                "totalRows": 1, "currentPage": 1, "currentSize": 1,
                "data": [{"id": "private-id", "defaultProfile": True, "name": "secret",
                          "protocol": 0, "destStartPort": 443, "description": "private"}],
            }}
        main._openapi_client.return_value = client
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            for route, resource in (
                (f"/v1/sites/{site_ref}/topology/snapshot-summary",
                 "site_topology_snapshot_summary"),
                (f"/v1/sites/{site_ref}/gateway-qos/service-profiles/summary",
                 "site_gateway_qos_service_profiles_summary"),
            ):
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], resource)
                self.assertNotIn("private", json.dumps(response))
                rpc = {"jsonrpc": "2.0", "id": 164, "method": "tools/call",
                       "params": {"name": f"omada_{resource}",
                                  "arguments": {"site_ref": site_ref}}}
                status, mcp = self.request_post("/mcp", rpc, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(mcp["result"]["structuredContent"]["resource"], resource)
                self.assertNotIn("private", json.dumps(mcp))
        self.assertEqual(calls, [
            ("GET", "/openapi/v2/ctrl/sites/site_1/topology"),
            ("GET", "/openapi/v2/ctrl/sites/site_1/topology"),
            ("GET", "/openapi/v1/ctrl/sites/site_1/profiles/service-type?page=1&pageSize=1000"),
            ("GET", "/openapi/v1/ctrl/sites/site_1/profiles/service-type?page=1&pageSize=1000"),
        ])

    def test_http_and_mcp_topology_vlan_summary_omits_vlan_values(self) -> None:
        site_ref = "b" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site_1"
        calls = []
        def upstream(method, path, **kwargs):
            calls.append((method, path))
            return {"result": {"splitNetworks": [
                {"id": "hidden-network", "name": "Office LAN", "vlanId": 14,
                 "defaultNetwork": True, "configuring": False},
                {"id": "another-network", "name": "Guest LAN", "vlanId": 14,
                 "defaultNetwork": False, "configuring": True},
                {"name": "Incomplete LAN", "defaultNetwork": False, "configuring": False},
            ]}}
        main._openapi_client.return_value = client
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=upstream):
            route = f"/v1/sites/{site_ref}/topology/vlan-summary"
            status, response = self.request(route, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["resource"], "site_topology_vlan_summary")
            self.assertIsNone(response["data"]["distinct_vlan_count"])
            self.assertEqual(response["data"]["missing_vlan_id_count"], 1)
            for private_value in ("hidden-network", "another-network", "Office LAN",
                                  "Guest LAN", "Incomplete LAN", "14"):
                self.assertNotIn(private_value, json.dumps(response))
            rpc = {"jsonrpc": "2.0", "id": 164, "method": "tools/call",
                   "params": {"name": "omada_site_topology_vlan_summary",
                              "arguments": {"site_ref": site_ref}}}
            status, mcp = self.request_post("/mcp", rpc, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(mcp["result"]["structuredContent"]["resource"],
                             "site_topology_vlan_summary")
            self.assertNotIn("Office LAN", json.dumps(mcp))
            self.assertEqual(calls, [
                ("GET", "/openapi/v2/ctrl/sites/site_1/topology/available-vlans"),
                ("GET", "/openapi/v2/ctrl/sites/site_1/topology/available-vlans"),
            ])

    def test_switch_port_tags_http_and_mcp_are_site_bound_reads(self) -> None:
        site_ref = "a" * 24
        status, body = self.request(f"/v1/sites/{site_ref}/switch-port-tags", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_port_tags")
        self.assertEqual(self.fake.calls[-1], ("switch_port_tags", site_ref))

        rpc = {"jsonrpc": "2.0", "id": 36, "method": "tools/call",
               "params": {"name": "omada_switch_port_tags",
                          "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        result = response["result"]["structuredContent"]
        self.assertEqual(result["resource"], "switch_port_tags")
        self.assertEqual(self.fake.calls[-1], ("switch_port_tags", site_ref))

    def test_mcp_endpoint_authenticates_and_dispatches_registered_read(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "omada_devices",
                "arguments": {"site_ref": "a" * 24},
            },
        }
        status, unauthorized = self.request_post("/mcp", request)
        self.assertEqual(status, 401, repr(unauthorized))
        self.assertEqual(unauthorized["error"], "unauthorized")
        self.assertEqual(self.fake.calls, [])

        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "devices")
        self.assertEqual(self.fake.calls, [("devices", "a" * 24)])

    def test_mcp_dispatches_site_topology_through_fixed_http_route(self) -> None:
        request = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "omada_site_topology",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "site_topology")
        self.assertEqual(self.fake.calls, [("site_topology", "a" * 24)])

    def test_mcp_ssid_network_summary_uses_current_inventories_and_redacts_refs(self) -> None:
        site_ref, ssid_a, ssid_b, network_ref = "a" * 24, "b" * 24, "c" * 24, "d" * 24
        self.fake.list_ssids = lambda ref: self.fake.calls.append(("ssids", ref)) or {
            "status": "ok", "resource": "ssids", "count": 2,
            "items": [{"ssid_ref": ssid_a, "ssid_name": "private-wlan-a"},
                      {"ssid_ref": ssid_b, "ssid_name": "private-wlan-b"}]}
        self.fake.list_networks = lambda ref: self.fake.calls.append(("networks", ref)) or {
            "status": "ok", "resource": "networks", "count": 1,
            "items": [{"network_ref": network_ref, "name": "private-lan"}]}
        self.fake.read_ssid_configuration = lambda ref, ssid: self.fake.calls.append(
            ("ssid_configuration", ssid)) or {
                "status": "ok", "resource": "ssid_configuration", "data": {
                    "ssid_ref": ssid,
                    **({"network_binding_ref": network_ref} if ssid == ssid_a else {})}}
        http_status, http_summary = self.request(
            f"/v1/sites/{site_ref}/ssid-network-summary", self.token)
        self.assertEqual(http_status, 200)
        request = {"jsonrpc": "2.0", "id": 41, "method": "tools/call",
                   "params": {"name": "omada_ssid_network_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        summary = response["result"]["structuredContent"]
        self.assertEqual(summary["resource"], "ssid_network_summary")
        self.assertEqual(summary["matched_count"], 1)
        self.assertEqual(summary["unbound_count"], 1)
        self.assertEqual(summary["stale_binding_count"], 0)
        self.assertEqual(http_summary, summary)
        self.assertNotIn("site_ref", summary)
        self.assertNotIn(ssid_a, repr(summary))
        self.assertNotIn(network_ref, repr(summary))
        self.assertNotIn("private-wlan", repr(summary))
        one_run = [("sites", None), ("ssids", site_ref), ("networks", site_ref),
                   ("devices", site_ref), ("ssid_configuration", ssid_a),
                   ("ssid_configuration", ssid_b),
                   ("site_lan_network_detail_summary", site_ref + ":" + network_ref),
                   ("network_dhcp_server_info", site_ref + ":" + network_ref)]
        self.assertEqual(self.fake.calls, one_run * 2)

    def test_mcp_network_overview_uses_fixed_http_reads_and_inventory_first(self) -> None:
        site_ref, device_ref = "a" * 24, "b" * 24
        self.fake.list_devices = lambda ref: self.fake.calls.append(("devices", ref)) or {
            "status": "ok", "resource": "devices", "site_ref": ref, "count": 1,
            "items": [{"device_ref": device_ref, "device_type": "ap", "name": "hidden"}]}
        self.fake.read_site_overview = lambda ref: self.fake.calls.append(("site_overview", ref)) or {
            "status": "ok", "resource": "site_overview", "site_ref": ref,
            "data": {"health_score": 95}}
        self.fake.list_networks = lambda ref: self.fake.calls.append(("networks", ref)) or {
            "status": "ok", "resource": "networks", "site_ref": ref, "count": 0, "items": []}
        self.fake.list_dhcp_leases = lambda ref: self.fake.calls.append(("dhcp_leases", ref)) or {
            "status": "ok", "resource": "dhcp_leases", "site_ref": ref, "count": 0,
            "summary": {"total": 0, "devices": 0, "clients": 0, "dynamic": 0, "static": 0},
            "items": []}
        self.fake.read_site_topology_network_summary = lambda ref: self.fake.calls.append(("site_topology_network_summary", ref)) or {
            "status": "ok", "resource": "site_topology_network_summary", "site_ref": ref,
            "data": {"unknown_field_count": 0, "split_network_count": 0,
                     "default_network_count": 0, "configuring_network_count": 0,
                     "unknown_network_field_count": 0, "ssid_count": 0,
                     "ssid_vlan_enabled_count": 0, "ssid_configuring_count": 0,
                     "ssid_client_count_sum": 0, "ssid_vlan_id_count": 0,
                     "unknown_ssid_field_count": 0, "partial": False}}

        self.fake.read_site_topology_vlan_summary = lambda ref: self.fake.calls.append(("site_topology_vlan_summary", ref)) or {
            "status": "ok", "resource": "site_topology_vlan_summary", "site_ref": ref,
            "data": {"network_count": 0, "distinct_vlan_count": 0,
                     "default_network_count": 0, "configuring_network_count": 0,
                     "missing_vlan_id_count": 0, "unknown_network_field_count": 0,
                     "unknown_field_count": 0, "partial": False}}
        self.fake.read_dns_cache_settings = lambda ref: self.fake.calls.append(("dns_cache_settings", ref)) or {
            "status": "ok", "resource": "dns_cache_settings", "site_ref": ref, "data": {"enabled": True}}
        self.fake.read_dns_proxy_settings = lambda ref: self.fake.calls.append(("dns_proxy_settings", ref)) or {
            "status": "ok", "resource": "dns_proxy_settings", "site_ref": ref, "data": {"enabled": True}}
        self.fake.list_lan_dns_records = lambda ref: self.fake.calls.append(("lan_dns_records", ref)) or {
            "status": "ok", "resource": "lan_dns_records", "site_ref": ref, "count": 0, "items": []}
        self.fake.list_site_events = lambda ref: self.fake.calls.append(("site_events", ref)) or {
            "status": "ok", "resource": "site_events", "site_ref": ref, "count": 0,
            "window_start_ms": 100, "window_end_ms": 200, "items": []}
        self.fake.list_site_alerts = lambda ref: self.fake.calls.append(("site_alerts", ref)) or {
            "status": "ok", "resource": "site_alerts", "site_ref": ref, "count": 0,
            "window_start_ms": 100, "window_end_ms": 200, "items": []}
        self.fake.read_site_topology = lambda ref: self.fake.calls.append(("site_topology", ref)) or {
            "status": "ok", "resource": "site_topology", "site_ref": ref,
            "nodes": [{"device_ref": device_ref, "device_type": "ap"}], "edges": [],
            "partial": False, "omitted_node_count": 0, "omitted_edge_count": 0}
        request = {"jsonrpc": "2.0", "id": 39, "method": "tools/call",
                   "params": {"name": "omada_network_overview",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        report = response["result"]["structuredContent"]
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["results"]["topology"]["node_count"], 1)
        self.assertEqual(report["results"]["topology_network_summary"]["data"]["ssid_count"], 0)
        self.assertEqual(report["results"]["vlan_summary"]["data"]["distinct_vlan_count"], 0)
        self.assertNotIn("hidden", repr(report))
        self.assertEqual(self.fake.calls, [("devices", site_ref), ("site_overview", site_ref),
                                           ("networks", site_ref), ("dhcp_leases", site_ref),
                                           ("site_topology_network_summary", site_ref),
                                           ("site_topology_vlan_summary", site_ref),
                                           ("dns_cache_settings", site_ref), ("dns_proxy_settings", site_ref),
                                           ("lan_dns_records", site_ref), ("site_events", site_ref),
                                           ("site_alerts", site_ref), ("site_topology", site_ref)])

    def test_mcp_capability_summary_uses_local_catalog_and_redacts_references(self) -> None:
        request = {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                   "params": {"name": "omada_capability_summary",
                              "arguments": {"operation_id": "devices"}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        result = response["result"]["structuredContent"]
        self.assertEqual(result["operation"], "devices")
        self.assertEqual(result["observed_support_states"],
                         {"live_verified_supported": 1})
        self.assertEqual(result["controller_response_evidence_count"], 1)
        self.assertEqual(result["observed_response_shape_states"],
                         {"response_shape_supported": 1})
        self.assertNotIn("private-reference", str(response))
        self.assertEqual(self.fake.calls, [("capability_catalog", None)])

    def test_mcp_exposes_site_client_health_timeline_as_a_fixed_read(self) -> None:
        request = {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                   "params": {"name": "omada_site_client_health_timeline",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_client_health_timeline")
        self.assertEqual(self.fake.calls, [("site_client_health_timeline", "a" * 24)])

    def test_http_and_mcp_expose_experience_index_as_a_fixed_read(self) -> None:
        status, response = self.request(
            "/v1/sites/" + "a" * 24 + "/wifi/optimization/history", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "experience_index")
        request = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                   "params": {"name": "omada_experience_index",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "experience_index")
        self.assertEqual(self.fake.calls, [("experience_index", "a" * 24)] * 2)

    def test_http_and_mcp_expose_rf_planning_status_as_a_fixed_read(self) -> None:
        status, response = self.request(
            "/v1/sites/" + "a" * 24 + "/wifi/optimization/status", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_planning_result")
        request = {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                   "params": {"name": "omada_rf_planning_result",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["data"]["status"], 1)
        self.assertEqual(self.fake.calls, [("rf_planning_result", "a" * 24)] * 2)

    def test_http_and_mcp_expose_rf_dashboard_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/optimization/dashboard"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_planning_dashboard")
        request = {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                   "params": {"name": "omada_rf_planning_dashboard",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "rf_planning_dashboard")
        self.assertEqual(self.fake.calls, [("rf_planning_dashboard", "a" * 24)] * 2)

    def test_http_and_mcp_expose_rf_planning_detail_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/optimization/detail"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_planning_detail")
        request = {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                   "params": {"name": "omada_rf_planning_detail",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "rf_planning_detail")
        self.assertEqual(self.fake.calls, [("rf_planning_detail", "a" * 24)] * 2)

    def test_http_and_mcp_expose_rf_planning_dashboard_history_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/optimization/dashboard/history"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_planning_dashboard_history")
        request = {"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                   "params": {"name": "omada_rf_planning_dashboard_history",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "rf_planning_dashboard_history")
        self.assertEqual(self.fake.calls, [("rf_planning_dashboard_history", "a" * 24)] * 2)

    def test_http_and_mcp_expose_rf_planning_dashboard_current_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/optimization/dashboard/current"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_planning_dashboard_current")
        request = {"jsonrpc": "2.0", "id": 14, "method": "tools/call",
                   "params": {"name": "omada_rf_planning_dashboard_current",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "rf_planning_dashboard_current")
        self.assertEqual(self.fake.calls, [("rf_planning_dashboard_current", "a" * 24)] * 2)

    def test_http_and_mcp_expose_rf_excluded_aps_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/optimization/excluded-aps"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_excluded_aps")
        request = {"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                   "params": {"name": "omada_rf_excluded_aps",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "rf_excluded_aps")
        self.assertEqual(self.fake.calls, [("rf_excluded_aps", "a" * 24)] * 2)

    def test_http_and_mcp_expose_rf_deploy_history_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/optimization/deployment-history"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_deploy_history")
        request = {"jsonrpc": "2.0", "id": 15, "method": "tools/call",
                   "params": {"name": "omada_rf_deploy_history",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "rf_deploy_history")
        self.assertEqual(self.fake.calls, [("rf_deploy_history", "a" * 24)] * 2)

    def test_http_and_mcp_expose_rf_planning_history_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/optimization/history/records"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_planning_history")
        request = {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                   "params": {"name": "omada_rf_planning_history",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "rf_planning_history")
        self.assertEqual(self.fake.calls, [("rf_planning_history", "a" * 24)] * 2)

    def test_http_and_mcp_expose_history_detail_with_an_opaque_reference(self) -> None:
        history_ref = "b" * 24
        path = ("/v1/sites/" + "a" * 24 + "/wifi/optimization/history/records/" + history_ref)
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_planning_history_detail")
        request = {"jsonrpc": "2.0", "id": 16, "method": "tools/call",
                   "params": {"name": "omada_rf_planning_history_detail",
                              "arguments": {"site_ref": "a" * 24, "history_ref": history_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "rf_planning_history_detail")
        self.assertEqual(self.fake.calls,
                         [("rf_planning_history_detail", "a" * 24 + ":" + history_ref)] * 2)

    def test_http_and_mcp_expose_site_reboot_schedule_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/reboot-schedule-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_reboot_schedule_summary")
        request = {"jsonrpc": "2.0", "id": 141, "method": "tools/call",
                   "params": {"name": "omada_site_reboot_schedule_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_reboot_schedule_summary")
        self.assertEqual(self.fake.calls,
                         [("site_reboot_schedule_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wifi_summary_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/summary"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_wifi_summary")
        self.assertEqual(response["data"]["channelUtilization"], 34)
        request = {"jsonrpc": "2.0", "id": 18, "method": "tools/call",
                   "params": {"name": "omada_site_wifi_summary",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_wifi_summary")
        self.assertEqual(self.fake.calls, [("site_wifi_summary", "a" * 24)] * 2)

    def test_http_and_mcp_expose_site_6ghz_presence_as_a_fixed_read(self) -> None:
        path = f"/v1/sites/{'a' * 24}/wifi/6ghz-ap-presence"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_6ghz_ap_presence")
        self.assertIs(response["data"]["has_6ghz_ap"], True)
        request = {"jsonrpc": "2.0", "id": 82, "method": "tools/call",
                   "params": {"name": "omada_site_6ghz_ap_presence",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertIs(response["result"]["structuredContent"]["data"]["has_6ghz_ap"], True)
        self.assertEqual(self.fake.calls, [("site_6ghz_ap_presence", "a" * 24)] * 2)

    def test_http_and_mcp_expose_saved_rogue_ap_summary(self) -> None:
        path = f"/v1/sites/{'a' * 24}/wifi/rogue-ap-results"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_rogue_ap_results")
        self.assertEqual(response["data_age"], "unknown_stored_scan")
        request = {"jsonrpc": "2.0", "id": 86, "method": "tools/call",
                   "params": {"name": "omada_site_rogue_ap_results",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_rogue_ap_results")
        self.assertEqual(self.fake.calls, [("site_rogue_ap_results", "a" * 24)] * 2)

    def test_http_and_mcp_expose_redacted_wids_summary(self) -> None:
        path = f"/v1/sites/{'a' * 24}/wifi/wids-summary"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_wids_summary")
        request = {"jsonrpc": "2.0", "id": 87, "method": "tools/call",
                   "params": {"name": "omada_site_wids_summary",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_wids_summary")
        self.assertEqual(self.fake.calls, [("site_wids_summary", "a" * 24)] * 2)

    def test_http_and_mcp_expose_redacted_wids_blacklist_summary(self) -> None:
        path = f"/v1/sites/{'a' * 24}/wifi/wids-blacklist-summary"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_wids_blacklist_summary")
        request = {"jsonrpc": "2.0", "id": 88, "method": "tools/call",
                   "params": {"name": "omada_site_wids_blacklist_summary",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_wids_blacklist_summary")
        self.assertEqual(self.fake.calls,
                         [("site_wids_blacklist_summary", "a" * 24)] * 2)

    def test_http_and_mcp_expose_existing_ap_scan_status_as_a_fixed_read(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/scan-status"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "scan_status")
        request = {"jsonrpc": "2.0", "id": 19, "method": "tools/call",
                   "params": {"name": "omada_ap_scan_status",
                              "arguments": {"site_ref": "a" * 24, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "scan_status")
        self.assertEqual(self.fake.calls,
                         [("scan_status", "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_redacted_ap_wifi_neighbors(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/wifi-neighbors"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_wifi_neighbors")
        request = {"jsonrpc": "2.0", "id": 20, "method": "tools/call",
                   "params": {"name": "omada_ap_wifi_interference",
                              "arguments": {"site_ref": "a" * 24, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "ap_wifi_neighbors")
        self.assertEqual(self.fake.calls,
                         [("ap_wifi_neighbors", "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_existing_ap_speed_test_results_as_a_read(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/speed-test-results"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_speed_test_results")
        request = {"jsonrpc": "2.0", "id": 21, "method": "tools/call",
                   "params": {"name": "omada_ap_speed_test_results",
                              "arguments": {"site_ref": "a" * 24, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "ap_speed_test_results")
        self.assertEqual(self.fake.calls,
                         [("ap_speed_test_results", "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_ap_ssid_override_audit_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/aps/{AP_REF}/ssid-override-audit-summary"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_ssid_override_audit_summary")
        rpc = {"jsonrpc": "2.0", "id": 241, "method": "tools/call",
               "params": {"name": "omada_ap_ssid_override_audit_summary",
                          "arguments": {"site_ref": site_ref, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "ap_ssid_override_audit_summary")
        self.assertEqual(self.fake.calls,
                         [("ap_ssid_override_audit_summary", site_ref + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_ap_wired_downlink_read(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/wired-downlink"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_wired_downlink")
        request = {"jsonrpc": "2.0", "id": 23, "method": "tools/call",
                   "params": {"name": "omada_ap_wired_downlink",
                              "arguments": {"site_ref": "a" * 24, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "ap_wired_downlink")
        self.assertEqual(self.fake.calls,
                         [("ap_wired_downlink", "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_ap_port_summary(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/ports"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_ports")
        request = {"jsonrpc": "2.0", "id": 34, "method": "tools/call",
                   "params": {"name": "omada_ap_ports",
                              "arguments": {"site_ref": "a" * 24, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "ap_ports")
        self.assertEqual(self.fake.calls,
                         [("ap_ports", "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_ap_lldp_configuration_read(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/lldp-config"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_lldp_config")
        self.assertEqual(response["data"]["setting"], "site_default")
        request = {"jsonrpc": "2.0", "id": 72, "method": "tools/call",
                   "params": {"name": "omada_ap_lldp_config",
                              "arguments": {"site_ref": "a" * 24, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "ap_lldp_config")
        self.assertEqual(self.fake.calls,
                         [("ap_lldp_config", "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_ap_lan_traffic_read(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/lan-traffic"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_lan_traffic")
        request = {"jsonrpc": "2.0", "id": 32, "method": "tools/call",
                   "params": {"name": "omada_ap_lan_traffic",
                              "arguments": {"site_ref": "a" * 24,
                                            "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "ap_lan_traffic")
        self.assertEqual(self.fake.calls,
                         [("ap_lan_traffic", "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_ap_afc_operating_status_read(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/afc/status"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_afc_status")
        request = {"jsonrpc": "2.0", "id": 33, "method": "tools/call",
                   "params": {"name": "omada_ap_afc_status",
                              "arguments": {"site_ref": "a" * 24,
                                            "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "ap_afc_status")
        self.assertEqual(self.fake.calls,
                         [("ap_afc_status", "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_redacted_ap_configuration_reads(self) -> None:
        operations = (
            ("ap_channel_limit", "channel-limit", "read_ap_channel_limit"),
            ("ap_ofdma", "ofdma", "read_ap_ofdma"),
            ("ap_qos", "qos", "read_ap_qos"),
            ("ap_lag", "lag", "read_ap_lag"),
            ("ap_load_balance", "load-balance", "read_ap_load_balance"),
            ("ap_antenna", "antenna", "read_ap_antenna"),
            ("ap_antenna_gain", "antenna-gain", "read_ap_antenna_gain"),
            ("ap_power_saving", "power-saving", "read_ap_power_saving"),
            ("ap_vlan", "vlan", "read_ap_vlan"),
            ("ap_port_vlans", "port-vlans", "read_ap_port_vlans"),
            ("ap_bridge_config", "bridge-config", "read_ap_bridge_config"),
            ("ap_mesh_candidates", "mesh/candidates", "read_ap_mesh_candidates"),
            ("ap_general_config", "general-config", "read_ap_general_config"),
            ("ap_ip_setting", "ip-setting", "read_ap_ip_setting"),
            ("ap_ipv6_setting", "ipv6-setting", "read_ap_ipv6_setting"),
            ("ap_p2p_info", "p2p-info", "read_ap_p2p_info"),
            ("ap_l3_access", "l3-access", "read_ap_l3_access"),
            ("ap_paring_window", "paring-window-result", "read_ap_paring_window"),
            ("ap_lag_config", "lag-config", "read_ap_lag_config"),
        )
        for operation_id, path_part, method in operations:
            with self.subTest(operation=operation_id):
                def read(site_ref, device_ref, operation_id=operation_id):
                    self.fake.calls.append((operation_id, site_ref + ":" + device_ref))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": site_ref, "device_ref": device_ref,
                            "data": {}, "partial": False}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/{path_part}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 34, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": "a" * 24,
                                                    "device_ref": AP_REF}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                self.assertEqual(self.fake.calls[-2:],
                                 [(operation_id, "a" * 24 + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_read_only_site_settings(self) -> None:
        operations = (
            ("band_steering", "wifi/band-steering", "read_band_steering"),
            ("rrm_settings", "wifi/optimization", "read_rrm_settings"),
            ("roaming_settings", "wifi/roaming", "read_roaming_settings"),
            ("site_led", "led", "read_site_led"),
            ("site_lldp", "lldp", "read_site_lldp"),
            ("site_dpi", "application-control", "read_site_dpi_logging"),
            ("gateway_voip", "qos/gateway/voip-prioritization", "read_gateway_voip"),
            ("gateway_tag_qos", "qos/gateway/tag-outbound-traffic", "read_gateway_tag_qos"),
        )
        for operation_id, path_part, method in operations:
            with self.subTest(operation=operation_id):
                def read(site_ref, operation_id=operation_id):
                    self.fake.calls.append((operation_id, site_ref))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": site_ref, "data": {}, "partial": False}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{'a' * 24}/{path_part}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 35, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": "a" * 24}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                self.assertEqual(self.fake.calls[-2:],
                                 [(operation_id, "a" * 24)] * 2)

    def test_http_and_mcp_expose_site_channel_and_rrm_reads(self) -> None:
        operations = (
            ("site_channel_limit", "wifi/channel-limit", "read_site_channel_limit"),
            ("rrm_incompatible", "wifi/rrm-incompatible", "read_rrm_incompatible"),
        )
        site_ref = "a" * 24
        for operation_id, suffix, method in operations:
            with self.subTest(operation=operation_id):
                def read(ref, operation_id=operation_id):
                    self.fake.calls.append((operation_id, ref))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": ref, "data": {}, "count": 0, "items": []}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{site_ref}/{suffix}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 42, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": site_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                self.assertEqual(self.fake.calls[-2:], [(operation_id, site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_acl_reads(self) -> None:
        operations = (
            ("gateway_firewall_rules", "gateway-acls", "list_gateway_firewall_rules"),
            ("switch_firewall_rules", "switch-acls", "list_switch_firewall_rules"),
            ("ap_firewall_rules", "ap-acls", "list_ap_firewall_rules"),
        )
        site_ref = "a" * 24
        for operation_id, suffix, method in operations:
            with self.subTest(operation=operation_id):
                def read(ref, operation_id=operation_id):
                    self.fake.calls.append((operation_id, ref))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": ref, "count": 0, "items": []}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{site_ref}/firewall/{suffix}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 35, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": site_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                self.assertEqual(self.fake.calls[-2:],
                                 [(operation_id, site_ref)] * 2)

    def test_http_and_mcp_expose_bounded_site_logs(self) -> None:
        operations = (
            ("site_events", "events", "list_site_events"),
            ("site_alerts", "alerts", "list_site_alerts"),
        )
        site_ref = "a" * 24
        for operation_id, suffix, method in operations:
            with self.subTest(operation=operation_id):
                def read(ref, operation_id=operation_id):
                    self.fake.calls.append((operation_id, ref))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": ref, "count": 0, "items": [],
                            "window_start_ms": 1, "window_end_ms": 2}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{site_ref}/{suffix}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 37, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": site_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                self.assertEqual(self.fake.calls[-2:],
                                 [(operation_id, site_ref)] * 2)

    def test_site_events_accepts_optional_window_over_http_and_mcp(self) -> None:
        from urllib.parse import urlencode

        site_ref = "a" * 24
        start_ms, end_ms = 1_795_000_000_000 - 60_000, 1_795_000_000_000
        calls = []

        def read(ref, start=None, end=None):
            calls.append((ref, start, end))
            return {"status": "ok", "resource": "site_events", "site_ref": ref,
                    "count": 0, "items": [], "window_start_ms": start,
                    "window_end_ms": end}

        self.fake.list_site_events = read
        route = f"/v1/sites/{site_ref}/events?" + urlencode(
            {"start_ms": str(start_ms), "end_ms": str(end_ms)})
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["window_start_ms"], start_ms)
        self.assertEqual(calls[-1], (site_ref, start_ms, end_ms))

        request = {"jsonrpc": "2.0", "id": 41, "method": "tools/call",
                   "params": {"name": "omada_site_events",
                              "arguments": {"site_ref": site_ref,
                                            "start_ms": start_ms, "end_ms": end_ms}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["window_end_ms"], end_ms)
        self.assertEqual(calls[-1], (site_ref, start_ms, end_ms))

        equal_route = f"/v1/sites/{site_ref}/events?" + urlencode(
            {"start_ms": str(end_ms), "end_ms": str(end_ms)})
        status, response = self.request(equal_route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["window_start_ms"], end_ms)
        self.assertEqual(response["window_end_ms"], end_ms)
        self.assertEqual(calls[-1], (site_ref, end_ms, end_ms))

        equal_request = {"jsonrpc": "2.0", "id": 42, "method": "tools/call",
                         "params": {"name": "omada_site_events",
                                    "arguments": {"site_ref": site_ref,
                                                  "start_ms": end_ms, "end_ms": end_ms}}}
        status, response = self.request_post("/mcp", equal_request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["window_start_ms"], end_ms)
        self.assertEqual(response["result"]["structuredContent"]["window_end_ms"], end_ms)
        self.assertEqual(calls[-1], (site_ref, end_ms, end_ms))

        invalid_route = f"/v1/sites/{site_ref}/events?" + urlencode(
            {"start_ms": str(end_ms), "end_ms": str(start_ms)})
        previous_call_count = len(calls)
        status, response = self.request(invalid_route, self.token)
        self.assertEqual(status, 400)
        self.assertEqual(len(calls), previous_call_count)

    def test_site_events_paged_read_dispatches_explicit_page_over_http_and_mcp(self) -> None:
        import time
        from urllib.parse import urlencode

        site_ref = "a" * 24
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - 30 * 86_400_000
        calls = []

        def read(ref, start=None, end=None, **page):
            calls.append((ref, start, end, page))
            return {"status": "ok", "resource": "site_events", "site_ref": ref,
                    "count": 1, "total_count": 6056, "partial": True,
                    "window_start_ms": start, "window_end_ms": end,
                    "items": [{"event_ref": "b" * 24, "time_ms": end,
                               "module": "device"}],
                    "pagination": {"page_number": page["page_number"],
                                   "page_size": page["page_size"],
                                   "next_page": page["page_number"] + 1,
                                   "page_limit": 64, "page_limit_reached": False}}

        self.fake.list_site_events = read
        arguments = {"start_ms": start_ms, "end_ms": end_ms,
                     "page_number": 1, "page_size": 200}
        route = f"/v1/sites/{site_ref}/events?" + urlencode(arguments)
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["pagination"]["next_page"], 2)
        self.assertEqual(calls[-1], (site_ref, start_ms, end_ms,
                                     {"page_number": 1, "page_size": 200}))

        request = {"jsonrpc": "2.0", "id": 48, "method": "tools/call",
                   "params": {"name": "omada_site_events", "arguments": {
                       "site_ref": site_ref, **arguments}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["pagination"]["next_page"], 2)
        self.assertEqual(calls[-1], (site_ref, start_ms, end_ms,
                                     {"page_number": 1, "page_size": 200}))

        continuation = {**arguments, "page_number": 2, "expected_total": 6056}
        status, response = self.request(
            f"/v1/sites/{site_ref}/events?" + urlencode(continuation), self.token)
        self.assertEqual(status, 200)
        self.assertEqual(calls[-1][3], {
            "page_number": 2, "page_size": 200, "expected_total": 6056})

        invalid = {**arguments, "page_number": 1, "expected_total": 6056}
        previous = len(calls)
        status, response = self.request(
            f"/v1/sites/{site_ref}/events?" + urlencode(invalid), self.token)
        self.assertEqual(status, 400)
        self.assertEqual(len(calls), previous)

        for invalid_page in (
                {**arguments, "page_number": 65},
                {**arguments, "page_number": 2},
                {**arguments, "start_ms": start_ms - 1},
                {**arguments, "start_ms": end_ms}):
            previous = len(calls)
            status, _ = self.request(
                f"/v1/sites/{site_ref}/events?" + urlencode(invalid_page), self.token)
            self.assertEqual(status, 400)
            self.assertEqual(len(calls), previous)

        invalid_mcp = {"jsonrpc": "2.0", "id": 49, "method": "tools/call",
                       "params": {"name": "omada_site_events", "arguments": {
                           "site_ref": site_ref, **arguments, "page_number": 2}}}
        previous = len(calls)
        status, response = self.request_post("/mcp", invalid_mcp, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(len(calls), previous)

    def test_site_events_6056_fixture_completes_through_http_and_mcp_pages(self) -> None:
        import json
        import time
        from urllib.parse import urlencode
        from app.openapi import OmadaOpenApiClient, OpenApiConfig

        site_ref = "a" * 24
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - 30 * 86_400_000
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="c" * 64, page_size=200))
        client._site_ids_by_ref[site_ref] = "site_1"
        upstream_pages = []

        def request(method, path, **kwargs):
            self.assertEqual(method, "GET")
            query = dict(part.split("=", 1) for part in path.split("?", 1)[1].split("&"))
            page, size = int(query["page"]), int(query["pageSize"])
            self.assertEqual((int(query["filters.timeStart"]), int(query["filters.timeEnd"])),
                             (start_ms, end_ms))
            upstream_pages.append(page)
            rows = [{"id": f"event-{index}", "module": "Device", "time": end_ms,
                     "content": "private event text"}
                    for index in range((page - 1) * size, min(page * size, 6056))]
            return {"result": {"totalRows": 6056, "currentPage": page,
                               "currentSize": len(rows), "data": rows}}

        page_refs = {"http": set(), "mcp": set()}
        with patch.object(main, "_openapi_client", return_value=client), \
                patch.object(client, "_access_token", return_value="synthetic-token"), \
                patch.object(client, "_request_json", side_effect=request):
            for transport in ("http", "mcp"):
                for page in range(1, 32):
                    arguments = {"site_ref": site_ref, "start_ms": start_ms,
                                 "end_ms": end_ms, "page_number": page,
                                 "page_size": 200}
                    if page > 1:
                        arguments["expected_total"] = 6056
                    before = len(upstream_pages)
                    if transport == "http":
                        query = {key: value for key, value in arguments.items()
                                 if key != "site_ref"}
                        status, result = self.request(
                            f"/v1/sites/{site_ref}/events?" + urlencode(query), self.token)
                        self.assertEqual(status, 200)
                    else:
                        request_body = {"jsonrpc": "2.0", "id": page,
                                        "method": "tools/call",
                                        "params": {"name": "omada_site_events",
                                                   "arguments": arguments}}
                        status, response = self.request_post("/mcp", request_body, self.token)
                        self.assertEqual(status, 200)
                        result = response["result"]["structuredContent"]
                    self.assertEqual(len(upstream_pages) - before, 1)
                    self.assertEqual(result["count"], 56 if page == 31 else 200)
                    self.assertEqual(result["total_count"], 6056)
                    self.assertEqual(result["partial"], result["count"] < 6056)
                    self.assertEqual(result["pagination"]["next_page"],
                                     page + 1 if page < 31 else None)
                    self.assertNotIn("private event text", json.dumps(result))
                    refs = {item["event_ref"] for item in result["items"]}
                    self.assertEqual(len(refs), result["count"])
                    self.assertFalse(page_refs[transport].intersection(refs))
                    page_refs[transport].update(refs)

        self.assertEqual(upstream_pages, list(range(1, 32)) * 2)
        self.assertEqual(len(page_refs["http"]), 6056)
        self.assertEqual(len(page_refs["mcp"]), 6056)

    def test_http_and_mcp_expose_identity_and_time_window_reads(self) -> None:
        from urllib.parse import urlencode

        site_ref = "a" * 24
        start_ms, end_ms = 1_760_000_000_000, 1_760_000_000_500

        def identity(ref, client_name, ssid_name):
            self.fake.calls.append(("site_client_identity_match", ref,
                                    client_name, ssid_name))
            return {"status": "ok", "resource": "site_client_identity_match",
                    "match_state": "unmatched", "match_count": 0,
                    "client_ref": None,
                    "search_coverage": {"inventory_row_count": 0,
                        "complete_identity_row_count": 0,
                        "incomplete_identity_row_count": 0,
                        "potential_match_count": 0, "complete": True,
                        "fields": {field: {"present_count": 0, "missing_count": 0}
                                   for field in ("name", "hostName", "model", "ssid", "wireless")}},
                    "partial": False}

        self.fake.resolve_site_client_identity = identity
        route = f"/v1/sites/{site_ref}/clients/identity-match?" + urlencode(
            {"client_name": "Sample client", "ssid_name": "Lab WLAN"})
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["match_state"], "unmatched")
        self.assertTrue(response["search_coverage"]["complete"])

        def events(ref, kind, start, end):
            self.fake.calls.append(("site_events_window_summary", ref, kind, start, end))
            return {"status": "ok", "resource": "site_events_window_summary",
                    "window_start_ms": start, "window_end_ms": end,
                    "returned_count": 0, "total_count": 0,
                    "partial": False, "module_counts": {}}

        self.fake.read_site_log_window_summary = events
        route = f"/v1/sites/{site_ref}/events/window?" + urlencode(
            {"start_ms": str(start_ms), "end_ms": str(end_ms)})
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertFalse(response["partial"])
        request = {"jsonrpc": "2.0", "id": 39, "method": "tools/call",
                   "params": {"name": "omada_site_events_window_summary",
                              "arguments": {"site_ref": site_ref,
                                            "start_ms": start_ms,
                                            "end_ms": end_ms}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_events_window_summary")

        def local_events(ref, kind, start_local, end_local, time_zone):
            self.fake.calls.append(("site_events_window_local", ref, kind,
                                   start_local, end_local, time_zone))
            return {"status": "ok", "resource": f"site_{kind}_window_summary",
                    "time_zone": time_zone, "window_start_local": start_local,
                    "window_end_local": end_local, "partial": False}

        self.fake.read_site_log_local_window_summary = local_events
        local_args = {"start_local": "2026-11-18T09:20",
                      "end_local": "2026-11-18T09:30", "time_zone": "Europe/Berlin"}
        status, response = self.request(
            f"/v1/sites/{site_ref}/alerts/window?" + urlencode(local_args), self.token)
        self.assertEqual(status, 200)
        self.assertEqual(self.fake.calls[-1], (
            "site_events_window_local", site_ref, "alerts", "2026-11-18T09:20",
            "2026-11-18T09:30", "Europe/Berlin"))
        request = {"jsonrpc": "2.0", "id": 40, "method": "tools/call",
                   "params": {"name": "omada_site_alerts_window_summary",
                              "arguments": {"site_ref": site_ref, **local_args}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["time_zone"],
                         "Europe/Berlin")
        invalid_args = {"start_local": "2026-10-25T02:30",
                        "end_local": "2026-10-25T03:00",
                        "time_zone": "Europe/Berlin"}
        status, response = self.request(
            f"/v1/sites/{site_ref}/events/window?" + urlencode(invalid_args), self.token)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.fake.calls[-1][0], "site_events_window_local")

    def test_site_and_controller_audit_window_http_and_mcp(self) -> None:
        from urllib.parse import urlencode
        site_ref = "a" * 24
        start_ms, end_ms = 1_760_000_000_000, 1_760_000_000_500
        calls = []

        def site_audit(ref, start, end):
            calls.append(("site", ref, start, end))
            return {"status": "ok", "resource": "site_audit_log_window_summary",
                    "window_start_ms": start, "window_end_ms": end,
                    "entries": [], "partial": False}

        def controller_audit(start, end):
            calls.append(("controller", start, end))
            return {"status": "ok", "resource": "controller_audit_log_window_summary",
                    "window_start_ms": start, "window_end_ms": end,
                    "entries": [], "partial": False}

        self.fake.read_site_audit_log_window_summary = site_audit
        self.fake.read_controller_audit_log_window_summary = controller_audit
        query = urlencode({"start_ms": start_ms, "end_ms": end_ms})
        status, response = self.request(
            f"/v1/sites/{site_ref}/audit-logs/window?{query}", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_audit_log_window_summary")
        status, response = self.request(f"/v1/controller/audit-logs/window?{query}", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(calls, [("site", site_ref, start_ms, end_ms),
                                 ("controller", start_ms, end_ms)])

        for request_id, name, arguments in (
            (81, "omada_site_audit_log_window_summary",
             {"site_ref": site_ref, "start_ms": start_ms, "end_ms": end_ms}),
            (82, "omada_controller_audit_log_window_summary",
             {"start_ms": start_ms, "end_ms": end_ms}),
        ):
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}}, self.token)
            self.assertEqual(status, 200)
            self.assertFalse(response["result"]["isError"])
            self.assertEqual(response["result"]["structuredContent"]["resource"],
                             name.removeprefix("omada_"))
        self.assertEqual(len(calls), 4)

    def test_wan_port_availability_http_and_mcp_require_documented_function(self) -> None:
        site_ref = "a" * 24
        calls = []

        def availability(ref, function):
            calls.append((ref, function))
            return {"status": "ok", "resource": "site_wan_port_availability_summary",
                    "site_ref": ref, "function": function, "listed_port_count": 2,
                    "qos_configured_count": 1, "partial": False}

        self.fake.read_site_wan_port_availability_summary = availability
        status, response = self.request(
            f"/v1/sites/{site_ref}/wan-ports/availability-summary?function=7", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["function"], 7)
        status, response = self.request(
            f"/v1/sites/{site_ref}/wan-ports/availability-summary?function=16", self.token)
        self.assertNotEqual(status, 200)
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 92, "method": "tools/call",
            "params": {"name": "omada_site_wan_port_availability_summary",
                       "arguments": {"site_ref": site_ref, "function": 7}}}, self.token)
        self.assertEqual(status, 200)
        self.assertIn("result", response, (status, response, calls))
        self.assertFalse(response["result"]["isError"], (response, calls))
        self.assertEqual(calls, [(site_ref, 7), (site_ref, 7)])
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 93, "method": "tools/call",
            "params": {"name": "omada_site_wan_port_availability_summary",
                       "arguments": {"site_ref": site_ref, "function": 16}}}, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["error"]["message"], "arguments_invalid")

    def test_controller_event_and_alert_windows_accept_http_and_mcp(self) -> None:
        from urllib.parse import urlencode
        start_ms, end_ms = 1_760_000_000_000, 1_760_000_000_500
        calls = []

        def summary(kind, start, end):
            calls.append((kind, start, end))
            return {"status": "ok", "resource": f"controller_{kind}_window_summary",
                    "scope": "configured_controller", "window_start_ms": start,
                    "window_end_ms": end, "returned_count": 0, "total_count": 0,
                    "partial": False}

        self.fake.read_controller_log_window_summary = summary
        query = urlencode({"start_ms": start_ms, "end_ms": end_ms})
        for kind in ("events", "alerts"):
            status, response = self.request(f"/v1/controller/{kind}/window?{query}", self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["resource"], f"controller_{kind}_window_summary")
        for index, kind in enumerate(("events", "alerts"), start=91):
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": index, "method": "tools/call",
                "params": {"name": f"omada_controller_{kind}_window_summary",
                           "arguments": {"start_ms": start_ms, "end_ms": end_ms}}}, self.token)
            self.assertEqual(status, 200)
            self.assertFalse(response["result"]["isError"])
            self.assertEqual(response["result"]["structuredContent"]["scope"],
                             "configured_controller")
        self.assertEqual(calls, [(kind, start_ms, end_ms)
                                 for _ in range(2) for kind in ("events", "alerts")])

    def test_client_outage_timeline_accepts_local_window_over_http_and_mcp(self) -> None:
        site_ref, client_ref = "a" * 24, "b" * 24
        seen = []

        def timeline(site, client, start_ms, end_ms):
            seen.append((site, client, start_ms, end_ms))
            return {"status": "ok", "resource": "client_outage_timeline",
                    "window_start_ms": start_ms, "window_end_ms": end_ms,
                    "client_events": [], "roaming_events": [], "health_scores": [],
                    "sources": {}, "partial": False}

        self.fake.read_client_outage_timeline = timeline
        arguments = {"start_local": "2026-09-14T10:00",
                     "end_local": "2026-09-14T10:10", "time_zone": "Europe/Berlin"}
        status, response = self.request(
            f"/v1/sites/{site_ref}/clients/{client_ref}/outage-timeline?" +
            urlencode(arguments), self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "client_outage_timeline")
        self.assertEqual(seen[-1][:2], (site_ref, client_ref))
        self.assertEqual(response["time_zone"], "Europe/Berlin")

        request = {"jsonrpc": "2.0", "id": 41, "method": "tools/call",
                   "params": {"name": "omada_client_outage_timeline",
                              "arguments": {"site_ref": site_ref,
                                            "client_ref": client_ref, **arguments}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "client_outage_timeline")

    def test_selected_site_capability_comparison_is_available_over_http_and_mcp(self) -> None:
        site_refs = ["a" * 24, "b" * 24]
        seen = []

        def comparison(refs):
            seen.append(refs)
            return {"status": "ok", "resource": "site_capability_comparison",
                    "site_refs": refs, "sites": [], "feature_columns": [],
                    "feature_values": [], "partial": False}

        self.fake.read_site_capability_comparison = comparison
        query = urlencode([("site_ref", ref) for ref in site_refs])
        status, response = self.request(
            "/v1/sites/capability-comparison?" + query, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_capability_comparison")

        request = {"jsonrpc": "2.0", "id": 199, "method": "tools/call",
                   "params": {"name": "omada_compare_site_capabilities",
                              "arguments": {"site_refs": site_refs}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_capability_comparison")
        self.assertEqual(seen, [site_refs, site_refs])

        invalid = {"jsonrpc": "2.0", "id": 200, "method": "tools/call",
                   "params": {"name": "omada_compare_site_capabilities",
                              "arguments": {"site_refs": [site_refs[0], site_refs[0]]}}}
        status, invalid_rpc = self.request_post("/mcp", invalid, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(invalid_rpc["error"]["message"], "arguments_invalid")

        status, invalid_http = self.request(
            "/v1/sites/capability-comparison?site_ref=" + site_refs[0], self.token)
        self.assertEqual(status, 400)
        self.assertEqual(invalid_http["error"], "site_refs_invalid")

    def test_bound_change_journal_summary_is_available_over_http_and_mcp(self) -> None:
        summary = {"status": "ok", "resource": "change_journal_summary",
                   "integrity": "validated_at_open", "total_plans": 2,
                   "counts_by_state": {"in_doubt": 1, "verified": 1,
                                       "closed_outcome_unknown": 0},
                   "record_details_included": False}
        journal = type("Journal", (), {"available": True,
                                        "summary": lambda _self: summary})()
        runtime = main.JournalRuntime("ready", journal=journal)
        with patch.object(main, "_JOURNAL_RUNTIME", runtime):
            status, response = self.request("/v1/change-journal/summary", self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response, summary)

            request = {"jsonrpc": "2.0", "id": 201, "method": "tools/call",
                       "params": {"name": "omada_change_journal_summary", "arguments": {}}}
            status, rpc = self.request_post("/mcp", request, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(rpc["result"]["structuredContent"], summary)

        self.assertNotIn("plan_id", json.dumps(response))
        self.assertNotIn("target_refs", json.dumps(response))
        self.assertEqual(self.fake.calls, [])

    def test_change_journal_summary_reports_unconfigured_without_opening_a_path(self) -> None:
        with patch.object(main, "_JOURNAL_RUNTIME", main.JournalRuntime("unconfigured")):
            status, response = self.request("/v1/change-journal/summary", self.token)
        self.assertEqual(status, 503)
        self.assertEqual(response, {"status": "unavailable", "error": "journal_unconfigured"})

    def test_change_journal_summary_never_initializes_and_reads_only_open_journal(self) -> None:
        unopened_dir = os.path.join(self.tempdir.name, "not-opened")
        rpc = {"jsonrpc": "2.0", "id": 202, "method": "tools/call",
               "params": {"name": "omada_change_journal_summary", "arguments": {}}}
        with patch.dict(os.environ, {"OMADA_CHANGE_JOURNAL_DIR": unopened_dir}), \
                patch.object(main, "_JOURNAL_RUNTIME", None), \
                patch.object(main, "_openapi_client", side_effect=AssertionError("client opened")), \
                patch.object(main, "initialize_journal_runtime",
                             side_effect=AssertionError("journal initialized")):
            status, response = self.request("/v1/change-journal/summary", self.token)
            self.assertEqual(status, 503)
            self.assertEqual(response, {"status": "unavailable", "error": "journal_not_open"})

            status, response = self.request_post("/mcp", rpc, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["result"]["structuredContent"],
                             {"status": "unavailable", "error": "journal_not_open"})

        self.assertFalse(os.path.exists(unopened_dir))

        binding = derive_controller_binding(b"k" * 32, "https://controller.example:8043", "test")
        journal = ChangePlanJournal(self.tempdir.name, controller_binding=binding)
        runtime = main.JournalRuntime("ready", journal=journal)
        try:
            journal.record_dispatch_intent(
                operation="radio", plan_id="a" * 48,
                target_refs={"site_ref": "a" * 24, "device_ref": "b" * 24},
                before={"radioSetting2g": {"txPowerLevel": 1}},
                target={"radioSetting2g": {"txPowerLevel": 2}})
            with patch.object(main, "_JOURNAL_RUNTIME", runtime):
                status, response = self.request("/v1/change-journal/summary", self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["total_plans"], 1)
                self.assertEqual(response["counts_by_state"]["in_doubt"], 1)

                status, response = self.request_post("/mcp", rpc, self.token)
                self.assertEqual(status, 200)
                summary = response["result"]["structuredContent"]
                self.assertEqual(summary["total_plans"], 1)
                self.assertEqual(summary["counts_by_state"]["in_doubt"], 1)
        finally:
            runtime.close()

    def test_http_and_mcp_expose_dhcp_and_dns_reads(self) -> None:
        operations = (
            ("dhcp_leases", "dhcp/leases", "list_dhcp_leases"),
            ("dns_cache_settings", "dns/cache", "read_dns_cache_settings"),
            ("dns_proxy_settings", "dns/proxy", "read_dns_proxy_settings"),
            ("lan_dns_records", "dns/records", "list_lan_dns_records"),
        )
        site_ref = "a" * 24
        for operation_id, suffix, method in operations:
            with self.subTest(operation=operation_id):
                def read(ref, operation_id=operation_id):
                    self.fake.calls.append((operation_id, ref))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": ref, "count": 0, "items": [],
                            "partial": False}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{site_ref}/{suffix}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 38, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": site_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                self.assertEqual(self.fake.calls[-2:],
                                 [(operation_id, site_ref)] * 2)

    def test_http_and_mcp_expose_inventory_detail_reads(self) -> None:
        operations = (
            ("device_firmware", f"devices/{'b' * 24}/firmware",
             "read_device_firmware", "device_ref"),
            ("client_detail", f"clients/{'c' * 24}",
             "read_client_detail", "client_ref"),
            ("wlan_groups", "wireless-groups", "list_wlan_groups", None),
            ("ssid_configuration", f"ssids/{'d' * 24}",
             "read_ssid_configuration", "ssid_ref"),
        )
        site_ref = "a" * 24
        for operation_id, suffix, method, resource_key in operations:
            with self.subTest(operation=operation_id):
                def read(ref, target=None, operation_id=operation_id):
                    self.fake.calls.append((operation_id, ref + (":" + target if target else "")))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": ref, "data": {}}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{site_ref}/{suffix}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                arguments = {"site_ref": site_ref}
                if resource_key:
                    value = {"device_ref": "b" * 24, "client_ref": "c" * 24,
                             "ssid_ref": "d" * 24}[resource_key]
                    arguments[resource_key] = value
                request = {"jsonrpc": "2.0", "id": 39, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": arguments}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)

    def test_ssid_preflight_context_survives_http_and_mcp_redacted(self) -> None:
        site_ref, ssid_ref, network_ref = "a" * 24, "d" * 24, "e" * 24
        safe_data = {"ssid_ref": ssid_ref, "security_settings_present": True,
                     "network_binding_ref": network_ref, "ap_group_binding_count": 2}

        def read(site, ssid):
            self.fake.calls.append(("ssid_configuration", site + ":" + ssid))
            return {"status": "ok", "resource": "ssid_configuration",
                    "site_ref": site, "data": safe_data}

        self.fake.read_ssid_configuration = read
        route = f"/v1/sites/{site_ref}/ssids/{ssid_ref}"
        status, http_result = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(http_result["data"], safe_data)

        request = {"jsonrpc": "2.0", "id": 91, "method": "tools/call",
                   "params": {"name": "omada_ssid_configuration",
                              "arguments": {"site_ref": site_ref, "ssid_ref": ssid_ref}}}
        status, mcp_result = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(mcp_result["result"]["structuredContent"]["data"], safe_data)
        serialized = json.dumps({"http": http_result, "mcp": mcp_result})
        for private in ("ssid-name-private", "credential-private", "network-id-private",
                        "ap-group-id-private", "vlan-value-private"):
            self.assertNotIn(private, serialized)

    def test_http_and_mcp_expose_ap_health_and_radio_reads(self) -> None:
        ap_ref = "b" * 24
        site_ref = "a" * 24
        operations = (
            ("ap_radio_config", "radio-config", "read_ap_radio_part", "radio_config"),
            ("ap_health", "health", "read_ap_health", None),
            ("ap_health_timeline", "health/timeline", "read_ap_health_timeline", None),
            ("ap_afc", "afc", "read_ap_afc", None),
            ("ap_radios", "radios", "read_ap_radio_part", "radios"),
            ("ap_channel_load", "channel-load", "read_ap_radio_part", "channel_load"),
            ("ap_rf_scan", "rf-scan", "read_ap_rf_scan", None),
            ("ap_rf_scan_v2", "rf-scan-v2", "read_ap_rf_scan_v2", None),
            ("ap_management_ssid", "management-ssid", "read_ap_management_ssid", None),
            ("ap_snmp_config", "snmp", "read_ap_snmp_config", None),
            ("ap_vlan_v1", "vlan-v1", "read_ap_vlan_v1", None),
            ("ap_wlan_overrides", "wlan-overrides", "read_ap_wlan_overrides", None),
        )
        for operation_id, suffix, method, part in operations:
            with self.subTest(operation=operation_id):
                if method == "read_ap_radio_part":
                    def read(ref, device_ref, part_name, operation_id=operation_id):
                        self.fake.calls.append((operation_id, ref + ":" + device_ref + ":" + part_name))
                        return {"status": "ok", "resource": part_name,
                                "site_ref": ref, "device_ref": device_ref, "data": {}}
                else:
                    def read(ref, device_ref, operation_id=operation_id):
                        self.fake.calls.append((operation_id, ref + ":" + device_ref))
                        return {"status": "ok", "resource": operation_id,
                                "site_ref": ref, "device_ref": device_ref, "data": {}}
                setattr(self.fake, method, read)
                route = f"/v1/sites/{site_ref}/aps/{ap_ref}/{suffix}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                expected_resource = part if method == "read_ap_radio_part" else operation_id
                self.assertEqual(response["resource"], expected_resource)
                request = {"jsonrpc": "2.0", "id": 40, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": site_ref,
                                                    "device_ref": ap_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    expected_resource)
                call_key = site_ref + ":" + ap_ref + (":" + part if part else "")
                self.assertEqual(self.fake.calls[-2:], [(operation_id, call_key)] * 2)

    def test_http_and_mcp_expose_site_ap_retry_drop_summary(self) -> None:
        site_ref = "a" * 24

        def read(ref):
            self.fake.calls.append(("ap_retry_drop", ref))
            return {"status": "ok", "resource": "ap_retry_drop",
                    "site_ref": ref, "data": {}}

        self.fake.read_ap_retry_drop = read
        route = f"/v1/sites/{site_ref}/aps/retry-drop"
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_retry_drop")
        request = {"jsonrpc": "2.0", "id": 41, "method": "tools/call",
                   "params": {"name": "omada_ap_retry_drop",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(
            response["result"]["structuredContent"]["resource"],
            "ap_retry_drop")
        self.assertEqual(self.fake.calls[-2:], [("ap_retry_drop", site_ref)] * 2)

    def test_http_and_mcp_expose_switch_inventory_reads(self) -> None:
        operations = (
            ("switch_ports", "ports", "read_switch_ports"),
            ("switch_port_counters", "ports/counters", "read_switch_port_counters"),
            ("switch_port_poe_info", "ports/poe-info", "read_switch_port_poe_info"),
            ("switch_vlans", "vlans", "read_switch_vlans"),
            ("switch_lldp_neighbors", "lldp-neighbors", "read_switch_lldp_neighbors"),
            ("switch_health", "health", "read_switch_health"),
            ("switch_health_timeline", "health/timeline", "read_switch_health_timeline"),
            ("switch_sdm_usage", "sdm-usage", "read_switch_sdm_usage"),
            ("switch_cable_test_logs", "cable-test/logs", "read_switch_cable_test_logs"),
            ("switch_cable_test_full_results", "cable-test/full-results", "read_switch_cable_test_full_results"),
            ("switch_cable_test_increment_results", "cable-test/increment-results", "read_switch_cable_test_increment_results"),
            ("switch_cable_test_ports", "cable-test/ports", "read_switch_cable_test_ports"),
            ("switch_dhcp_users", "dhcp/users", "list_switch_dhcp_users"),
            ("switch_ospf_neighbors", "ospf-neighbors", "list_switch_ospf_neighbors"),
            ("switch_port_networks", "port-networks", "list_switch_port_networks"),
            ("switch_exist_networks", "exist-networks", "list_switch_exist_networks"),
            ("switch_networks", "networks", "list_switch_networks"),
            ("switch_interfaces", "interfaces", "list_switch_interfaces"),
            ("switch_routing_table", "routing-table", "list_switch_routing_table"),
            ("switch_static_routes", "static-routes", "list_switch_static_routes"),
            ("switch_vrfs", "vrfs", "list_switch_vrfs"),
            ("switch_vlan_interfaces", "vlan-interfaces", "list_switch_vlan_interfaces"),
            ("switch_statistics", "statistics", "read_switch_statistics"),
        )
        switch_ref = "c" * 24
        for operation_id, path_part, method in operations:
            with self.subTest(operation=operation_id):
                def read(site_ref, ref, operation_id=operation_id):
                    self.fake.calls.append((operation_id, site_ref + ":" + ref))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": site_ref, "switch_ref": ref,
                            "data": {}, "partial": False}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{'a' * 24}/switches/{switch_ref}/{path_part}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 36, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": "a" * 24,
                                                    "switch_ref": switch_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                self.assertEqual(self.fake.calls[-2:],
                                 [(operation_id, "a" * 24 + ":" + switch_ref)] * 2)

    def test_http_and_mcp_expose_bounded_switch_port_reads(self) -> None:
        site_ref, switch_ref = "a" * 24, "c" * 24
        operations = (
            ("switch_port_poe_mode", "poe", "read_switch_port_poe_state"),
            ("switch_port_status", "status", "read_switch_port_status"),
        )
        for operation_id, suffix, method in operations:
            with self.subTest(operation=operation_id):
                def read(ref, device_ref, port, operation_id=operation_id):
                    self.fake.calls.append((operation_id, ref + ":" + device_ref + ":" + str(port)))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": ref, "switch_ref": device_ref,
                            "port": port, "data": {}}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{site_ref}/switches/{switch_ref}/ports/24/{suffix}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 43, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": site_ref,
                                                    "switch_ref": switch_ref, "port": 24}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                self.assertEqual(self.fake.calls[-2:],
                                 [(operation_id, site_ref + ":" + switch_ref + ":24")] * 2)

    def test_http_and_mcp_expose_inventory_bound_client_reads(self) -> None:
        operations = (
            ("client_connection_history", "connections", "read_client_connection_history"),
            ("client_history", "history", "read_client_history"),
            ("client_health", "health", "read_client_health"),
            ("client_health_timeline", "health/timeline", "read_client_health_timeline"),
            ("client_timeline_connect", "timeline/connect", "read_client_timeline"),
            ("client_timeline_association", "timeline/association", "read_client_timeline"),
            ("client_timeline_roaming", "timeline/roaming", "read_client_timeline"),
            ("client_timeline_disconnect", "timeline/disconnect", "read_client_timeline"),
        )
        client_ref = "d" * 24
        for operation_id, path_part, method in operations:
            with self.subTest(operation=operation_id):
                timeline_type = path_part.split("/")[-1] if path_part.startswith("timeline/") else None

                def read(site_ref, ref, kind=None, operation_id=operation_id,
                         timeline_type=timeline_type):
                    self.fake.calls.append((operation_id, site_ref + ":" + ref +
                                            (":" + str(kind) if kind is not None else "")))
                    return {"status": "ok", "resource": operation_id,
                            "site_ref": site_ref, "client_ref": ref,
                            "data": {}, "partial": False}

                setattr(self.fake, method, read)
                route = f"/v1/sites/{'a' * 24}/clients/{client_ref}/{path_part}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation_id)
                request = {"jsonrpc": "2.0", "id": 37, "method": "tools/call",
                           "params": {"name": "omada_" + operation_id,
                                      "arguments": {"site_ref": "a" * 24,
                                                    "client_ref": client_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(
                    response["result"]["structuredContent"]["resource"],
                    operation_id)
                expected = "a" * 24 + ":" + client_ref
                if timeline_type is not None:
                    expected += ":" + timeline_type
                self.assertEqual(self.fake.calls[-2:],
                                 [(operation_id, expected)] * 2)

    def test_mcp_bundles_fixed_gateway_wan_and_health_reads(self) -> None:
        gateway_ref = "d" * 24
        self.fake.list_devices = lambda site_ref: self.fake.calls.append(("devices", site_ref)) or {
            "status": "ok", "resource": "devices", "site_ref": site_ref, "count": 1,
            "items": [{"device_ref": gateway_ref, "device_type": "gateway"}]}
        request = {"jsonrpc": "2.0", "id": 22, "method": "tools/call",
                   "params": {"name": "omada_network_diagnose_gateway",
                              "arguments": {"site_ref": "a" * 24,
                                            "gateway_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        result = response["result"]["structuredContent"]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(set(result["results"]), {
            "wan_status", "wan_details", "health", "health_timeline", "lan_status", "ports",
            "speed_test_results", "internet_info", "site_setting_existence", "site_capabilities"})
        self.assertEqual(result["results"]["wan_status"]["items"][0]["latency_ms"], 12)
        self.assertEqual(result["results"]["health"]["window_start_ms"], 100)
        self.assertEqual(self.fake.calls, [
            ("sites", None),
            ("devices", "a" * 24),
            ("gateway_wan_status", "a" * 24 + ":" + gateway_ref),
            ("gateway_wan_health", "a" * 24 + ":" + gateway_ref),
            ("gateway_health", "a" * 24 + ":" + gateway_ref),
            ("gateway_health_timeline", "a" * 24 + ":" + gateway_ref),
            ("gateway_lan_status", "a" * 24 + ":" + gateway_ref),
            ("gateway_ports", "a" * 24 + ":" + gateway_ref),
            ("gateway_speed_test_results", "a" * 24 + ":" + gateway_ref),
            ("gateway_internet_info", "a" * 24 + ":" + gateway_ref),
            ("site_setting_existence", "a" * 24),
            ("site_capabilities", "a" * 24),
        ])

    def test_gateway_diagnostic_preserves_only_sanitized_upstream_error_codes(self) -> None:
        gateway_ref = "d" * 24
        self.fake.list_devices = lambda site_ref: self.fake.calls.append(("devices", site_ref)) or {
            "status": "ok", "resource": "devices", "site_ref": site_ref, "count": 1,
            "items": [{"device_ref": gateway_ref, "device_type": "gateway"}]}

        def reject_internet_read(site_ref: str, selected_gateway: str) -> dict[str, object]:
            raise OpenApiError("openapi_rejected", upstream_error_code=-1,
                               upstream_http_status=200)

        self.fake.read_gateway_internet_info = reject_internet_read
        request = {"jsonrpc": "2.0", "id": 23, "method": "tools/call",
                   "params": {"name": "omada_network_diagnose_gateway",
                              "arguments": {"site_ref": "a" * 24,
                                            "gateway_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        result = response["result"]["structuredContent"]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["results"]["internet_info"], {
            "status": "error", "error": "openapi_rejected",
            "capability_status": "unknown", "upstream_http_status": 200,
            "upstream_error_code": -1,
        })

    def test_http_and_mcp_expose_fixed_gateway_wan_status_read(self) -> None:
        gateway_ref = "d" * 24
        path = f"/v1/sites/{'a' * 24}/gateways/{gateway_ref}/wan-status"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "gateway_wan_status")
        request = {"jsonrpc": "2.0", "id": 25, "method": "tools/call",
                   "params": {"name": "omada_gateway_wan_status",
                              "arguments": {"site_ref": "a" * 24,
                                            "device_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "gateway_wan_status")
        self.assertEqual(self.fake.calls,
                         [("gateway_wan_status", "a" * 24 + ":" + gateway_ref)] * 2)

    def test_http_and_mcp_expose_gateway_info_summary(self) -> None:
        site_ref, device_ref = "a" * 24, "d" * 24
        path = f"/v1/sites/{site_ref}/gateways/{device_ref}/info-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "gateway_info_summary")
        self.assertEqual(direct["data"]["firmware_version"], "1.2.3")
        request = {"jsonrpc": "2.0", "id": 228, "method": "tools/call",
                   "params": {"name": "omada_gateway_info_summary",
                              "arguments": {"site_ref": site_ref,
                                            "device_ref": device_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertIn("result", response, repr(response))
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("gateway_info_summary", site_ref + ":" + device_ref)] * 2)

    def test_http_and_mcp_expose_bridge_device_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/bridge-devices/summary"
        status, body = self.request(path)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_bridge_device_summary")
        request = {"jsonrpc": "2.0", "id": 234, "method": "tools/call",
                   "params": {"name": "omada_site_bridge_device_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("site_bridge_device_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_upnp_template_comparison(self) -> None:
        site_ref, template_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/settings/upnp/compare/{template_ref}"
        status, body = self.request(path)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_upnp_template_comparison")
        request = {"jsonrpc": "2.0", "id": 233, "method": "tools/call",
                   "params": {"name": "omada_site_upnp_template_comparison",
                              "arguments": {"site_ref": site_ref,
                                            "site_template_ref": template_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_upnp_template_comparison", site_ref, template_ref)] * 2)

    def test_http_and_mcp_expose_wan_qos_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/wan-qos-summary"
        status, body = self.request(path)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_wan_qos_summary")
        request = {"jsonrpc": "2.0", "id": 232, "method": "tools/call",
                   "params": {"name": "omada_site_wan_qos_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("site_wan_qos_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_remote_access_tunnel_status_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/remote-access/tunnels/status-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_remote_access_tunnel_status_summary")
        request = {"jsonrpc": "2.0", "id": 308, "method": "tools/call",
                   "params": {"name": "omada_site_remote_access_tunnel_status_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_remote_access_tunnel_status_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_ids_ips_config_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/security/ids-ips-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_ids_ips_config_summary")
        request = {"jsonrpc": "2.0", "id": 331, "method": "tools/call",
                   "params": {"name": "omada_site_ids_ips_config_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("site_ids_ips_config_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wan_unsupported_function_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/wan/unsupported-functions/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_wan_unsupported_function_summary")
        request = {"jsonrpc": "2.0", "id": 340, "method": "tools/call",
                   "params": {"name": "omada_site_wan_unsupported_function_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_wan_unsupported_function_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_vpn_server_status_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/vpn/servers/status-summary?vpn_type=5"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_vpn_server_status_summary")
        request = {"jsonrpc": "2.0", "id": 231, "method": "tools/call",
                   "params": {"name": "omada_site_vpn_server_status_summary",
                              "arguments": {"site_ref": site_ref, "vpn_type": 5}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertIn("result", response, repr(response))
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_vpn_server_status_summary", site_ref, 5)] * 2)

    def test_http_and_mcp_expose_vpn_client_status_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/vpn/clients/status-summary?vpn_type=4"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_vpn_client_status_summary")
        request = {"jsonrpc": "2.0", "id": 238, "method": "tools/call",
                   "params": {"name": "omada_site_vpn_client_status_summary",
                              "arguments": {"site_ref": site_ref, "vpn_type": 4}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_vpn_client_status_summary", site_ref, 4)] * 2)

    def test_http_and_mcp_expose_site_vpn_s2s_status_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/vpn/site-to-site/status-summary?vpn_type=4"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 240, "method": "tools/call",
                   "params": {"name": "omada_site_vpn_s2s_status_summary",
                              "arguments": {"site_ref": site_ref, "vpn_type": 4}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_vpn_s2s_status_summary", site_ref, 4)] * 2)

    def test_http_and_mcp_expose_site_s2s_vpn_inventory(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/vpn/site-to-site/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 251, "method": "tools/call",
                   "params": {"name": "omada_site_s2s_vpn_inventory_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_s2s_vpn_inventory_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_gateway_webfilter_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/gateway-webfilter/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_gateway_webfilter_summary")
        request = {"jsonrpc": "2.0", "id": 333, "method": "tools/call",
                   "params": {"name": "omada_site_gateway_webfilter_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_gateway_webfilter_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_ap_webfilter_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/ap-webfilter/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_ap_webfilter_summary")
        request = {"jsonrpc": "2.0", "id": 335, "method": "tools/call",
                   "params": {"name": "omada_site_ap_webfilter_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("site_ap_webfilter_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_url_filter_general_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/url-filter-general/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_url_filter_general_summary")
        request = {"jsonrpc": "2.0", "id": 336, "method": "tools/call",
                   "params": {"name": "omada_site_url_filter_general_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_url_filter_general_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_lan_interface_isolation_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/lan/interfaces/isolation-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_lan_interface_isolation_summary")
        request = {"jsonrpc": "2.0", "id": 337, "method": "tools/call",
                   "params": {"name": "omada_site_lan_interface_isolation_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_lan_interface_isolation_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_ospf_interface_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/ospf/interfaces/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_ospf_interface_summary")
        request = {"jsonrpc": "2.0", "id": 338, "method": "tools/call",
                   "params": {"name": "omada_site_ospf_interface_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_ospf_interface_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_switch_qos_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/switches/qos-rules/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_switch_qos_summary")
        request = {"jsonrpc": "2.0", "id": 339, "method": "tools/call",
                   "params": {"name": "omada_site_switch_qos_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("site_switch_qos_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_switch_ddm_summary(self) -> None:
        site_ref, device_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/switches/{device_ref}/ddm-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_switch_ddm_summary")
        request = {"jsonrpc": "2.0", "id": 340, "method": "tools/call",
                   "params": {"name": "omada_site_switch_ddm_summary",
                              "arguments": {"site_ref": site_ref, "device_ref": device_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_switch_ddm_summary", site_ref, device_ref)] * 2)

    def test_http_and_mcp_expose_site_gateway_qos_class_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/gateway-qos/classes/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_gateway_qos_class_summary")
        request = {"jsonrpc": "2.0", "id": 334, "method": "tools/call",
                   "params": {"name": "omada_site_gateway_qos_class_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_gateway_qos_class_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_vpn_server_config_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/vpn/servers/config-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_vpn_server_config_summary")
        request = {"jsonrpc": "2.0", "id": 307, "method": "tools/call",
                   "params": {"name": "omada_site_vpn_server_config_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_vpn_server_config_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_vpn_client_config_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/vpn/clients/config-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "site_vpn_client_config_summary")
        request = {"jsonrpc": "2.0", "id": 308, "method": "tools/call",
                   "params": {"name": "omada_site_vpn_client_config_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_vpn_client_config_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_s2s_vpn_v2_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/vpn/site-to-site-v2-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_s2s_vpn_v2_summary")
        request = {"jsonrpc": "2.0", "id": 306, "method": "tools/call",
                   "params": {"name": "omada_site_s2s_vpn_v2_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_s2s_vpn_v2_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_selected_s2s_peer_status(self) -> None:
        site_ref, vpn_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/vpn/site-to-site/{vpn_ref}/peers/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 252, "method": "tools/call",
                   "params": {"name": "omada_site_s2s_peer_status_summary",
                              "arguments": {"site_ref": site_ref, "vpn_ref": vpn_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertIn("result", response, repr(response))
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_s2s_peer_status_summary", site_ref, vpn_ref)] * 2)

    def test_http_and_mcp_expose_selected_ssid_topology_counts(self) -> None:
        site_ref, ssid_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/ssids/{ssid_ref}/topology-device-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 241, "method": "tools/call",
                   "params": {"name": "omada_site_ssid_topology_device_summary",
                              "arguments": {"site_ref": site_ref, "ssid_ref": ssid_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_ssid_topology_device_summary", site_ref, ssid_ref)] * 2)

    def test_http_and_mcp_expose_selected_ap_topology_client_counts(self) -> None:
        site_ref, device_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/aps/{device_ref}/topology-clients/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 242, "method": "tools/call",
                   "params": {"name": "omada_site_ap_topology_clients_summary",
                              "arguments": {"site_ref": site_ref,
                                            "device_ref": device_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_ap_topology_clients_summary", site_ref, device_ref)] * 2)

    def test_http_and_mcp_expose_selected_network_delivery_summary(self) -> None:
        site_ref, network_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/networks/{network_ref}/delivery-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 243, "method": "tools/call",
                   "params": {"name": "omada_site_network_delivery_summary",
                              "arguments": {"site_ref": site_ref,
                                            "network_ref": network_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_network_delivery_summary", site_ref, network_ref)] * 2)

    def test_http_and_mcp_expose_site_lan_port_profiles(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/lan-port-profiles/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 244, "method": "tools/call",
                   "params": {"name": "omada_site_lan_port_profiles_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_lan_port_profiles_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_controller_upgrade_plans(self) -> None:
        path = "/v1/controller/firmware-upgrade-plans/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, f"{direct!r} calls={self.fake.calls!r}")
        request = {"jsonrpc": "2.0", "id": 245, "method": "tools/call",
                   "params": {"name": "omada_controller_upgrade_plans_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("controller_upgrade_plans_summary",)] * 2)

    def test_http_and_mcp_expose_controller_try_beta_settings(self) -> None:
        path = "/v1/controller/firmware-preview-settings/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, f"{direct!r} calls={self.fake.calls!r}")
        request = {"jsonrpc": "2.0", "id": 256, "method": "tools/call",
                   "params": {"name": "omada_controller_try_beta_settings_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("controller_try_beta_settings_summary",)] * 2)

    def test_http_and_mcp_expose_controller_auto_check_upgrade_summary(self) -> None:
        path = "/v1/controller/automatic-firmware-checks/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, f"{direct!r} calls={self.fake.calls!r}")
        request = {"jsonrpc": "2.0", "id": 257, "method": "tools/call",
                   "params": {"name": "omada_controller_auto_check_upgrade_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("controller_auto_check_upgrade_summary",)] * 2)

    def test_http_and_mcp_expose_controller_firmware_inventory_summary(self) -> None:
        path = "/v1/controller/firmware-inventory-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 258, "method": "tools/call",
                   "params": {"name": "omada_controller_firmware_inventory_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("controller_firmware_inventory_summary",)] * 2)

    def test_http_and_mcp_expose_controller_firmware_pool_channel_counts(self) -> None:
        path = "/v1/controller/firmware-pool-channel-counts/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 260, "method": "tools/call",
                   "params": {"name": "omada_controller_firmware_pool_channel_counts",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("controller_firmware_pool_channel_counts",)] * 2)

    def test_http_and_mcp_expose_agile_switch_general_config_summary(self) -> None:
        site_ref, switch_ref = "a" * 24, "b" * 24
        path = (f"/v1/sites/{site_ref}/switches/{switch_ref}/"
                "agile-general-config-summary")
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 259, "method": "tools/call",
                   "params": {"name": "omada_site_agile_switch_general_config_summary",
                              "arguments": {"site_ref": site_ref, "switch_ref": switch_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [
            ("site_agile_switch_general_config_summary", site_ref, switch_ref)] * 2)

    def test_http_and_mcp_expose_controller_try_beta_settings(self) -> None:
        path = "/v1/controller/firmware-preview-settings/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, f"{direct!r} calls={self.fake.calls!r}")
        request = {"jsonrpc": "2.0", "id": 256, "method": "tools/call",
                   "params": {"name": "omada_controller_try_beta_settings_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("controller_try_beta_settings_summary",)] * 2)

    def test_http_and_mcp_expose_controller_auto_check_upgrade_summary(self) -> None:
        path = "/v1/controller/automatic-firmware-checks/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, f"{direct!r} calls={self.fake.calls!r}")
        request = {"jsonrpc": "2.0", "id": 257, "method": "tools/call",
                   "params": {"name": "omada_controller_auto_check_upgrade_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("controller_auto_check_upgrade_summary",)] * 2)

    def test_http_and_mcp_expose_controller_global_log_notifications(self) -> None:
        path = "/v1/controller/log-notifications/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, f"{direct!r} calls={self.fake.calls!r}")
        request = {"jsonrpc": "2.0", "id": 249, "method": "tools/call",
                   "params": {"name": "omada_controller_global_log_notification_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("controller_global_log_notification_summary",)] * 2)

    def test_http_and_mcp_expose_controller_upgrade_model_list(self) -> None:
        path = "/v1/controller/firmware-upgrade-models/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, f"{direct!r} calls={self.fake.calls!r}")
        request = {"jsonrpc": "2.0", "id": 250, "method": "tools/call",
                   "params": {"name": "omada_controller_upgrade_model_list_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("controller_upgrade_model_list_summary",)] * 2)

    def test_http_and_mcp_expose_site_lan_multicast_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/lan-multicast-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 246, "method": "tools/call",
                   "params": {"name": "omada_site_lan_multicast_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("site_lan_multicast_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_bandwidth_rules_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/bandwidth-control-rules/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 247, "method": "tools/call",
                   "params": {"name": "omada_site_bandwidth_rules_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_bandwidth_rules_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_hotspot_rate_limit_profiles_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/hotspot/rate-limit-profiles/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 262, "method": "tools/call",
                   "params": {"name": "omada_site_hotspot_rate_limit_profiles_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_hotspot_rate_limit_profiles_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_rate_limit_profiles_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/rate-limit-profiles/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 268, "method": "tools/call",
                   "params": {"name": "omada_site_rate_limit_profiles_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(direct["resource"], "site_rate_limit_profiles_summary")
        self.assertEqual(direct["profile_count"], 2)
        self.assertEqual(direct["directional_coverage"]["downstream"]["enabled_limit_kbps"]["sum"], 20000000)
        self.assertEqual(self.fake.calls,
                         [("site_rate_limit_profiles_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_log_notification_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/log-notification-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 248, "method": "tools/call",
                   "params": {"name": "omada_site_log_notification_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_log_notification_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_voucher_all_time_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/hotspot/vouchers/all-time-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_voucher_all_time_summary")
        request = {"jsonrpc": "2.0", "id": 267, "method": "tools/call",
                   "params": {"name": "omada_site_voucher_all_time_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_voucher_all_time_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_voucher_currency_options(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/hotspot/voucher-currency-options"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_voucher_currency_options")
        self.assertEqual(direct["data"]["currency_codes"], ["X1"])
        self.assertEqual(direct["data"]["selected_currency_code"], "Y2")
        request = {"jsonrpc": "2.0", "id": 268, "method": "tools/call",
                   "params": {"name": "omada_site_voucher_currency_options",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_voucher_currency_options", site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_voucher_group_inventory_coverage(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/hotspot/voucher-groups/coverage"
        self.fake.voucher_group_inventory_source = {
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"id": "private-group-id", "name": "private-group-name",
                      "unusedCount": 7, "usedCount": 8, "inUseCount": 9,
                      "expiredCount": 10, "totalCount": 34,
                      "unitPrice": "private-price", "currency": "private-currency",
                      "portalNames": ["private-portal"]}],
        }
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_hotspot_voucher_group_inventory_coverage")
        self.assertEqual(direct["returned_row_count"], 1)
        self.assertEqual(direct["voucher_count_field_coverage"]["totalCount"]["type_valid"], 1)
        serialized = json.dumps(direct)
        for marker in ("private-group-id", "private-group-name", "private-price",
                       "private-currency", "private-portal", '"unusedCount": 7'):
            self.assertNotIn(marker, serialized)
        request = {"jsonrpc": "2.0", "id": 270, "method": "tools/call",
                   "params": {"name": "omada_site_hotspot_voucher_group_inventory_coverage",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], direct)

        self.fake.voucher_group_inventory_source = {
            "currentPage": 1, "currentSize": 0, "data": []}
        status, missing = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertIsNone(missing["reported_total_row_count"])
        self.assertTrue(missing["partial"])
        status, missing_rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertIsNone(missing_rpc["result"]["structuredContent"]["reported_total_row_count"])
        self.assertTrue(missing_rpc["result"]["structuredContent"]["partial"])

        self.fake.voucher_group_inventory_source = {
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}
        status, zero = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(zero["reported_total_row_count"], 0)
        self.assertFalse(zero["partial"])
        status, zero_rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(zero_rpc["result"]["structuredContent"]["reported_total_row_count"], 0)
        self.assertFalse(zero_rpc["result"]["structuredContent"]["partial"])
        self.assertEqual(self.fake.calls,
                         [("site_hotspot_voucher_group_inventory_coverage", site_ref)] * 6)

    def test_http_and_mcp_preserve_missing_voucher_group_total_vs_zero(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/hotspot/voucher-group-options/coverage"
        request = {"jsonrpc": "2.0", "id": 269, "method": "tools/call",
                   "params": {"name": "omada_site_hotspot_voucher_group_options_coverage",
                              "arguments": {"site_ref": site_ref}}}

        self.fake.voucher_group_options_source = {
            "currentPage": 1, "currentSize": 0, "data": []}
        status, missing = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertIsNone(missing["reported_total_row_count"])
        self.assertTrue(missing["partial"])
        status, missing_rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        missing_structured = missing_rpc["result"]["structuredContent"]
        self.assertIsNone(missing_structured["reported_total_row_count"])
        self.assertTrue(missing_structured["partial"])

        self.fake.voucher_group_options_source = {
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}
        request["id"] = 270
        status, zero = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(zero["reported_total_row_count"], 0)
        self.assertFalse(zero["partial"])
        status, zero_rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        zero_structured = zero_rpc["result"]["structuredContent"]
        self.assertEqual(zero_structured["reported_total_row_count"], 0)
        self.assertFalse(zero_structured["partial"])
        for value in (missing, missing_structured, zero, zero_structured):
            json.dumps(value, allow_nan=False)
        self.assertEqual(self.fake.calls,
                         [("site_hotspot_voucher_group_options_coverage", site_ref)] * 4)

    def test_http_and_mcp_preserve_inconsistent_voucher_group_total_as_partial(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/hotspot/voucher-group-options/coverage"
        request = {"jsonrpc": "2.0", "id": 271, "method": "tools/call",
                   "params": {"name": "omada_site_hotspot_voucher_group_options_coverage",
                              "arguments": {"site_ref": site_ref}}}
        self.fake.voucher_group_options_source = {
            "totalRows": 0, "currentPage": 1, "currentSize": 100,
            "data": [{"groupId": "private-group-id", "name": "private-group-name"}],
        }
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["page_state"], "first_page_inconsistent_total")
        self.assertEqual(direct["reported_total_row_count"], 0)
        self.assertEqual(direct["returned_row_count"], 1)
        self.assertIsNone(direct["reported_remaining_row_count"])
        self.assertIsNone(direct["first_page_covers_reported_total"])
        self.assertTrue(direct["partial"])

        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], direct)
        for encoded in (json.dumps(direct), json.dumps(rpc)):
            self.assertNotIn("private-group-id", encoded)
            self.assertNotIn("private-group-name", encoded)
        for encoded in (direct, rpc["result"]["structuredContent"]):
            json.dumps(encoded, allow_nan=False)
        self.assertEqual(self.fake.calls,
                         [("site_hotspot_voucher_group_options_coverage", site_ref)] * 2)

        # The documented ER example's page zero is still rejected over both surfaces.
        self.fake.voucher_group_options_source = {
            "totalRows": 0, "currentPage": 0, "currentSize": 0,
            "data": [{"groupId": "private-group-id", "name": "private-group-name"}],
        }
        status, failure = self.request(path, self.token)
        self.assertEqual(status, 502)
        self.assertEqual(failure["error"], "openapi_response_invalid")
        status, failure_rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertTrue(failure_rpc["result"]["isError"])
        self.assertEqual(failure_rpc["result"]["structuredContent"]["error"],
                         "openapi_response_invalid")

    def test_http_and_mcp_expose_lan_network_interface_summary_and_optional_filter(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/lan-network-interfaces/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 249, "method": "tools/call",
                   "params": {"name": "omada_site_lan_network_interface_summary",
                              "arguments": {"site_ref": site_ref, "interface_type": 0}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_lan_network_interface_summary", site_ref, None),
                          ("site_lan_network_interface_summary", site_ref, 0)])
        status, _ = self.request(path + "?interface_type=1", self.token)
        self.assertEqual(status, 400)

    def test_http_and_mcp_expose_selected_ssid_client_count(self) -> None:
        site_ref, ssid_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/ssids/{ssid_ref}/clients/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_ssid_client_count_summary")
        request = {"jsonrpc": "2.0", "id": 239, "method": "tools/call",
                   "params": {"name": "omada_site_ssid_client_count_summary",
                              "arguments": {"site_ref": site_ref, "ssid_ref": ssid_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_ssid_client_count_summary", site_ref, ssid_ref)] * 2)

    def test_http_and_mcp_expose_redacted_site_remote_logging(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/remote-logging/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_remote_logging_summary")
        request = {"jsonrpc": "2.0", "id": 240, "method": "tools/call",
                   "params": {"name": "omada_site_remote_logging_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_remote_logging_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_bounded_upgrade_log_summary(self) -> None:
        path = "/v1/controller/firmware-upgrades/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "controller_upgrade_log_summary")
        request = {"jsonrpc": "2.0", "id": 241, "method": "tools/call",
                   "params": {"name": "omada_controller_upgrade_log_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("controller_upgrade_log_summary", None)] * 2)

    def test_http_and_mcp_expose_upgrade_log_inventory_and_failed_devices(self) -> None:
        status, direct = self.request(
            "/v1/controller/firmware-upgrades/inventory?page_number=1&page_size=25", self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "controller_upgrade_log_inventory")
        self.assertEqual(direct["page_number"], 1)
        self.assertEqual(direct["page_size"], 25)
        status, invalid = self.request(
            "/v1/controller/firmware-upgrades/inventory?page_number=0&page_size=25", self.token)
        self.assertEqual(status, 400, repr(invalid))
        ref = "a" * 24
        path = f"/v1/controller/firmware-upgrades/{ref}/failed-devices-summary"
        status, summary = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(summary["resource"], "controller_upgrade_failed_devices_summary")
        request = {"jsonrpc": "2.0", "id": 251, "method": "tools/call",
                   "params": {"name": "omada_controller_upgrade_failed_devices_summary",
                              "arguments": {"upgrade_log_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], summary)
        self.assertEqual(self.fake.calls[-3:], [
            ("controller_upgrade_log_inventory", 1, 25),
            ("controller_upgrade_failed_devices_summary", ref),
            ("controller_upgrade_failed_devices_summary", ref)])
        invalid_request = {"jsonrpc": "2.0", "id": 252, "method": "tools/call",
                           "params": {"name": "omada_controller_upgrade_log_inventory",
                                      "arguments": {"page_number": 0, "page_size": 25}}}
        status, invalid_rpc = self.request_post("/mcp", invalid_request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(invalid_rpc["error"]["message"], "arguments_invalid")

    def test_http_and_mcp_expose_controller_sdwan_group_summary(self) -> None:
        path = "/v1/controller/sdwan-groups/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "controller_sdwan_group_summary")
        request = {"jsonrpc": "2.0", "id": 242, "method": "tools/call",
                   "params": {"name": "omada_controller_sdwan_group_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("controller_sdwan_group_summary", None)] * 2)

    def test_http_and_mcp_expose_controller_sdwan_group_devices_summary(self) -> None:
        group_ref = "a" * 24
        path = f"/v1/controller/sdwan-groups/{group_ref}/devices/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200, repr(direct))
        self.assertEqual(direct["resource"], "controller_sdwan_group_devices_summary")
        request = {"jsonrpc": "2.0", "id": 309, "method": "tools/call",
                   "params": {"name": "omada_controller_sdwan_group_devices_summary",
                              "arguments": {"group_ref": group_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response.get("result", {}).get("structuredContent"), direct,
                         repr(response))
        self.assertEqual(self.fake.calls,
                         [("controller_sdwan_group_devices_summary", group_ref)] * 2)

    def test_http_and_mcp_expose_ipsec_sa_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/ipsec-sa-summary"
        status, body = self.request(path)
        self.assertEqual(status, 401, repr(body))
        self.assertEqual(body["error"], "unauthorized")
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_ipsec_sa_summary")
        request = {"jsonrpc": "2.0", "id": 230, "method": "tools/call",
                   "params": {"name": "omada_site_ipsec_sa_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_ipsec_sa_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_policy_route_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/policy-route-summary"
        status, body = self.request(path)
        self.assertEqual(status, 401, repr(body))
        self.assertEqual(body["error"], "unauthorized")
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_policy_route_summary")
        request = {"jsonrpc": "2.0", "id": 229, "method": "tools/call",
                   "params": {"name": "omada_site_policy_route_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_policy_route_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_static_route_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/static-route-summary"
        status, body = self.request(path)
        self.assertEqual(status, 401, repr(body))
        self.assertEqual(body["error"], "unauthorized")
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_static_route_summary")
        request = {"jsonrpc": "2.0", "id": 229, "method": "tools/call",
                   "params": {"name": "omada_site_static_route_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_static_route_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_static_route_interface_options_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/static-routing/interfaces/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_static_route_interface_options_summary")
        request = {"jsonrpc": "2.0", "id": 291, "method": "tools/call",
                   "params": {"name": "omada_site_static_route_interface_options_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_static_route_interface_options_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_group_bound_ssid_config_summary(self) -> None:
        site_ref, group_ref, ssid_ref = "a" * 24, "b" * 24, "c" * 24
        path = f"/v1/sites/{site_ref}/wlan-groups/{group_ref}/ssids/{ssid_ref}/config-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_wlan_group_ssid_config_summary")
        request = {"jsonrpc": "2.0", "id": 292, "method": "tools/call",
                   "params": {"name": "omada_site_wlan_group_ssid_config_summary",
                              "arguments": {"site_ref": site_ref,
                                            "wlan_group_ref": group_ref,
                                            "ssid_ref": ssid_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_wlan_group_ssid_config_summary", site_ref,
                           group_ref, ssid_ref)] * 2)

    def test_http_and_mcp_expose_fixed_gateway_lan_status_read(self) -> None:
        gateway_ref = "d" * 24
        path = f"/v1/sites/{'a' * 24}/gateways/{gateway_ref}/lan-status"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "gateway_lan_status")
        request = {"jsonrpc": "2.0", "id": 24, "method": "tools/call",
                   "params": {"name": "omada_gateway_lan_status",
                              "arguments": {"site_ref": "a" * 24,
                                            "device_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "gateway_lan_status")
        self.assertEqual(self.fake.calls,
                         [("gateway_lan_status", "a" * 24 + ":" + gateway_ref)] * 2)

    def test_http_and_mcp_expose_fixed_gateway_ports_read(self) -> None:
        gateway_ref = "d" * 24
        path = f"/v1/sites/{'a' * 24}/gateways/{gateway_ref}/ports"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "gateway_ports")
        request = {"jsonrpc": "2.0", "id": 25, "method": "tools/call",
                   "params": {"name": "omada_gateway_ports",
                              "arguments": {"site_ref": "a" * 24,
                                            "device_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "gateway_ports")
        self.assertEqual(self.fake.calls,
                         [("gateway_ports", "a" * 24 + ":" + gateway_ref)] * 2)

    def test_http_and_mcp_expose_gateway_internet_info(self) -> None:
        gateway_ref = "d" * 24
        path = f"/v1/sites/{'a' * 24}/gateways/{gateway_ref}/internet-info"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "gateway_internet_info")
        request = {"jsonrpc": "2.0", "id": 28, "method": "tools/call",
                   "params": {"name": "omada_gateway_internet_info",
                              "arguments": {"site_ref": "a" * 24, "device_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "gateway_internet_info")
        self.assertEqual(self.fake.calls,
                         [("gateway_internet_info", "a" * 24 + ":" + gateway_ref)] * 2)

    def test_http_and_mcp_expose_site_setting_existence(self) -> None:
        path = f"/v1/sites/{'a' * 24}/settings/existence"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_setting_existence")
        self.assertEqual(response["data"]["present_count"], len(FIELDS))
        request = {"jsonrpc": "2.0", "id": 83, "method": "tools/call",
                   "params": {"name": "omada_site_setting_existence",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_setting_existence")
        self.assertEqual(self.fake.calls, [("site_setting_existence", "a" * 24)] * 2)

    def test_http_and_mcp_expose_site_session_limit_enable_state(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/session-limit/enable-state", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_session_limit_enable_state")
        self.assertEqual(response["data"], {"enabled": False})
        request = {"jsonrpc": "2.0", "id": 154, "method": "tools/call",
                   "params": {"name": "omada_site_session_limit_enable_state",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_session_limit_enable_state")
        self.assertFalse(response["result"]["structuredContent"]["data"]["enabled"])
        self.assertEqual(self.fake.calls,
                         [("site_session_limit_enable_state", site_ref)] * 2)

    def test_http_and_mcp_expose_site_session_limit_rule_coverage(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/session-limit/rules/coverage", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_session_limit_rule_coverage")
        self.assertEqual(response["page_state"], "empty")
        self.assertNotIn("site_ref", response)
        request = {"jsonrpc": "2.0", "id": 159, "method": "tools/call",
                   "params": {"name": "omada_site_session_limit_rule_coverage",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        content = response["result"]["structuredContent"]
        self.assertEqual(content["resource"], "site_session_limit_rule_coverage")
        self.assertEqual(content["support_ip_address_coverage"]["type_valid"], 1)
        self.assertNotIn("site_ref", content)
        self.assertEqual(self.fake.calls,
                         [("site_session_limit_rule_coverage", site_ref)] * 2)

    def test_http_and_mcp_serialize_missing_and_explicit_total_distinctly(self) -> None:
        site_ref = "a" * 24
        sources = (
            {"currentPage": 1, "currentSize": 0, "data": [],
             "supportIpAddress": False},
            {"currentPage": 1, "currentSize": 1, "data": [{
                "name": "synthetic-rule", "status": True,
                "sourceType": 1, "maxSession": 5}],
             "supportIpAddress": True},
            {"totalRows": 0, "currentPage": 0, "currentSize": 0, "data": [],
             "supportIpAddress": False},
        )
        for request_id, source in enumerate(sources, start=201):
            with self.subTest(request_id=request_id):
                self.fake.session_limit_rule_coverage_source = source
                status, response = self.request(
                    f"/v1/sites/{site_ref}/session-limit/rules/coverage", self.token)
                self.assertEqual(status, 200)
                self.assertIn("reported_total_row_count", response)
                if "totalRows" in source:
                    self.assertEqual(response["reported_total_row_count"], 0)
                    self.assertFalse(response["partial"])
                else:
                    self.assertIsNone(response["reported_total_row_count"])
                    self.assertTrue(response["partial"])

                status, response = self.request_post("/mcp", {
                    "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                    "params": {"name": "omada_site_session_limit_rule_coverage",
                               "arguments": {"site_ref": site_ref}}}, self.token)
                self.assertEqual(status, 200)
                structured = response["result"]["structuredContent"]
                self.assertIn("reported_total_row_count", structured)
                if "totalRows" in source:
                    self.assertEqual(structured["reported_total_row_count"], 0)
                    self.assertFalse(structured["partial"])
                else:
                    self.assertIsNone(structured["reported_total_row_count"])
                    self.assertTrue(structured["partial"])

    def test_http_and_mcp_expose_site_mac_filtering_general_state(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/mac-filtering/general-state", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_mac_filtering_general_state")
        self.assertEqual(response["data"], {
            "direction_present": False, "enabled": False,
        })
        request = {"jsonrpc": "2.0", "id": 155, "method": "tools/call",
                   "params": {"name": "omada_site_mac_filtering_general_state",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_mac_filtering_general_state")
        self.assertFalse(
            response["result"]["structuredContent"]["data"]["enabled"])
        self.assertEqual(self.fake.calls,
                         [("site_mac_filtering_general_state", site_ref)] * 2)

    def test_http_and_mcp_expose_site_access_control_policy_coverage(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/access-control/policy-coverage", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_access_control_policy_coverage")
        self.assertEqual(response["data"], {
            "pre_auth_access_enabled": False,
            "free_auth_client_enabled": True,
        })
        request = {"jsonrpc": "2.0", "id": 158, "method": "tools/call",
                   "params": {"name": "omada_site_access_control_policy_coverage",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        content = response["result"]["structuredContent"]
        self.assertEqual(content["resource"], "site_access_control_policy_coverage")
        self.assertEqual(content["policy_list_coverage"][
            "free_auth_client_policies"]["entry_count"], 2)
        self.assertEqual(self.fake.calls,
                         [("site_access_control_policy_coverage", site_ref)] * 2)

    def test_http_and_mcp_expose_site_device_model_whitelist_coverage(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/devices/model-whitelist-coverage", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_device_model_whitelist_coverage")
        self.assertTrue(response["data"]["empty"])
        self.assertEqual(response["data"]["record_count"], 0)
        request = {"jsonrpc": "2.0", "id": 156, "method": "tools/call",
                   "params": {"name": "omada_site_device_model_whitelist_coverage",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        content = response["result"]["structuredContent"]
        self.assertEqual(content["resource"], "site_device_model_whitelist_coverage")
        self.assertEqual(content["data"]["record_count"], 0)
        self.assertEqual(self.fake.calls,
                         [("site_device_model_whitelist_coverage", site_ref)] * 2)

    def test_http_and_mcp_expose_site_portal_inventory_coverage(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/portals/coverage", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_portal_inventory_coverage")
        self.assertTrue(response["data"]["empty"])
        self.assertEqual(response["data"]["portal_count"], 0)
        request = {"jsonrpc": "2.0", "id": 157, "method": "tools/call",
                   "params": {"name": "omada_site_portal_inventory_coverage",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        content = response["result"]["structuredContent"]
        self.assertEqual(content["resource"], "site_portal_inventory_coverage")
        self.assertEqual(content["data"]["portal_count"], 0)
        self.assertEqual(self.fake.calls,
                         [("site_portal_inventory_coverage", site_ref)] * 2)

    def test_http_and_mcp_expose_site_capabilities(self) -> None:
        path = f"/v1/sites/{'a' * 24}/capabilities"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_capabilities")
        self.assertEqual(response["data"]["present_count"], len(SITE_CAPABILITY_FIELDS))
        request = {"jsonrpc": "2.0", "id": 84, "method": "tools/call",
                   "params": {"name": "omada_site_capabilities",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "site_capabilities")
        self.assertEqual(self.fake.calls, [("site_capabilities", "a" * 24)] * 2)

    def test_http_and_mcp_expose_site_unresolved_incident_count(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/incidents/unresolved-count"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_unresolved_incident_count")
        self.assertEqual(response["data"]["unresolved_count"], 2)
        rpc = {"jsonrpc": "2.0", "id": 86, "method": "tools/call",
               "params": {"name": "omada_site_unresolved_incident_count",
                          "arguments": {"site_ref": site_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_unresolved_incident_count")
        self.assertEqual(self.fake.calls, [("site_unresolved_incident_count", site_ref)] * 2)

    def test_http_and_mcp_expose_bounded_site_incident_overview(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/incidents/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_incident_overview")
        self.assertEqual(response["data"]["counts"], {"all_status": 3})
        rpc = {"jsonrpc": "2.0", "id": 87, "method": "tools/call",
               "params": {"name": "omada_site_incident_overview",
                          "arguments": {"site_ref": site_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"], "site_incident_overview")
        self.assertEqual(self.fake.calls, [("site_incident_overview", site_ref)] * 2)

    def test_http_and_mcp_expose_site_incident_distribution(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/incidents/distribution", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_incident_distribution")
        self.assertEqual(response["data"]["point_count"], 0)
        rpc = {"jsonrpc": "2.0", "id": 88, "method": "tools/call",
               "params": {"name": "omada_site_incident_distribution",
                          "arguments": {"site_ref": site_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_incident_distribution")
        self.assertEqual(self.fake.calls, [("site_incident_distribution", site_ref)] * 2)

    def test_http_and_mcp_expose_site_incident_category_counts(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/incidents/categories?category=13"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_incident_category_counts")
        self.assertEqual(response["category"], 13)
        self.assertEqual((response["window_start_ms"], response["window_end_ms"]), (100, 200))
        self.assertEqual(response["data"]["category_count"], 0)
        rpc = {"jsonrpc": "2.0", "id": 89, "method": "tools/call",
               "params": {"name": "omada_site_incident_category_counts",
                          "arguments": {"site_ref": site_ref, "category": 13}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_incident_category_counts")
        self.assertEqual(result["result"]["structuredContent"]["category"], 13)
        self.assertEqual(self.fake.calls, [("site_incident_category_counts", site_ref, 13)] * 2)

    def test_site_incident_category_requires_one_valid_code_before_dispatch(self) -> None:
        site_ref = "a" * 24
        for path in (f"/v1/sites/{site_ref}/incidents/categories",
                     f"/v1/sites/{site_ref}/incidents/categories?category=10",
                     f"/v1/sites/{site_ref}/incidents/categories?category=20",
                     f"/v1/sites/{site_ref}/incidents/categories?category=11&category=12"):
            status, response = self.request(path, self.token)
            self.assertEqual(status, 400)
            self.assertEqual(response["error"], "incident_category_required_or_invalid")
        for arguments in ({"site_ref": site_ref}, {"site_ref": site_ref, "category": 20},
                          {"site_ref": site_ref, "category": True}):
            rpc = {"jsonrpc": "2.0", "id": 890, "method": "tools/call",
                   "params": {"name": "omada_site_incident_category_counts",
                              "arguments": arguments}}
            status, response = self.request_post("/mcp", rpc, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["error"]["message"], "arguments_invalid")
        self.assertEqual(self.fake.calls, [])

    def test_http_and_mcp_expose_redacted_site_incident_list(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/incidents/list"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_incident_list")
        self.assertEqual(response["data"]["returned_count"], 0)
        rpc = {"jsonrpc": "2.0", "id": 90, "method": "tools/call",
               "params": {"name": "omada_site_incident_list",
                          "arguments": {"site_ref": site_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_incident_list")
        self.assertEqual(self.fake.calls, [("site_incident_list", site_ref)] * 2)

    def test_http_and_mcp_expose_site_batch_interference_history_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/wifi/interference-history-summary"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_batch_interference_history")
        self.assertEqual(response["data"]["scanning_count"], 1)
        rpc = {"jsonrpc": "2.0", "id": 119, "method": "tools/call",
               "params": {"name": "omada_site_batch_interference_history",
                          "arguments": {"site_ref": site_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(
            result["result"]["structuredContent"]["resource"],
            "site_batch_interference_history")
        self.assertEqual(self.fake.calls,
                         [("site_batch_interference_history", site_ref)] * 2)

    def test_http_and_mcp_expose_selected_site_channel_reuse(self) -> None:
        site_ref, refs = "a" * 24, ["b" * 24, "c" * 24]
        report = {"status": "ok", "resource": "site_channel_reuse_summary",
                  "site_ref": site_ref, "same_channel_reuse": [], "partial": False}
        calls: list[tuple[str, list[str]]] = []
        def read(site: str, devices: list[str]) -> dict[str, object]:
            calls.append((site, devices))
            return report
        self.fake.read_site_channel_reuse_summary = read  # type: ignore[attr-defined]
        status, response = self.request(
            f"/v1/sites/{site_ref}/channel-reuse?device_refs={refs[0]},{refs[1]}", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_channel_reuse_summary")
        rpc = {"jsonrpc": "2.0", "id": 121, "method": "tools/call",
               "params": {"name": "omada_site_channel_reuse_summary",
                           "arguments": {"site_ref": site_ref, "device_refs": refs}}}
        status, mcp = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(mcp["result"]["structuredContent"]["resource"],
                         "site_channel_reuse_summary")
        self.assertEqual(calls, [(site_ref, refs), (site_ref, refs)])

    def test_http_and_mcp_expose_batch_interference_ap_summary(self) -> None:
        site_ref, history_ref = "a" * 24, "d" * 24
        path = f"/v1/sites/{site_ref}/wifi/interference-history/{history_ref}/ap-summary"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_batch_interference_ap_summary")
        rpc = {"jsonrpc": "2.0", "id": 120, "method": "tools/call",
               "params": {"name": "omada_site_batch_interference_ap_summary",
                          "arguments": {"site_ref": site_ref, "history_ref": history_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_batch_interference_ap_summary")
        self.assertEqual(self.fake.calls,
                         [("site_batch_interference_ap_summary", site_ref + ":" + history_ref)] * 2)

    def test_http_and_mcp_expose_batch_wifi_interference_summary(self) -> None:
        site_ref, history_ref = "a" * 24, "b" * 24
        path = (f"/v1/sites/{site_ref}/wifi/interference-history/"
                f"{history_ref}/wifi-interference-summary")
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_batch_wifi_interference_summary")
        self.assertEqual(response["data"]["radio_id_counts"], {"0": 1})
        rpc = {"jsonrpc": "2.0", "id": 121, "method": "tools/call",
               "params": {"name": "omada_site_batch_wifi_interference_summary",
                          "arguments": {"site_ref": site_ref, "history_ref": history_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_batch_wifi_interference_summary")
        self.assertEqual(self.fake.calls,
                         [("site_batch_wifi_interference_summary",
                           site_ref + ":" + history_ref)] * 2)

    def test_http_and_mcp_expose_batch_channel_load_summary(self) -> None:
        site_ref, history_ref, device_ref = "a" * 24, "b" * 24, "c" * 24
        path = (f"/v1/sites/{site_ref}/wifi/interference-history/{history_ref}/"
                f"aps/{device_ref}/channel-load-summary")
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_batch_channel_load_summary")
        rpc = {"jsonrpc": "2.0", "id": 122, "method": "tools/call",
               "params": {"name": "omada_site_batch_channel_load_summary",
                          "arguments": {"site_ref": site_ref, "history_ref": history_ref,
                                        "device_ref": device_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_batch_channel_load_summary")
        self.assertEqual(self.fake.calls, [
            ("site_batch_channel_load_summary", site_ref + ":" + history_ref + ":" + device_ref)] * 2)

    def test_http_and_mcp_expose_batch_interference_result_summary(self) -> None:
        site_ref, history_ref = "a" * 24, "b" * 24
        path = (f"/v1/sites/{site_ref}/wifi/interference-history/{history_ref}/"
                "interference-summary")
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_batch_interference_result_summary")
        rpc = {"jsonrpc": "2.0", "id": 123, "method": "tools/call",
               "params": {"name": "omada_site_batch_interference_result_summary",
                          "arguments": {"site_ref": site_ref, "history_ref": history_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_batch_interference_result_summary")
        self.assertEqual(self.fake.calls, [
            ("site_batch_interference_result_summary", site_ref + ":" + history_ref)] * 2)

    def test_http_and_mcp_expose_interference_status_read(self) -> None:
        site_ref, history_ref = "a" * 24, "b" * 24
        path = (f"/v1/sites/{site_ref}/wifi/interference-history/{history_ref}/"
                "status-summary")
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["items"], [{"status": "finished"}])
        rpc = {"jsonrpc": "2.0", "id": 124, "method": "tools/call",
               "params": {"name": "omada_site_batch_interference_status_summary",
                          "arguments": {"site_ref": site_ref, "history_ref": history_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result.get("result", {}).get("structuredContent", {}).get("resource"),
                         "site_batch_interference_status_summary", result)
        self.assertEqual(self.fake.calls, [
            ("site_batch_interference_status_summary", site_ref + ":" + history_ref)] * 2)

    def test_http_and_mcp_expose_ap_full_channel_detect_status(self) -> None:
        site_ref, device_ref = "a" * 24, "c" * 24
        path = f"/v1/sites/{site_ref}/aps/{device_ref}/full-channel-detect-status"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["statuses"]["full_channel_detection"], "scanning")
        rpc = {"jsonrpc": "2.0", "id": 125, "method": "tools/call",
               "params": {"name": "omada_site_ap_full_channel_detect_status",
                          "arguments": {"site_ref": site_ref, "device_ref": device_ref}}}
        status, result = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(result["result"]["structuredContent"]["resource"],
                         "site_ap_full_channel_detect_status")
        self.assertEqual(self.fake.calls,
            [("site_ap_full_channel_detect_status", site_ref + ":" + device_ref)] * 2)

    def test_http_and_mcp_expose_opaque_device_incident_refs_and_detail(self) -> None:
        site_ref, device_ref, incident_ref = "a" * 24, "b" * 24, "c" * 24
        status, listed = self.request(
            f"/v1/sites/{site_ref}/devices/{device_ref}/incidents", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(listed["items"][0]["incident_ref"], incident_ref)
        status, detail = self.request(f"/v1/sites/{site_ref}/incidents/{incident_ref}", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(detail["resource"], "site_incident_detail")
        rpc = {"jsonrpc": "2.0", "id": 93, "method": "tools/call",
               "params": {"name": "omada_device_health_incidents",
                          "arguments": {"site_ref": site_ref, "device_ref": device_ref}}}
        status, mcp_list = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(mcp_list["result"]["structuredContent"]["resource"],
                         "device_health_incidents")
        rpc["id"] = 95
        rpc["params"] = {"name": "omada_client_health_incidents",
                         "arguments": {"site_ref": site_ref, "client_ref": device_ref}}
        status, mcp_client_list = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(mcp_client_list["result"]["structuredContent"]["resource"],
                         "client_health_incidents")
        rpc["id"] = 94
        rpc["params"] = {"name": "omada_site_incident_detail",
                         "arguments": {"site_ref": site_ref, "incident_ref": incident_ref}}
        status, mcp_detail = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(mcp_detail["result"]["structuredContent"]["resource"],
                         "site_incident_detail")
        self.assertEqual(self.fake.calls, [
            ("device_health_incidents", site_ref + ":" + device_ref),
            ("site_incident_detail", site_ref + ":" + incident_ref),
            ("device_health_incidents", site_ref + ":" + device_ref),
            ("client_health_incidents", site_ref + ":" + device_ref),
            ("site_incident_detail", site_ref + ":" + incident_ref),
        ])

    def test_http_and_mcp_expose_site_incident_notification(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/incidents/notification", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_incident_notification")
        request = {"jsonrpc": "2.0", "id": 86, "method": "tools/call",
                   "params": {"name": "omada_site_incident_notification",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_incident_notification")
        self.assertEqual(self.fake.calls,
                         [("site_incident_notification", site_ref)] * 2)

    def test_http_and_mcp_expose_site_anomaly_event_settings(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/incidents/settings", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_anomaly_event_settings")
        request = {"jsonrpc": "2.0", "id": 87, "method": "tools/call",
                   "params": {"name": "omada_site_anomaly_event_settings",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_anomaly_event_settings")
        self.assertEqual(self.fake.calls,
                         [("site_anomaly_event_settings", site_ref)] * 2)

    def test_http_and_mcp_expose_incident_influence_reads(self) -> None:
        site_ref, incident_ref = "a" * 24, "b" * 24
        for kind in ("clients", "devices"):
            with self.subTest(kind=kind):
                operation = "site_incident_influencing_" + kind
                route = f"/v1/sites/{site_ref}/incidents/{incident_ref}/influencing-{kind}"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation)
                request = {"jsonrpc": "2.0", "id": 88, "method": "tools/call",
                           "params": {"name": "omada_" + operation,
                                      "arguments": {"site_ref": site_ref,
                                                    "incident_ref": incident_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
        self.assertEqual(len(self.fake.calls), 4)

    def test_http_and_mcp_expose_wireless_group_capacity_reads(self) -> None:
        site_ref = "a" * 24
        for kind in ("wlan", "ap"):
            with self.subTest(kind=kind):
                operation = "site_" + kind + "_group_capacity"
                status, response = self.request(
                    f"/v1/sites/{site_ref}/{kind}-group-capacity", self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation)
                request = {"jsonrpc": "2.0", "id": 89, "method": "tools/call",
                           "params": {"name": "omada_" + operation,
                                      "arguments": {"site_ref": site_ref}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
        self.assertEqual(len(self.fake.calls), 4)

    def test_http_and_mcp_expose_site_switch_support(self) -> None:
        path = f"/v1/sites/{'a' * 24}/switch-support"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_switch_support")
        self.assertEqual(response["data"]["present_count"], len(SITE_SWITCH_SUPPORT_FIELDS))
        request = {"jsonrpc": "2.0", "id": 85, "method": "tools/call",
                   "params": {"name": "omada_site_switch_support",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_switch_support")
        self.assertEqual(self.fake.calls, [("site_switch_support", "a" * 24)] * 2)

    def test_http_and_mcp_expose_network_dhcp_server_capabilities(self) -> None:
        path = f"/v1/sites/{'a' * 24}/networks/{'c' * 24}/dhcp-server/capabilities"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "network_dhcp_server_capabilities")
        self.assertEqual(response["data"]["capabilities"], {
            "get_dhcp_client_table": True, "get_dhcp_server_info": False})
        request = {"jsonrpc": "2.0", "id": 86, "method": "tools/call",
                   "params": {"name": "omada_network_dhcp_server_capabilities",
                              "arguments": {"site_ref": "a" * 24, "network_ref": "c" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "network_dhcp_server_capabilities")
        self.assertEqual(self.fake.calls, [
            ("network_dhcp_server_capabilities", "a" * 24 + ":" + "c" * 24)] * 2)

    def test_http_and_mcp_expose_network_dhcp_server_info(self) -> None:
        path = f"/v1/sites/{'a' * 24}/networks/{'c' * 24}/dhcp-server/info"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "network_dhcp_server_info")
        self.assertEqual(response["data"]["available_ip_count"], 12)
        request = {"jsonrpc": "2.0", "id": 87, "method": "tools/call",
                   "params": {"name": "omada_network_dhcp_server_info",
                              "arguments": {"site_ref": "a" * 24, "network_ref": "c" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "network_dhcp_server_info")
        self.assertEqual(self.fake.calls, [
            ("network_dhcp_server_info", "a" * 24 + ":" + "c" * 24)] * 2)

    def test_http_and_mcp_expose_gateway_dhcp_lease_summary(self) -> None:
        gateway_ref = "d" * 24
        path = f"/v1/sites/{'a' * 24}/gateways/{gateway_ref}/dhcp/leases"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "gateway_dhcp_leases")
        request = {"jsonrpc": "2.0", "id": 27, "method": "tools/call",
                   "params": {"name": "omada_gateway_dhcp_leases",
                              "arguments": {"site_ref": "a" * 24, "gateway_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "gateway_dhcp_leases")
        self.assertEqual(self.fake.calls,
                         [("gateway_dhcp_leases", "a" * 24 + ":" + gateway_ref)] * 2)

    def test_http_and_mcp_expose_saved_gateway_speed_test_results(self) -> None:
        gateway_ref = "d" * 24
        path = f"/v1/sites/{'a' * 24}/gateways/{gateway_ref}/speed-test-results"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "gateway_speed_test_results")
        request = {"jsonrpc": "2.0", "id": 26, "method": "tools/call",
                   "params": {"name": "omada_gateway_speed_test_results",
                              "arguments": {"site_ref": "a" * 24, "device_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "gateway_speed_test_results")
        self.assertEqual(self.fake.calls,
                         [("gateway_speed_test_results", "a" * 24 + ":" + gateway_ref)] * 2)

    def test_http_and_mcp_expose_site_speed_test_settings_without_starting_a_test(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/speed-test/settings"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "speed_test_settings")
        request = {"jsonrpc": "2.0", "id": 32, "method": "tools/call",
                   "params": {"name": "omada_site_speed_test_settings",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "speed_test_settings")
        self.assertEqual(self.fake.calls, [("site_speed_test_settings", site_ref)] * 2)

    def test_http_and_mcp_expose_inventory_bound_ap_uplink_configuration(self) -> None:
        site_ref, ap_ref = "a" * 24, AP_REF
        path = f"/v1/sites/{site_ref}/aps/{ap_ref}/uplink-config"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "ap_uplink_config")
        request = {"jsonrpc": "2.0", "id": 33, "method": "tools/call",
                   "params": {"name": "omada_ap_uplink_config",
                              "arguments": {"site_ref": site_ref, "device_ref": ap_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "ap_uplink_config")
        self.assertEqual(self.fake.calls,
                         [("ap_uplink_config", site_ref + ":" + ap_ref)] * 2)

    def test_http_and_mcp_expose_recent_rf_planning_history_as_a_fixed_read(self) -> None:
        path = "/v1/sites/" + "a" * 24 + "/wifi/optimization/history/recent"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "rf_planning_recent_history")
        request = {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                   "params": {"name": "omada_rf_planning_recent_history",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "rf_planning_recent_history")
        self.assertEqual(self.fake.calls, [("rf_planning_recent_history", "a" * 24)] * 2)

    def test_http_and_mcp_expose_inventory_bound_ap_channel_load_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/aps/{AP_REF}/channel-load-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "ap_channel_load_summary")
        self.assertEqual(direct["data"]["bands"]["2g"]["average_load"], 50.0)
        request = {"jsonrpc": "2.0", "id": 130, "method": "tools/call",
                   "params": {"name": "omada_ap_channel_load_summary",
                              "arguments": {"site_ref": site_ref, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
            [("ap_channel_load_summary", site_ref + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_inventory_bound_ap_interference_result_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/aps/{AP_REF}/interference-result-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "ap_interference_result_summary")
        self.assertTrue(direct["partial"])
        request = {"jsonrpc": "2.0", "id": 129, "method": "tools/call",
                   "params": {"name": "omada_ap_interference_result_summary",
                              "arguments": {"site_ref": site_ref, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
            [("ap_interference_result_summary", site_ref + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_compact_inventory_bound_ap_available_channels(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/aps/{AP_REF}/available-channels-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "ap_available_channels_summary")
        self.assertEqual(direct["data"]["radios"][0]["channels"], [[1, 2412, 1, [20, 40]], [2, 2437, 2, [20]]])
        request = {"jsonrpc": "2.0", "id": 128, "method": "tools/call",
                   "params": {"name": "omada_ap_available_channels_summary",
                              "arguments": {"site_ref": site_ref, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
            [("ap_available_channels_summary", site_ref + ":" + AP_REF)] * 2)

    def test_http_and_mcp_expose_inventory_bound_ap_available_channels(self) -> None:
        path = f"/v1/sites/{'a' * 24}/aps/{AP_REF}/available-channels"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "ap_available_channels")
        self.assertEqual(direct["data"]["radios"][0]["channels"][0]["frequency_mhz"], 2412)
        request = {"jsonrpc": "2.0", "id": 29, "method": "tools/call",
                   "params": {"name": "omada_ap_available_channels",
                              "arguments": {"site_ref": "a" * 24, "device_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [
            ("ap_available_channels", "a" * 24 + ":" + AP_REF)] * 2)

    def test_mcp_runs_fixed_wlan_diagnosis_workflow(self) -> None:
        site_ref = "a" * 24
        self.fake.read_band_steering = lambda ref: self.fake.calls.append(("band_steering", ref)) or {
            "status": "ok", "resource": "band_steering", "site_ref": ref,
            "data": {"mode": 1}}
        self.fake.read_rrm_settings = lambda ref: self.fake.calls.append(("rrm_settings", ref)) or {
            "status": "ok", "resource": "rrm_settings", "site_ref": ref,
            "data": {"mode": 1, "timeRangeEnable": False, "resource": 0,
                     "timeRangeAction": 1}, "partial": False, "omitted_field_count": 0}
        self.fake.read_roaming_settings = lambda ref: self.fake.calls.append(("roaming_settings", ref)) or {
            "status": "ok", "resource": "roaming_settings", "site_ref": ref,
            "data": {"fastRoamingEnable": True, "aiRoamingEnable": False,
                     "dualBand11kReportEnable": True, "forceDisassociationEnable": False,
                     "nonStickRoamingEnable": True}, "partial": False, "omitted_field_count": 0}
        request = {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                   "params": {"name": "omada_wifi_diagnose_site",
                              "arguments": {"site_ref": "a" * 24}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        report = response["result"]["structuredContent"]
        self.assertEqual(set(report["results"]), {
            "wifi_health_timeline", "wifi_health_details", "wifi_channels",
            "client_signal_distribution", "site_6ghz_ap_presence",
            "site_rogue_ap_results", "band_steering", "rrm_settings", "roaming_settings",
            "site_wids_summary", "site_wids_blacklist_summary",
            "site_topology_network_summary"})
        self.assertEqual(self.fake.calls, [
            ("sites", None), ("wifi_health", "a" * 24),
            ("wifi_subhealth", "a" * 24), ("wifi_channels", "a" * 24),
            ("client_signal_distribution", "a" * 24),
            ("site_6ghz_ap_presence", "a" * 24),
            ("site_rogue_ap_results", "a" * 24),
            ("site_wids_summary", "a" * 24),
            ("site_wids_blacklist_summary", "a" * 24),
            ("band_steering", site_ref), ("rrm_settings", site_ref),
            ("roaming_settings", site_ref),
            ("site_topology_network_summary", site_ref),
        ])

    def test_mcp_client_workflow_selects_compact_timeline_report(self) -> None:
        expected = {"status": "ok", "client": {"timelines": {}}}
        request = {"jsonrpc": "2.0", "id": 41, "method": "tools/call",
                   "params": {"name": "omada_wifi_diagnose_client",
                              "arguments": {"site_ref": "a" * 24,
                                            "client_ref": "c" * 24}}}
        with patch("tools.wifi_diagnose.run", return_value=expected) as run:
            status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], expected)
        self.assertTrue(run.call_args.kwargs["compact_client_timeline"])
        self.assertFalse(run.call_args.kwargs["include_wlan_policy_context"])

    def test_mcp_runs_fixed_ap_diagnosis_using_only_read_routes(self) -> None:
        request = {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                   "params": {"name": "omada_wifi_diagnose_ap",
                              "arguments": {"site_ref": "a" * 24, "ap_ref": AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        report = response["result"]["structuredContent"]
        self.assertEqual(report["ap"]["status"], "ok",
                         repr((report["ap"], self.fake.calls)))
        self.assertEqual(set(report["ap"]) - {"status", "capability_status"},
                         {"health", "timeline", "radio_config", "rf_scan", "lan_traffic",
                          "wifi_neighbors", "speed_test_results", "wired_downlink",
                          "wired_uplink", "ports", "lldp_config", "port_vlans",
                          "wlan_overrides"})
        self.assertEqual(self.fake.calls, [
            ("sites", None), ("devices", "a" * 24),
            ("wifi_health", "a" * 24), ("wifi_subhealth", "a" * 24),
            ("wifi_channels", "a" * 24), ("client_signal_distribution", "a" * 24),
            ("site_6ghz_ap_presence", "a" * 24),
            ("site_rogue_ap_results", "a" * 24),
            ("ap_health", "a" * 24 + ":" + AP_REF),
            ("ap_health_timeline", "a" * 24 + ":" + AP_REF),
            ("radio_config", "a" * 24 + ":" + AP_REF),
            ("ap_rf_scan", "a" * 24 + ":" + AP_REF),
            ("ap_lan_traffic", "a" * 24 + ":" + AP_REF),
            ("ap_wifi_neighbors", "a" * 24 + ":" + AP_REF),
            ("ap_speed_test_results", "a" * 24 + ":" + AP_REF),
            ("ap_wired_downlink", "a" * 24 + ":" + AP_REF),
            ("ap_wired_uplink", "a" * 24 + ":" + AP_REF),
            ("ap_ports", "a" * 24 + ":" + AP_REF),
            ("ap_lldp_config", "a" * 24 + ":" + AP_REF),
            ("ap_port_vlans", "a" * 24 + ":" + AP_REF),
            ("ap_wlan_overrides", "a" * 24 + ":" + AP_REF),
        ])

    def test_mcp_runs_fixed_switch_diagnosis_using_current_inventory_and_read_routes(self) -> None:
        switch_ref = "f" * 24
        self.fake.list_devices = lambda site_ref: self.fake.calls.append(("devices", site_ref)) or {
            "status": "ok", "resource": "devices", "count": 1,
            "items": [{"device_ref": switch_ref, "device_type": "switch"}]}
        request = {"jsonrpc": "2.0", "id": 28, "method": "tools/call",
                   "params": {"name": "omada_network_diagnose_switch",
                              "arguments": {"site_ref": "a" * 24,
                                            "switch_ref": switch_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        report = response["result"]["structuredContent"]
        self.assertEqual(report["status"], "ok")
        self.assertEqual(set(report["results"]), {
            "health", "health_timeline", "sdm_usage", "cable_test_logs", "cable_test_full_results", "cable_test_increment_results", "cable_test_ports", "dhcp_users", "ospf_neighbors", "port_networks", "exist_networks", "networks", "interfaces", "routing_table", "static_routes", "vrfs", "vlan_interfaces", "statistics", "ports", "port_counters", "poe", "vlans", "lldp"})
        self.assertEqual(report["results"]["dhcp_users"]["summary"], {"total": 0})
        self.assertEqual(self.fake.calls, [
            ("sites", None), ("devices", "a" * 24),
            ("switch_health", "a" * 24 + ":" + switch_ref),
            ("switch_health_timeline", "a" * 24 + ":" + switch_ref),
            ("switch_sdm_usage", "a" * 24 + ":" + switch_ref),
            ("switch_cable_test_logs", "a" * 24 + ":" + switch_ref),
            ("switch_cable_test_full_results", "a" * 24 + ":" + switch_ref),
            ("switch_cable_test_increment_results", "a" * 24 + ":" + switch_ref),
            ("switch_cable_test_ports", "a" * 24 + ":" + switch_ref),
            ("switch_dhcp_users", "a" * 24 + ":" + switch_ref),
            ("switch_ospf_neighbors", "a" * 24 + ":" + switch_ref),
            ("switch_port_networks", "a" * 24 + ":" + switch_ref),
            ("switch_exist_networks", "a" * 24 + ":" + switch_ref),
            ("switch_networks", "a" * 24 + ":" + switch_ref),
            ("switch_interfaces", "a" * 24 + ":" + switch_ref),
            ("switch_routing_table", "a" * 24 + ":" + switch_ref),
            ("switch_static_routes", "a" * 24 + ":" + switch_ref),
            ("switch_vrfs", "a" * 24 + ":" + switch_ref),
            ("switch_vlan_interfaces", "a" * 24 + ":" + switch_ref),
            ("switch_statistics", "a" * 24 + ":" + switch_ref),
            ("switch_ports", "a" * 24 + ":" + switch_ref),
            ("switch_port_counters", "a" * 24 + ":" + switch_ref),
            ("switch_port_poe_info", "a" * 24 + ":" + switch_ref),
            ("switch_vlans", "a" * 24 + ":" + switch_ref),
            ("switch_lldp_neighbors", "a" * 24 + ":" + switch_ref),
        ])

    def test_mcp_compares_two_inventory_bound_aps_with_compact_fixed_reads(self) -> None:
        self.fake.list_devices = lambda site_ref: {
            "status": "ok", "resource": "devices", "count": 2,
            "items": [_device(AP_REF), _device(OTHER_AP_REF)]}
        request = {"jsonrpc": "2.0", "id": 17, "method": "tools/call",
                   "params": {"name": "omada_wifi_compare_aps",
                              "arguments": {"site_ref": "a" * 24,
                                            "ap_ref_a": AP_REF, "ap_ref_b": OTHER_AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        result = response["result"]["structuredContent"]
        self.assertEqual(result["resource"], "wifi_ap_comparison")
        self.assertEqual(result["count"], 2)
        self.assertEqual([item["ap_ref"] for item in result["items"]], [AP_REF, OTHER_AP_REF])
        self.assertNotIn("timeline", result["items"][0])
        self.assertEqual(len(self.fake.calls), 11)
        self.assertEqual({call[0] for call in self.fake.calls}, {
            "sites", "ap_health", "radio_config", "ap_rf_scan", "ap_lan_traffic",
            "ap_wifi_neighbors"})

    def test_mcp_ap_comparison_preserves_sanitized_upstream_neighbor_error(self) -> None:
        self.fake.list_devices = lambda site_ref: {
            "status": "ok", "resource": "devices", "count": 2,
            "items": [_device(AP_REF), _device(OTHER_AP_REF)]}
        original = self.fake.read_ap_wifi_neighbors

        def read_neighbors(site_ref: str, ap_ref: str) -> dict[str, object]:
            if ap_ref == AP_REF:
                raise OpenApiError("openapi_rejected", upstream_error_code=-39386,
                                   upstream_http_status=200)
            return original(site_ref, ap_ref)

        self.fake.read_ap_wifi_neighbors = read_neighbors
        request = {"jsonrpc": "2.0", "id": 27, "method": "tools/call",
                   "params": {"name": "omada_wifi_compare_aps",
                              "arguments": {"site_ref": "a" * 24,
                                            "ap_ref_a": AP_REF, "ap_ref_b": OTHER_AP_REF}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        result = response["result"]["structuredContent"]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["items"][0]["wifi_neighbors"]["error"], "openapi_rejected")
        self.assertEqual(result["items"][0]["wifi_neighbors"]["upstream_http_status"], 200)
        self.assertEqual(result["items"][0]["wifi_neighbors"]["upstream_error_code"], -39386)
        self.assertEqual(result["items"][1]["wifi_neighbors"]["status"], "ok")

    def test_mcp_exposes_each_fixed_wlan_diagnosis_read(self) -> None:
        tools = (
            ("omada_wifi_health", "wifi_health"),
            ("omada_wifi_subhealth", "wifi_subhealth"),
            ("omada_site_dashboard_channels", "site_dashboard_channels"),
            ("omada_site_client_signal_distribution", "client_signal_distribution"),
        )
        for index, (name, resource) in enumerate(tools, start=10):
            with self.subTest(name=name):
                status, response = self.request_post(
                    "/mcp", {"jsonrpc": "2.0", "id": index, "method": "tools/call",
                             "params": {"name": name,
                                        "arguments": {"site_ref": "a" * 24}}}, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], resource)
        self.assertEqual(self.fake.calls, [
            ("wifi_health", "a" * 24), ("wifi_subhealth", "a" * 24),
            ("wifi_channels", "a" * 24), ("client_signal_distribution", "a" * 24),
        ])

    def test_mcp_rejects_non_local_browser_origin(self) -> None:
        status, body = self.request_post(
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            self.token,
            origin="https://untrusted.example",
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "origin_not_allowed")

    def test_both_routes_require_bearer_token(self) -> None:
        for path in ("/v1/sites", "/v1/sites/" + "a" * 24 + "/devices",
                     "/v1/sites/" + "a" * 24 + "/clients",
                     "/v1/sites/" + "a" * 24 + "/networks",
                     "/v1/sites/" + "a" * 24 + "/ssids",
                     "/v1/sites/" + "a" * 24 + "/aps/" + "b" * 24 + "/radios"):
            with self.subTest(path=path):
                status, body = self.request(path)
                self.assertEqual(status, 401, repr(body))
                self.assertEqual(body["error"], "unauthorized")
        self.assertEqual(self.fake.calls, [])

    def test_controller_health_http_dispatch_requires_auth(self) -> None:
        self.assertEqual(self.request("/v1/controller/health")[0], 401)
        status, body = self.request("/v1/controller/health", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "controller_health")
        self.assertEqual(self.fake.calls, [("controller_health", None)])

    def test_controller_scenarios_http_and_mcp(self) -> None:
        self.assertEqual(self.request("/v1/controller/scenarios")[0], 401)
        status, body = self.request("/v1/controller/scenarios", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["items"], ["Wireless", "Switching"])
        request = {"jsonrpc": "2.0", "id": 111, "method": "tools/call",
                   "params": {"name": "omada_controller_scenarios", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["scenario_count"], 2)
        self.assertEqual(self.fake.calls, [
            ("controller_scenarios", None), ("controller_scenarios", None)])

    def test_controller_scenario_differences_http_and_mcp(self) -> None:
        self.assertEqual(self.request("/v1/controller/scenario-differences")[0], 401)
        status, body = self.request("/v1/controller/scenario-differences", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["items"], [{"name": "Default", "is_default": True}])
        request = {"jsonrpc": "2.0", "id": 112, "method": "tools/call",
                   "params": {"name": "omada_controller_scenario_differences",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        result = response["result"]["structuredContent"]
        self.assertEqual(result["default_count"], 1)
        self.assertEqual(self.fake.calls, [
            ("controller_scenario_differences", None),
            ("controller_scenario_differences", None)])

    def test_controller_threat_severity_http_and_mcp_are_time_bounded(self) -> None:
        start_ms, end_ms = 1794903300000, 1794904500000
        path = (f"/v1/controller/threat-severity-summary?start_ms={start_ms}"
                f"&end_ms={end_ms}")
        self.assertEqual(self.request(path)[0], 401)
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "controller_threat_severity_summary")
        request = {"jsonrpc": "2.0", "id": 109, "method": "tools/call",
                   "params": {"name": "omada_controller_threat_severity_summary",
                              "arguments": {"start_ms": start_ms, "end_ms": end_ms}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        result = response["result"]["structuredContent"]
        self.assertEqual(result["counts"], {"critical": 0, "major": 1,
                                             "moderate": 2, "minor": 3, "low": 4})
        self.assertEqual(self.fake.calls, [
            ("controller_threat_severity_summary", start_ms, end_ms),
            ("controller_threat_severity_summary", start_ms, end_ms),
        ])
        for bad in (
            f"/v1/controller/threat-severity-summary?start_ms={end_ms}&end_ms={start_ms}",
            f"/v1/controller/threat-severity-summary?start_ms={start_ms}&end_ms={start_ms + 86400001}",
            f"/v1/controller/threat-severity-summary?start_ms={start_ms}&end_ms={end_ms}&extra=1",
        ):
            self.assertNotEqual(self.request(bad, self.token)[0], 200)
        self.assertEqual(len(self.fake.calls), 2)

    def test_site_threat_window_http_and_mcp_are_site_bound(self) -> None:
        site_ref = "a" * 24
        start_ms, end_ms = 1794903300000, 1794904500000
        path = (f"/v1/sites/{site_ref}/threats/window?start_ms={start_ms}"
                f"&end_ms={end_ms}&archived=true")
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_threat_window_summary")
        request = {"jsonrpc": "2.0", "id": 110, "method": "tools/call",
                   "params": {"name": "omada_site_threat_window_summary",
                              "arguments": {"site_ref": site_ref,
                                            "start_ms": start_ms,
                                            "end_ms": end_ms,
                                            "archived": True}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_threat_window_summary")
        self.assertEqual(self.fake.calls, [
            ("site_threat_window_summary", site_ref, start_ms, end_ms, True),
            ("site_threat_window_summary", site_ref, start_ms, end_ms, True),
        ])
        for bad in (
            f"/v1/sites/{site_ref}/threats/window?start_ms={end_ms}&end_ms={start_ms}&archived=false",
            f"/v1/sites/{site_ref}/threats/window?start_ms={start_ms}&end_ms={end_ms}&archived=maybe",
            f"/v1/sites/{site_ref}/threats/window?start_ms={start_ms}&end_ms={end_ms}&archived=false&extra=1",
        ):
            self.assertNotEqual(self.request(bad, self.token)[0], 200)
        self.assertEqual(len(self.fake.calls), 2)

    def test_http_and_mcp_expose_controller_client_recognition(self) -> None:
        status, response = self.request("/v1/controller/settings/client-recognition", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_client_recognition")
        self.assertIs(response["data"]["enabled"], True)
        request = {"jsonrpc": "2.0", "id": 88, "method": "tools/call",
                   "params": {"name": "omada_controller_client_recognition", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_client_recognition")
        self.assertEqual(self.fake.calls, [("controller_client_recognition", None)] * 2)

    def test_http_and_mcp_expose_controller_device_statistics(self) -> None:
        status, response = self.request("/v1/controller/devices/statistics", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_device_statistics")
        self.assertEqual(response["data"]["counts"]["total_devices"], 4)
        request = {"jsonrpc": "2.0", "id": 89, "method": "tools/call",
                   "params": {"name": "omada_controller_device_statistics", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_device_statistics")
        self.assertEqual(self.fake.calls,
                         [("controller_device_statistics", None)] * 2)

    def test_http_and_mcp_expose_controller_client_active_timeout(self) -> None:
        status, response = self.request("/v1/controller/settings/client-active-timeout", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_client_active_timeout")
        self.assertEqual(response["data"]["active_timeout_minutes"], 5)
        request = {"jsonrpc": "2.0", "id": 90, "method": "tools/call",
                   "params": {"name": "omada_controller_client_active_timeout", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_client_active_timeout")
        self.assertEqual(self.fake.calls,
                         [("controller_client_active_timeout", None)] * 2)

    def test_http_and_mcp_expose_controller_history_and_audit_reads(self) -> None:
        for operation, endpoint, tool in (
                ("controller_client_history_retention", "/v1/controller/settings/client-history",
                 "omada_controller_client_history_retention"),
                ("controller_audit_notification", "/v1/controller/settings/audit-notification",
                 "omada_controller_audit_notification")):
            with self.subTest(operation=operation):
                status, response = self.request(endpoint, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation)
                request = {"jsonrpc": "2.0", "id": 901, "method": "tools/call",
                           "params": {"name": tool, "arguments": {}}}
                status, response = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
        self.assertEqual(self.fake.calls,
                         [("controller_client_history_retention", None)] * 2 +
                         [("controller_audit_notification", None)] * 2)

    def test_http_and_mcp_expose_controller_ui_interface(self) -> None:
        status, response = self.request("/v1/controller/settings/ui-interface", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_ui_interface")
        self.assertEqual(response["data"]["settings"]["time_zone_code"], 1)
        request = {"jsonrpc": "2.0", "id": 91, "method": "tools/call",
                   "params": {"name": "omada_controller_ui_interface", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_ui_interface")
        self.assertEqual(self.fake.calls, [("controller_ui_interface", None)] * 2)

    def test_http_and_mcp_expose_controller_retention(self) -> None:
        status, response = self.request("/v1/controller/settings/retention", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_retention")
        self.assertTrue(response["data"]["flags"]["clients_data_enable"])
        request = {"jsonrpc": "2.0", "id": 92, "method": "tools/call",
                   "params": {"name": "omada_controller_retention", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_retention")
        self.assertEqual(self.fake.calls, [("controller_retention", None)] * 2)

    def test_http_and_mcp_expose_controller_dst_info(self) -> None:
        status, response = self.request("/v1/controller/dst-info", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_dst_info")
        self.assertFalse(response["partial"])
        request = {"jsonrpc": "2.0", "id": 93, "method": "tools/call",
                   "params": {"name": "omada_controller_dst_info", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_dst_info")
        self.assertEqual(self.fake.calls, [("controller_dst_info", None)] * 2)

    def test_http_and_mcp_expose_site_dst_info(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/dst-info", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_dst_info")
        self.assertEqual(response["site_ref"], site_ref)
        self.assertEqual(response["data"]["timestamps_unit_unspecified"], {"startTime": 123})
        self.assertEqual(response["data"]["timestamps_ms"], {"nextStart": 456})
        self.assertFalse(response["partial"])
        request = {"jsonrpc": "2.0", "id": 94, "method": "tools/call",
                   "params": {"name": "omada_site_dst_info", "arguments": {
                       "site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "site_dst_info")
        self.assertEqual(response["result"]["structuredContent"]["data"][
            "timestamps_unit_unspecified"], {"startTime": 123})
        self.assertEqual(response["result"]["structuredContent"]["data"][
            "timestamps_ms"], {"nextStart": 456})
        self.assertEqual(self.fake.calls,
                         [("site_dst_info", site_ref), ("site_dst_info", site_ref)])

    def test_http_and_mcp_expose_controller_experience_improvement(self) -> None:
        status, response = self.request(
            "/v1/controller/settings/experience-improvement", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_experience_improvement")
        self.assertFalse(response["data"]["experience_improvement_enabled"])
        request = {"jsonrpc": "2.0", "id": 94, "method": "tools/call",
                   "params": {"name": "omada_controller_experience_improvement", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_experience_improvement")
        self.assertEqual(self.fake.calls,
                         [("controller_experience_improvement", None)] * 2)

    def test_http_and_mcp_expose_firmware_email_reminder_status(self) -> None:
        status, response = self.request(
            "/v1/controller/firmware-email-reminder/status", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_firmware_email_reminder_status")
        self.assertFalse(response["data"]["firmware_email_reminder_enabled"])
        request = {"jsonrpc": "2.0", "id": 95, "method": "tools/call",
                   "params": {"name": "omada_controller_firmware_email_reminder_status",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_firmware_email_reminder_status")
        self.assertEqual(self.fake.calls,
                         [("controller_firmware_email_reminder_status", None)] * 2)

    def test_http_and_mcp_expose_controller_client_detail_info(self) -> None:
        status, response = self.request(
            "/v1/controller/client-detail-information", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_client_detail_info")
        self.assertTrue(response["data"]["settings"]["client_history_enable"])
        request = {"jsonrpc": "2.0", "id": 95, "method": "tools/call",
                   "params": {"name": "omada_controller_client_detail_info", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_client_detail_info")
        self.assertEqual(self.fake.calls,
                         [("controller_client_detail_info", None)] * 2)

    def test_http_and_mcp_expose_controller_general_settings(self) -> None:
        status, response = self.request("/v1/controller/settings/general", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_general_settings")
        self.assertEqual(response["data"]["settings"]["time_zone"], "Europe/Berlin")
        request = {"jsonrpc": "2.0", "id": 96, "method": "tools/call",
                   "params": {"name": "omada_controller_general_settings", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_general_settings")
        self.assertEqual(self.fake.calls,
                         [("controller_general_settings", None)] * 2)

    def test_http_and_mcp_expose_controller_device_access(self) -> None:
        status, response = self.request("/v1/controller/settings/device-access", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_device_access")
        self.assertFalse(response["data"]["settings"]["web_control_http"])
        request = {"jsonrpc": "2.0", "id": 97, "method": "tools/call",
                   "params": {"name": "omada_controller_device_access", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_device_access")
        self.assertEqual(self.fake.calls, [("controller_device_access", None)] * 2)

    def test_http_and_mcp_expose_controller_device_adoption_tip_counts(self) -> None:
        status, response = self.request(
            "/v1/controller/device-adoption-tip/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_device_adoption_tip_summary")
        self.assertEqual(response["data"], {
            "adopted_device_count": 0, "recommended_device_count": 2,
        })
        request = {"jsonrpc": "2.0", "id": 98, "method": "tools/call",
                   "params": {"name": "omada_controller_device_adoption_tip_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["resource"], "controller_device_adoption_tip_summary")
        self.assertEqual(structured["data"]["adopted_device_count"], 0)
        self.assertEqual(self.fake.calls,
                         [("controller_device_adoption_tip_summary", None)] * 2)

    def test_http_and_mcp_expose_redacted_controller_placed_site_coverage(self) -> None:
        path = "/v1/controller/placed-site-position-coverage"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_placed_site_position_coverage")
        self.assertEqual(response["placed_site_row_count"], 2)
        self.assertFalse(response["server_completeness_established"])
        request = {"jsonrpc": "2.0", "id": 103, "method": "tools/call",
                   "params": {"name": "omada_controller_placed_site_position_coverage",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["resource"], "controller_placed_site_position_coverage")
        self.assertEqual(structured["placed_site_row_count"], 2)
        self.assertEqual(self.fake.calls,
                         [("controller_placed_site_position_coverage", None)] * 2)

    def test_http_and_mcp_expose_redacted_controller_unplaced_site_coverage(self) -> None:
        path = "/v1/controller/unplaced-site-position-coverage"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_unplaced_site_position_coverage")
        self.assertEqual(response["returned_count"], 1)
        self.assertFalse(response["partial"])
        request = {"jsonrpc": "2.0", "id": 104, "method": "tools/call",
                   "params": {"name": "omada_controller_unplaced_site_position_coverage",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["resource"], "controller_unplaced_site_position_coverage")
        self.assertEqual(structured["reported_total_rows"], 1)
        self.assertEqual(self.fake.calls,
                         [("controller_unplaced_site_position_coverage", None)] * 2)

    def test_http_and_mcp_expose_controller_client_correction_options(self) -> None:
        source = {
            "typeList": [{"key": f"type-{index}-\\\"", "name": f"Modèle 🛠 {index}"}
                         for index in range(140)],
            "vendorList": [{"key": f"vendor-{index}-\\\"", "name": f"Fábric 🛠 {index}"}
                           for index in range(1100)],
        }
        self.fake.correction_options_result = {
            "status": "ok", "resource": "controller_client_correction_options_summary",
            **project_controller_client_correction_options(source),
        }
        status, response = self.request(
            "/v1/controller/client-correction-options/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_client_correction_options_summary")
        self.assertEqual(response["data"]["type_option_count"], 140)
        self.assertEqual(response["data"]["vendor_option_count"], 1100)
        http_response_bytes = self.last_response_bytes
        self.correction_http_response_bytes = http_response_bytes
        self.assertNotIn("🛠".encode(), self.last_response_raw)
        self.assertLess(http_response_bytes, main._MAX_HTTP_RESPONSE_BYTES)
        request = {"jsonrpc": "2.0", "id": 144, "method": "tools/call",
                   "params": {"name": "omada_controller_client_correction_options_summary",
                              "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["resource"], "controller_client_correction_options_summary")
        self.assertEqual(structured["data"]["type_option_count"], 140)
        self.assertEqual(structured["data"]["vendor_option_count"], 1100)
        mcp_response_bytes = self.last_response_bytes
        self.correction_mcp_response_bytes = mcp_response_bytes
        self.assertLess(mcp_response_bytes, main._MAX_HTTP_RESPONSE_BYTES)
        self.assertGreater(mcp_response_bytes, http_response_bytes)
        self.assertEqual(self.last_response_raw.count("🛠".encode()), 2 * (140 + 1100))
        self.assertNotIn("icon", repr(response))
        self.assertNotIn("icon", repr(structured))
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]), structured)
        self.assertEqual(self.fake.calls,
                         [("controller_client_correction_options_summary", None)] * 2)

    def test_controller_client_correction_mcp_transport_limit_for_unicode_rich_rows(self) -> None:
        for count in (300, 350, 485):
            source = {
                "typeList": [{"key": f"key-{index}", "name": "🛠" * 128}
                             for index in range(count)],
                "vendorList": [],
            }
            upstream_bytes = len(json.dumps(source, ensure_ascii=False,
                                             separators=(",", ":")).encode("utf-8"))
            self.assertLess(upstream_bytes, 262_144)
            if count == 485:
                self.assertGreater(upstream_bytes, 261_000)
            self.fake.correction_options_result = {
                "status": "ok", "resource": "controller_client_correction_options_summary",
                **project_controller_client_correction_options(source),
            }
            if count == 350:
                original_send = main.Handler._send

                def ascii_only_send(handler, response_status, body, *, ensure_ascii=True):
                    return original_send(handler, response_status, body, ensure_ascii=True)

                with patch.object(main.Handler, "_send", ascii_only_send):
                    old_status, old_response = self.request_post(
                        "/mcp",
                        {"jsonrpc": "2.0", "id": count - 1, "method": "tools/call",
                         "params": {"name": "omada_controller_client_correction_options_summary",
                                    "arguments": {}}},
                        self.token,
                    )
                self.assertEqual(old_status, 502)
                self.assertEqual(old_response,
                                 {"error": "response_too_large", "status": "error"})
            status, response = self.request_post(
                "/mcp",
                {"jsonrpc": "2.0", "id": count, "method": "tools/call",
                 "params": {"name": "omada_controller_client_correction_options_summary",
                            "arguments": {}}},
                self.token,
            )
            self.assertEqual(status, 200)
            self.assertGreater(self.last_response_bytes, 300_000 if count == 300 else 0)
            self.assertLessEqual(self.last_response_bytes, main._MAX_HTTP_RESPONSE_BYTES)
            self.assertEqual(self.last_response_raw.count("🛠".encode()), 2 * count * 128)
            self.assertEqual(json.loads(response["result"]["content"][0]["text"]),
                             response["result"]["structuredContent"])

        escape_heavy = {
            "typeList": [{"key": f"key-{index}", "name": '"\\' * 64}
                         for index in range(920)],
            "vendorList": [],
        }
        upstream_bytes = len(json.dumps(escape_heavy, ensure_ascii=False,
                                        separators=(",", ":")).encode("utf-8"))
        self.assertGreater(upstream_bytes, 261_000)
        self.assertLess(upstream_bytes, 262_144)
        self.fake.correction_options_result = {
            "status": "ok", "resource": "controller_client_correction_options_summary",
            **project_controller_client_correction_options(escape_heavy),
        }
        status, response = self.request_post(
            "/mcp",
            {"jsonrpc": "2.0", "id": 920, "method": "tools/call",
             "params": {"name": "omada_controller_client_correction_options_summary",
                        "arguments": {}}},
            self.token,
        )
        self.assertEqual(status, 200)
        self.assertLessEqual(self.last_response_bytes, main._MAX_HTTP_RESPONSE_BYTES)
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]),
                         response["result"]["structuredContent"])

    def test_other_mcp_tools_keep_ascii_escaped_outer_response(self) -> None:
        self.fake.controller_scenarios_result = {
            "status": "ok", "resource": "controller_scenarios",
            "scenario_count": 1, "items": ["🛠"], "partial": False,
        }
        request = {"jsonrpc": "2.0", "id": 201, "method": "tools/call",
                   "params": {"name": "omada_controller_scenarios", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("🛠".encode(), self.last_response_raw)
        structured = response["result"]["structuredContent"]
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]), structured)

        self.fake.correction_options_result = {
            "status": "error", "resource": "controller_client_correction_options_summary",
            "diagnostic": "🛠",
        }
        correction_request = {
            "jsonrpc": "2.0", "id": 202, "method": "tools/call",
            "params": {"name": "omada_controller_client_correction_options_summary",
                       "arguments": {}},
        }
        status, response = self.request_post("/mcp", correction_request, self.token)
        self.assertEqual(status, 200)
        self.assertIs(response["result"]["isError"], True)
        self.assertNotIn("🛠".encode(), self.last_response_raw)

    def test_http_and_mcp_expose_backup_schedule_summary(self) -> None:
        status, response = self.request("/v1/controller/settings/backup-schedule", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_backup_schedule")
        self.assertEqual(response["data"]["retention_days"], 30)
        request = {"jsonrpc": "2.0", "id": 119, "method": "tools/call",
                   "params": {"name": "omada_controller_backup_schedule", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_backup_schedule")
        self.assertEqual(self.fake.calls, [("controller_backup_schedule", None)] * 2)

    def test_http_and_mcp_expose_cloud_access_summary(self) -> None:
        status, response = self.request("/v1/controller/cloud-access", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_cloud_access")
        request = {"jsonrpc": "2.0", "id": 120, "method": "tools/call",
                   "params": {"name": "omada_controller_cloud_access", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_cloud_access")
        self.assertEqual(self.fake.calls, [("controller_cloud_access", None)] * 2)

    def test_http_and_mcp_expose_device_management_summary(self) -> None:
        status, response = self.request("/v1/controller/settings/device-management", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_device_management")
        request = {"jsonrpc": "2.0", "id": 121, "method": "tools/call",
                   "params": {"name": "omada_controller_device_management", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_device_management")
        self.assertEqual(self.fake.calls, [("controller_device_management", None)] * 2)

    def test_http_and_mcp_expose_remote_binding_status(self) -> None:
        status, response = self.request("/v1/controller/cloud-binding", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_remote_binding")
        request = {"jsonrpc": "2.0", "id": 122, "method": "tools/call",
                   "params": {"name": "omada_controller_remote_binding", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_remote_binding")
        self.assertEqual(self.fake.calls, [("controller_remote_binding", None)] * 2)

    def test_http_and_mcp_expose_backup_result_status(self) -> None:
        status, response = self.request("/v1/controller/maintenance/backup-status", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["status"], "idle_or_finished")
        request = {"jsonrpc": "2.0", "id": 123, "method": "tools/call",
                   "params": {"name": "omada_controller_backup_result", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_backup_result")
        self.assertEqual(self.fake.calls, [("controller_backup_result", None)] * 2)

    def test_http_and_mcp_expose_restore_result_status(self) -> None:
        status, response = self.request("/v1/controller/maintenance/restore-status", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["status"], "prepared")
        request = {"jsonrpc": "2.0", "id": 124, "method": "tools/call",
                   "params": {"name": "omada_controller_restore_result", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_restore_result")
        self.assertEqual(self.fake.calls, [("controller_restore_result", None)] * 2)

    def test_http_and_mcp_expose_privacy_policy_state(self) -> None:
        status, response = self.request("/v1/controller/settings/privacy-policy", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["enabled"], True)
        request = {"jsonrpc": "2.0", "id": 125, "method": "tools/call",
                   "params": {"name": "omada_controller_privacy_policy", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_privacy_policy")
        self.assertEqual(self.fake.calls, [("controller_privacy_policy", None)] * 2)

    def test_http_and_mcp_expose_redacted_mail_status(self) -> None:
        status, response = self.request("/v1/controller/settings/mail-server-status", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["sender_configured"])
        request = {"jsonrpc": "2.0", "id": 126, "method": "tools/call",
                   "params": {"name": "omada_controller_mail_status", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_mail_status")
        self.assertEqual(self.fake.calls, [("controller_mail_status", None)] * 2)

    def test_http_and_mcp_expose_controller_global_mfa_status(self) -> None:
        status, response = self.request("/v1/controller/settings/mfa-status", self.token)
        self.assertEqual(status, 200, response)
        self.assertTrue(response["data"]["enabled"])
        request = {"jsonrpc": "2.0", "id": 128, "method": "tools/call",
                   "params": {"name": "omada_controller_global_mfa_status", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_global_mfa_status")
        self.assertEqual(self.fake.calls, [("controller_global_mfa_status", None)] * 2)

    def test_http_and_mcp_expose_bounded_msp_cloud_status(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/cloud-access", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_cloud_access_status")
        request = {"jsonrpc": "2.0", "id": 127, "method": "tools/call",
                   "params": {"name": "omada_msp_cloud_access_status",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_cloud_access_status")
        self.assertEqual(self.fake.calls,
                         [("msp_cloud_access_status", ref)] * 2)

    def test_http_and_mcp_expose_msp_privacy_policy(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/privacy-policy", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["enabled"])
        request = {"jsonrpc": "2.0", "id": 128, "method": "tools/call",
                   "params": {"name": "omada_msp_privacy_policy",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_privacy_policy")
        self.assertEqual(self.fake.calls, [("msp_privacy_policy", ref)] * 2)

    def test_http_and_mcp_expose_msp_client_detail_settings(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(
            f"/v1/msp/{ref}/client-detail-information", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["partial"])
        request = {"jsonrpc": "2.0", "id": 134, "method": "tools/call",
                   "params": {"name": "omada_msp_client_detail_info",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_client_detail_info")
        self.assertEqual(self.fake.calls, [("msp_client_detail_info", ref)] * 2)

    def test_http_and_mcp_expose_redacted_msp_audit_notification(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(
            f"/v1/msp/{ref}/settings/audit-notification", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_audit_notification")
        self.assertNotIn("webhook id", str(response).lower())
        request = {"jsonrpc": "2.0", "id": 135, "method": "tools/call",
                   "params": {"name": "omada_msp_audit_notification",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_audit_notification")
        self.assertEqual(self.fake.calls, [("msp_audit_notification", ref)] * 2)

    def test_http_and_mcp_expose_bounded_msp_device_link_topology(self) -> None:
        msp, customer, site, device = "msp-1", "customer-1", "a" * 24, "b" * 24
        route = f"/v1/msp/{msp}/customers/{customer}/sites/{site}/devices/{device}/link-topology"
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_device_link_topology")
        request = {"jsonrpc": "2.0", "id": 136, "method": "tools/call",
                   "params": {"name": "omada_msp_device_link_topology",
                               "arguments": {"msp_ref": msp, "customer_ref": customer,
                                             "site_ref": site, "device_ref": device}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_device_link_topology")
        expected = (msp, customer, site, device)
        self.assertEqual(self.fake.calls, [("msp_device_link_topology", expected)] * 2)

    def test_http_and_mcp_expose_redacted_msp_device_tags(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/device-tags-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_device_tags")
        request = {"jsonrpc": "2.0", "id": 137, "method": "tools/call",
                   "params": {"name": "omada_msp_device_tags",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_device_tags")
        self.assertEqual(self.fake.calls, [("msp_device_tags", ref)] * 2)

    def test_http_and_mcp_expose_msp_mfa_status(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/settings/mfa-status", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["enabled"])
        request = {"jsonrpc": "2.0", "id": 138, "method": "tools/call",
                   "params": {"name": "omada_msp_mfa_status",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"], "msp_mfa_status")
        self.assertEqual(self.fake.calls, [("msp_mfa_status", ref)] * 2)

    def test_http_and_mcp_expose_msp_license_auto_active(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(
            f"/v1/msp/{ref}/settings/license-auto-active", self.token)
        self.assertEqual(status, 200)
        self.assertFalse(response["data"]["enabled"])
        request = {"jsonrpc": "2.0", "id": 139, "method": "tools/call",
                   "params": {"name": "omada_msp_license_auto_active",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_license_auto_active")
        self.assertEqual(self.fake.calls, [("msp_license_auto_active", ref)] * 2)

    def test_http_and_mcp_expose_redacted_msp_customer_roles(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/customer-roles-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_customer_roles")
        request = {"jsonrpc": "2.0", "id": 140, "method": "tools/call",
                   "params": {"name": "omada_msp_customer_roles",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_customer_roles")
        self.assertEqual(self.fake.calls, [("msp_customer_roles", ref)] * 2)

    def test_http_and_mcp_expose_msp_dst_info(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/dst-info", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_dst_info")
        request = {"jsonrpc": "2.0", "id": 130, "method": "tools/call",
                   "params": {"name": "omada_msp_dst_info",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_dst_info")
        self.assertEqual(self.fake.calls, [("msp_dst_info", ref)] * 2)

    def test_http_and_mcp_expose_msp_remote_logging(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/settings/remote-logging", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["settings"]["host_present"])
        request = {"jsonrpc": "2.0", "id": 131, "method": "tools/call",
                   "params": {"name": "omada_msp_remote_logging",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_remote_logging")
        self.assertEqual(self.fake.calls, [("msp_remote_logging", ref)] * 2)

    def test_http_and_mcp_expose_msp_mail_server(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/settings/mail-server", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_mail_server")
        request = {"jsonrpc": "2.0", "id": 132, "method": "tools/call",
                   "params": {"name": "omada_msp_mail_server",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_mail_server")
        self.assertEqual(self.fake.calls, [("msp_mail_server", ref)] * 2)

    def test_http_and_mcp_expose_msp_general_settings(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/settings/general", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_general_settings")
        request = {"jsonrpc": "2.0", "id": 133, "method": "tools/call",
                   "params": {"name": "omada_msp_general_settings",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_general_settings")
        self.assertEqual(self.fake.calls, [("msp_general_settings", ref)] * 2)

    def test_http_and_mcp_expose_msp_log_notification_settings(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/settings/log-notifications", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_log_notification_settings")
        request = {"jsonrpc": "2.0", "id": 134, "method": "tools/call",
                   "params": {"name": "omada_msp_log_notification_settings",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_log_notification_settings")
        self.assertEqual(self.fake.calls, [("msp_log_notification_settings", ref)] * 2)

    def test_http_and_mcp_expose_msp_data_retention(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/settings/retention", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_data_retention")
        request = {"jsonrpc": "2.0", "id": 135, "method": "tools/call",
                   "params": {"name": "omada_msp_data_retention",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_data_retention")
        self.assertEqual(self.fake.calls, [("msp_data_retention", ref)] * 2)

    def test_http_and_mcp_expose_msp_ui_interface(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/settings/ui-interface", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_ui_interface")
        request = {"jsonrpc": "2.0", "id": 136, "method": "tools/call",
                   "params": {"name": "omada_msp_ui_interface",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"], "msp_ui_interface")
        self.assertEqual(self.fake.calls, [("msp_ui_interface", ref)] * 2)

    def test_http_and_mcp_expose_msp_user_interface(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/settings/user-interface", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_user_interface")
        request = {"jsonrpc": "2.0", "id": 137, "method": "tools/call",
                   "params": {"name": "omada_msp_user_interface",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"], "msp_user_interface")
        self.assertEqual(self.fake.calls, [("msp_user_interface", ref)] * 2)

    def test_http_and_mcp_expose_msp_available_roles(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/roles/available-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_available_roles")
        request = {"jsonrpc": "2.0", "id": 138, "method": "tools/call",
                   "params": {"name": "omada_msp_available_roles",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_available_roles")
        self.assertEqual(self.fake.calls, [("msp_available_roles", ref)] * 2)

    def test_http_and_mcp_expose_msp_available_customer_roles(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(
            f"/v1/msp/{ref}/roles/customer/available-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_available_customer_roles")
        request = {"jsonrpc": "2.0", "id": 139, "method": "tools/call",
                   "params": {"name": "omada_msp_available_customer_roles",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_available_customer_roles")
        self.assertEqual(self.fake.calls, [("msp_available_customer_roles", ref)] * 2)

    def test_http_and_mcp_expose_msp_dashboard_overall(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/dashboard/client-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_dashboard_overall")
        request = {"jsonrpc": "2.0", "id": 140, "method": "tools/call",
                   "params": {"name": "omada_msp_dashboard_overall",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_dashboard_overall")
        self.assertEqual(self.fake.calls, [("msp_dashboard_overall", ref)] * 2)

    def test_http_and_mcp_expose_msp_cluster_nodes(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/cluster/nodes/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_cluster_nodes")
        request = {"jsonrpc": "2.0", "id": 141, "method": "tools/call",
                   "params": {"name": "omada_msp_cluster_nodes",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_cluster_nodes")
        self.assertEqual(self.fake.calls, [("msp_cluster_nodes", ref)] * 2)

    def test_http_and_mcp_expose_msp_adopt_tip(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(
            f"/v1/msp/{ref}/devices/adoption-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_adopt_tip")
        request = {"jsonrpc": "2.0", "id": 142, "method": "tools/call",
                   "params": {"name": "omada_msp_adopt_tip",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_adopt_tip")
        self.assertEqual(self.fake.calls, [("msp_adopt_tip", ref)] * 2)

    def test_http_and_mcp_expose_msp_role_summary(self) -> None:
        ref = "msp-id_safe"
        status, response = self.request(f"/v1/msp/{ref}/roles/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "msp_role_summary")
        request = {"jsonrpc": "2.0", "id": 143, "method": "tools/call",
                   "params": {"name": "omada_msp_role_summary",
                               "arguments": {"msp_ref": ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "msp_role_summary")
        self.assertEqual(self.fake.calls, [("msp_role_summary", ref)] * 2)

    def test_mcp_rejects_msp_reference_path_syntax(self) -> None:
        request = {"jsonrpc": "2.0", "id": 129, "method": "tools/call",
                   "params": {"name": "omada_msp_cloud_access_status",
                               "arguments": {"msp_ref": "../secret"}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertIn("error", rpc)
        self.assertEqual(self.fake.calls, [])

    def test_http_and_mcp_expose_redacted_controller_remote_logging(self) -> None:
        status, response = self.request("/v1/controller/settings/remote-logging", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_remote_logging")
        self.assertTrue(response["data"]["settings"]["enabled"])
        self.assertNotIn("192.0.2.8", json.dumps(response))
        request = {"jsonrpc": "2.0", "id": 98, "method": "tools/call",
                   "params": {"name": "omada_controller_remote_logging", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_remote_logging")
        self.assertNotIn("192.0.2.8", json.dumps(response))
        self.assertEqual(self.fake.calls, [("controller_remote_logging", None)] * 2)

    def test_http_and_mcp_expose_redacted_remote_logging_tip(self) -> None:
        status, response = self.request("/v1/controller/settings/remote-logging-tip", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_remote_logging_tip")
        self.assertTrue(response["data"]["settings"]["enabled"])
        request = {"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                   "params": {"name": "omada_controller_remote_logging_tip", "arguments": {}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "controller_remote_logging_tip")
        self.assertEqual(self.fake.calls, [("controller_remote_logging_tip", None)] * 2)

    def test_http_and_mcp_expose_redacted_radius_proxy_settings(self) -> None:
        path = "/v1/controller/settings/radius-proxy"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_radius_proxy")
        self.assertTrue(response["data"]["settings"]["failure_reason_present"])
        self.assertNotIn("private startup detail", json.dumps(response))
        request = {"jsonrpc": "2.0", "id": 100, "method": "tools/call",
                   "params": {"name": "omada_controller_radius_proxy", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_radius_proxy")
        self.assertEqual(self.fake.calls, [("controller_radius_proxy", None)] * 2)

    def test_radius_proxy_http_error_is_generic_and_does_not_leak(self) -> None:
        with patch.object(self.fake, "read_controller_radius_proxy",
                          side_effect=OpenApiError("controller_error")):
            status, response = self.request(
                "/v1/controller/settings/radius-proxy", self.token)
        self.assertEqual(status, 502)
        self.assertEqual(response["error"], "controller_error")
        self.assertNotIn("shared-secret", json.dumps(response))

    def test_radius_proxy_change_preview_http_and_mcp_are_read_only(self) -> None:
        with patch.object(main, "_CONTROLLER_RADIUS_PROXY_PLANS", None), \
                patch.object(main, "_JOURNAL_RUNTIME", None):
            status, preview = self.request_post(
                "/v1/controller/settings/radius-proxy-preview",
                {"changes": {"enable": True}}, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(preview["patch"], {"enable": True, "port": 0})
            self.assertFalse(preview["writes_enabled"])
            self.assertEqual(preview["approval_request"]["operation"],
                             "controller-radius-proxy")
            rpc = {"jsonrpc": "2.0", "id": 102, "method": "tools/call",
                   "params": {"name": "omada_controller_radius_proxy_change",
                              "arguments": {"action": "preview",
                                            "changes": {"port": 1813}}}}
            status, response = self.request_post("/mcp", rpc, self.token)
            self.assertEqual(status, 200)
            content = response["result"]["structuredContent"]
            self.assertEqual(content["status"], "pending")
            self.assertEqual(content["scope"], "controller_radius_proxy")
            self.assertEqual(content["patch"], {"enable": False, "port": 1813})
            self.assertEqual(self.fake.calls,
                             [("controller_radius_proxy", None)] * 2)

    def test_http_and_mcp_expose_redacted_radius_server_settings(self) -> None:
        status, response = self.request("/v1/controller/settings/radius-server", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_radius_server")
        self.assertTrue(response["data"]["redacted_presence"]["secret"])
        request = {"jsonrpc": "2.0", "id": 101, "method": "tools/call",
                   "params": {"name": "omada_controller_radius_server", "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_radius_server")
        self.assertEqual(self.fake.calls, [("controller_radius_server", None)] * 2)

    def test_radius_server_http_error_is_generic(self) -> None:
        with patch.object(self.fake, "read_controller_radius_server",
                          side_effect=OpenApiError("controller_error")):
            status, response = self.request(
                "/v1/controller/settings/radius-server", self.token)
        self.assertEqual(status, 502)
        self.assertEqual(response["error"], "controller_error")

    def test_http_and_mcp_expose_redacted_site_radius_user_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/radius-users/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_radius_user_summary")
        self.assertEqual(response["data"]["user_count"], 2)
        request = {"jsonrpc": "2.0", "id": 104, "method": "tools/call",
                   "params": {"name": "omada_site_radius_user_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_radius_user_summary")
        self.assertEqual(self.fake.calls,
                         [("site_radius_user_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_site_entity_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/metadata/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_entity_summary")
        self.assertEqual(response["data"]["site_tier"], "basic")
        request = {"jsonrpc": "2.0", "id": 106, "method": "tools/call",
                   "params": {"name": "omada_site_entity_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_entity_summary")
        self.assertEqual(self.fake.calls, [("site_entity_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_switch_qos_mode(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/switches/qos-mode", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_switch_qos_mode")
        request = {"jsonrpc": "2.0", "id": 144, "method": "tools/call",
                   "params": {"name": "omada_site_switch_qos_mode",
                               "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_switch_qos_mode")
        self.assertEqual(self.fake.calls, [("site_switch_qos_mode", site_ref)] * 2)

    def test_http_and_mcp_expose_site_switch_qos_mapping_summaries(self) -> None:
        site_ref = "a" * 24
        for operation, route in (
                ("site_switch_qos_scheduler_summary", "scheduler-summary"),
                ("site_switch_qos_dscp_summary", "dscp-summary")):
            with self.subTest(operation=operation):
                status, response = self.request(
                    f"/v1/sites/{site_ref}/switches/qos/{route}", self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["resource"], operation)
                request = {"jsonrpc": "2.0", "id": 145, "method": "tools/call",
                           "params": {"name": "omada_" + operation,
                                       "arguments": {"site_ref": site_ref}}}
                status, rpc = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(rpc["result"]["structuredContent"]["resource"], operation)
                self.assertEqual(self.fake.calls[-2:], [(operation, site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_site_iptv_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/services/iptv-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_iptv_summary")
        self.assertEqual(response["data"]["port_type_counts"]["iptv"], 1)
        request = {"jsonrpc": "2.0", "id": 113, "method": "tools/call",
                   "params": {"name": "omada_site_iptv_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"], "site_iptv_summary")
        self.assertEqual(self.fake.calls, [("site_iptv_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_template_upnp_summary(self) -> None:
        template_ref = "c" * 24
        status, response = self.request(
            f"/v1/site-templates/{template_ref}/settings/upnp-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_template_upnp_summary")
        self.assertEqual(response["data"]["network_count"], 2)
        request = {"jsonrpc": "2.0", "id": 116, "method": "tools/call",
                   "params": {"name": "omada_site_template_upnp_summary",
                              "arguments": {"site_template_ref": template_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_template_upnp_summary")
        self.assertEqual(self.fake.calls, [("site_template_upnp_summary", template_ref)] * 2)

    def test_http_and_mcp_expose_site_template_ssh_summary(self) -> None:
        template_ref = "d" * 24
        status, response = self.request(
            f"/v1/site-templates/{template_ref}/settings/ssh-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_template_ssh_summary")
        self.assertEqual(response["data"]["server_port"], 22)
        request = {"jsonrpc": "2.0", "id": 117, "method": "tools/call",
                   "params": {"name": "omada_site_template_ssh_summary",
                              "arguments": {"site_template_ref": template_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_template_ssh_summary")
        self.assertEqual(self.fake.calls, [("site_template_ssh_summary", template_ref)] * 2)

    def test_http_and_mcp_expose_site_template_iptv_summary(self) -> None:
        template_ref = "e" * 24
        status, response = self.request(
            f"/v1/site-templates/{template_ref}/services/iptv-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_template_iptv_summary")
        self.assertEqual(response["data"]["port_count"], 1)
        request = {"jsonrpc": "2.0", "id": 118, "method": "tools/call",
                   "params": {"name": "omada_site_template_iptv_summary",
                              "arguments": {"site_template_ref": template_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_template_iptv_summary")
        self.assertEqual(self.fake.calls, [("site_template_iptv_summary", template_ref)] * 2)

    def test_http_and_mcp_expose_site_template_iptv_settings_summary(self) -> None:
        template_ref = "f" * 24
        status, response = self.request(
            f"/v1/site-templates/{template_ref}/services/iptv-settings-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_template_iptv_settings_summary")
        self.assertEqual(response["data"]["igmp"]["version"], 2)
        request = {"jsonrpc": "2.0", "id": 119, "method": "tools/call",
                   "params": {"name": "omada_site_template_iptv_settings_summary",
                              "arguments": {"site_template_ref": template_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_template_iptv_settings_summary")
        self.assertEqual(self.fake.calls,
                         [("site_template_iptv_settings_summary", template_ref)] * 2)

    def test_http_and_mcp_expose_site_template_list_and_igmp(self) -> None:
        status, inventory = self.request("/v1/site-templates", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(inventory["resource"], "site_templates")
        template_ref = "b" * 24
        status, response = self.request(
            f"/v1/site-templates/{template_ref}/services/igmp-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_template_igmp_summary")
        request = {"jsonrpc": "2.0", "id": 115, "method": "tools/call",
                   "params": {"name": "omada_site_template_igmp_summary",
                              "arguments": {"site_template_ref": template_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertIn("result", rpc, repr(rpc))
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_template_igmp_summary")
        self.assertEqual(self.fake.calls, [("site_templates", None),
                         ("site_template_igmp_summary", template_ref),
                         ("site_template_igmp_summary", template_ref)])

    def test_http_and_mcp_expose_site_igmp_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/services/igmp-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_igmp_summary")
        self.assertEqual(response["data"]["version"], 3)
        request = {"jsonrpc": "2.0", "id": 114, "method": "tools/call",
                   "params": {"name": "omada_site_igmp_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"], "site_igmp_summary")
        self.assertEqual(self.fake.calls, [("site_igmp_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_mld_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/services/mld-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_mld_summary")
        self.assertEqual(response["data"]["version"], 2)
        request = {"jsonrpc": "2.0", "id": 112, "method": "tools/call",
                   "params": {"name": "omada_site_mld_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"], "site_mld_summary")
        self.assertEqual(self.fake.calls, [("site_mld_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_ssh_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/settings/ssh-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_ssh_summary")
        self.assertEqual(response["data"]["server_port"], 22)
        request = {"jsonrpc": "2.0", "id": 111, "method": "tools/call",
                   "params": {"name": "omada_site_ssh_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"], "site_ssh_summary")
        self.assertEqual(self.fake.calls, [("site_ssh_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_site_ssl_vpn_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/settings/ssl-vpn-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_ssl_vpn_summary")
        self.assertEqual(response["data"]["service_port"], 443)
        request = {"jsonrpc": "2.0", "id": 110, "method": "tools/call",
                   "params": {"name": "omada_site_ssl_vpn_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_ssl_vpn_summary")
        self.assertEqual(self.fake.calls, [("site_ssl_vpn_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_site_gre_tunnel_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/settings/gre-tunnel-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_gre_tunnel_summary")
        self.assertEqual(response["data"]["tunnel_mtu"], 1400)
        request = {"jsonrpc": "2.0", "id": 109, "method": "tools/call",
                   "params": {"name": "omada_site_gre_tunnel_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_gre_tunnel_summary")
        self.assertEqual(self.fake.calls, [("site_gre_tunnel_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_site_upnp_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/settings/upnp-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_upnp_summary")
        self.assertEqual(response["data"]["network_count"], 2)
        request = {"jsonrpc": "2.0", "id": 108, "method": "tools/call",
                   "params": {"name": "omada_site_upnp_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_upnp_summary")
        self.assertEqual(self.fake.calls, [("site_upnp_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_iot_aging_time(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/iot/aging-time-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"], {"aging_value": 3600, "unit": "seconds"})
        request = {"jsonrpc": "2.0", "id": 129, "method": "tools/call",
                   "params": {"name": "omada_site_iot_aging_time",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_iot_aging_time")
        self.assertEqual(self.fake.calls, [("site_iot_aging_time", site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_site_iot_radio_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/iot/radio-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["bluetooth_enabled"])
        request = {"jsonrpc": "2.0", "id": 130, "method": "tools/call",
                   "params": {"name": "omada_site_iot_radio_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_iot_radio_summary")
        self.assertEqual(self.fake.calls, [("site_iot_radio_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_mesh_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/mesh-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["mesh_enabled"])
        request = {"jsonrpc": "2.0", "id": 131, "method": "tools/call",
                   "params": {"name": "omada_site_mesh_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"], "site_mesh_summary")
        self.assertEqual(self.fake.calls, [("site_mesh_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_multicast_rate_limit_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/multicast-rate-limit-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["igmp_packets_per_second"], 120)
        request = {"jsonrpc": "2.0", "id": 132, "method": "tools/call",
                   "params": {"name": "omada_site_multicast_rate_limit_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_multicast_rate_limit_summary")
        self.assertEqual(self.fake.calls,
                         [("site_multicast_rate_limit_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_beacon_control_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/beacon-control-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["beacon_interval_2g"], 100)
        request = {"jsonrpc": "2.0", "id": 133, "method": "tools/call",
                   "params": {"name": "omada_site_beacon_control_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_beacon_control_summary")
        self.assertEqual(self.fake.calls,
                         [("site_beacon_control_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_iot_transmit_power_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/iot/transmit-power-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["observed_row_count"], 2)
        request = {"jsonrpc": "2.0", "id": 134, "method": "tools/call",
                   "params": {"name": "omada_site_iot_transmit_power_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_iot_transmit_power_summary")
        self.assertEqual(self.fake.calls,
                         [("site_iot_transmit_power_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_bluetooth_advertising_v2_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/bluetooth-advertising-v2-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["observed_row_count"], 1)
        request = {"jsonrpc": "2.0", "id": 136, "method": "tools/call",
                   "params": {"name": "omada_site_bluetooth_advertising_v2_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_bluetooth_advertising_v2_summary")
        self.assertEqual(self.fake.calls,
                         [("site_bluetooth_advertising_v2_summary", site_ref)] * 2)

    def test_site_bluetooth_advertising_v2_errors_stay_public_and_redacted(self) -> None:
        site_ref = "a" * 24
        failure = OpenApiError("openapi_response_invalid")
        with patch.object(self.fake, "read_site_bluetooth_advertising_v2_summary",
                          side_effect=failure):
            status, response = self.request(
                f"/v1/sites/{site_ref}/bluetooth-advertising-v2-summary", self.token)
            self.assertEqual(status, 502)
            self.assertEqual(response["error"], "openapi_response_invalid")
            status, rpc = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": 137, "method": "tools/call",
                "params": {"name": "omada_site_bluetooth_advertising_v2_summary",
                           "arguments": {"site_ref": site_ref}},
            }, self.token)
        self.assertEqual(status, 200)
        self.assertTrue(rpc["result"]["isError"])
        self.assertEqual(rpc["result"]["structuredContent"]["error"],
                         "openapi_response_invalid")

    def test_http_and_mcp_expose_site_remember_setting_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/remember-setting-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["remember_enabled"])
        request = {"jsonrpc": "2.0", "id": 135, "method": "tools/call",
                   "params": {"name": "omada_site_remember_setting_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_remember_setting_summary")
        self.assertEqual(self.fake.calls,
                         [("site_remember_setting_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_client_connection_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-connection-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wireless_client_count"], 34)
        request = {"jsonrpc": "2.0", "id": 136, "method": "tools/call",
                   "params": {"name": "omada_site_client_connection_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_connection_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_connection_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_poe_usage_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/poe-usage-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["total_power_used_watts"], 92)
        request = {"jsonrpc": "2.0", "id": 137, "method": "tools/call",
                   "params": {"name": "omada_site_poe_usage_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_poe_usage_summary")
        self.assertEqual(self.fake.calls, [("site_poe_usage_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_poe_schedule_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/poe/schedule-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_poe_schedule_summary")
        self.assertEqual(
            response["source_contract"],
            "detailed_feed_fields_documented_in_all_three_exports; descriptions_and_numeric_wrappers_vary")
        request = {"jsonrpc": "2.0", "id": 139, "method": "tools/call",
                   "params": {"name": "omada_site_poe_schedule_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_poe_schedule_summary")
        self.assertEqual(
            rpc["result"]["structuredContent"]["source_contract"],
            "detailed_feed_fields_documented_in_all_three_exports; descriptions_and_numeric_wrappers_vary")
        self.assertEqual(self.fake.calls,
                         [("site_poe_schedule_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_bounded_site_port_schedule_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/port-schedules/summary?page_number=1&page_size=25",
            self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["reported_schedule_count"], 2)
        request = {"jsonrpc": "2.0", "id": 140, "method": "tools/call",
                   "params": {"name": "omada_site_port_schedule_summary",
                              "arguments": {"site_ref": site_ref,
                                            "page_number": 1, "page_size": 25}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_port_schedule_summary")
        self.assertEqual(self.fake.calls,
                         [("site_port_schedule_summary", site_ref, 1, 25)] * 2)

    def test_http_and_mcp_expose_selected_routing_table_type(self) -> None:
        site_ref = "a" * 24
        route = (f"/v1/sites/{site_ref}/routing-table/summary?device_type=switch&"
                 "page_number=0&page_size=20")
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200, repr(response))
        self.assertEqual(response["device_type"], "switch")
        request = {"jsonrpc": "2.0", "id": 141, "method": "tools/call",
                   "params": {"name": "omada_site_routing_table_summary",
                              "arguments": {"site_ref": site_ref, "device_type": "switch",
                                            "page_number": 0, "page_size": 20}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"].get("resource"),
                         "site_routing_table_summary", repr(rpc))
        self.assertEqual(self.fake.calls,
                         [("site_routing_table_summary", site_ref, "switch", 0, 20)] * 2)

    def test_http_and_mcp_expose_site_device_counts_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/device-counts-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["total_device_count"], 15)
        request = {"jsonrpc": "2.0", "id": 138, "method": "tools/call",
                   "params": {"name": "omada_site_device_counts_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_device_counts_summary")
        self.assertEqual(self.fake.calls,
                         [("site_device_counts_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_ipsec_tunnel_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/ipsec-tunnel-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["tunnel_count"], 2)
        request = {"jsonrpc": "2.0", "id": 139, "method": "tools/call",
                   "params": {"name": "omada_site_ipsec_tunnel_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_ipsec_tunnel_summary")
        self.assertEqual(self.fake.calls,
                         [("site_ipsec_tunnel_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_client_association_time_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-association-time-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["failed_association_count"], 1)
        request = {"jsonrpc": "2.0", "id": 140, "method": "tools/call",
                   "params": {"name": "omada_site_client_association_time_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_association_time_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_association_time_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_network_activity_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/network-activity-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["total_traffic"], 2000)
        request = {"jsonrpc": "2.0", "id": 141, "method": "tools/call",
                   "params": {"name": "omada_site_network_activity_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_network_activity_summary")
        self.assertEqual(self.fake.calls,
                         [("site_network_activity_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_client_rssi_distribution_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-rssi-distribution-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["band_5_ghz"]["less_than_72"], 2)
        request = {"jsonrpc": "2.0", "id": 142, "method": "tools/call",
                   "params": {"name": "omada_site_client_rssi_distribution_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_rssi_distribution_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_rssi_distribution_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_ap_rssi_density_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/ap-rssi-density-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["ap_count_in_buckets"], 7)
        request = {"jsonrpc": "2.0", "id": 143, "method": "tools/call",
                   "params": {"name": "omada_site_ap_rssi_density_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_ap_rssi_density_summary")
        self.assertEqual(self.fake.calls,
                         [("site_ap_rssi_density_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_client_attachment_distribution_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-attachment-distribution-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["access_point_attached_client_count"], 8)
        request = {"jsonrpc": "2.0", "id": 144, "method": "tools/call",
                   "params": {"name": "omada_site_client_attachment_distribution_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_attachment_distribution_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_attachment_distribution_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_client_frequency_distribution_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-frequency-distribution-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wireless_client_count"], 12)
        request = {"jsonrpc": "2.0", "id": 145, "method": "tools/call",
                   "params": {"name": "omada_site_client_frequency_distribution_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_frequency_distribution_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_frequency_distribution_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_device_traffic_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/device-traffic-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["ap_traffic_mb"], 50.0)
        request = {"jsonrpc": "2.0", "id": 146, "method": "tools/call",
                   "params": {"name": "omada_site_device_traffic_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_device_traffic_summary")
        self.assertEqual(self.fake.calls,
                         [("site_device_traffic_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_past_client_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/past-client-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wireless_client_count"], 23)
        request = {"jsonrpc": "2.0", "id": 147, "method": "tools/call",
                   "params": {"name": "omada_site_past_client_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_past_client_summary")
        self.assertEqual(self.fake.calls,
                         [("site_past_client_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_current_client_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/current-client-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wireless_client_count"], 13)
        request = {"jsonrpc": "2.0", "id": 148, "method": "tools/call",
                   "params": {"name": "omada_site_current_client_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_current_client_summary")
        self.assertEqual(self.fake.calls,
                         [("site_current_client_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_gateway_isp_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/gateway-isp-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["maximum_download_utilization_percent"], 81.25)
        request = {"jsonrpc": "2.0", "id": 149, "method": "tools/call",
                   "params": {"name": "omada_site_gateway_isp_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_gateway_isp_summary")
        self.assertEqual(self.fake.calls,
                         [("site_gateway_isp_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_top_ap_retry_drop_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/top-ap-retry-drop-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["top_ap_by_rt_count"], 2)
        request = {"jsonrpc": "2.0", "id": 150, "method": "tools/call",
                   "params": {"name": "omada_site_top_ap_retry_drop_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_top_ap_retry_drop_summary")
        self.assertEqual(self.fake.calls,
                         [("site_top_ap_retry_drop_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_active_ap_and_switch_summaries(self) -> None:
        site_ref = "a" * 24
        for operation, route, expected in (
            ("site_active_ap_summary", "active-ap-summary", 3.5),
            ("site_active_switch_summary", "active-switch-summary", 7.0),
        ):
            status, response = self.request(f"/v1/sites/{site_ref}/{route}", self.token)
            self.assertEqual(status, 200)
            self.assertEqual(response["data"]["total_traffic_value"], expected)
            request = {"jsonrpc": "2.0", "id": 151, "method": "tools/call",
                       "params": {"name": f"omada_{operation}",
                                  "arguments": {"site_ref": site_ref}}}
            status, rpc = self.request_post("/mcp", request, self.token)
            self.assertEqual(status, 200)
            self.assertEqual(rpc["result"]["structuredContent"]["resource"], operation)
        self.assertEqual(self.fake.calls, [
            ("site_active_ap_summary", site_ref), ("site_active_ap_summary", site_ref),
            ("site_active_switch_summary", site_ref),
            ("site_active_switch_summary", site_ref),
        ])

    def test_http_and_mcp_expose_site_device_memory_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/device-memory-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["maximum_memory_usage_percent"], 91)
        request = {"jsonrpc": "2.0", "id": 152, "method": "tools/call",
                   "params": {"name": "omada_site_device_memory_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_device_memory_summary")
        self.assertEqual(self.fake.calls,
                         [("site_device_memory_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_switch_dashboard_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/switch-dashboard-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["total_traffic_bytes"], 123456)
        request = {"jsonrpc": "2.0", "id": 153, "method": "tools/call",
                   "params": {"name": "omada_site_switch_dashboard_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_switch_dashboard_summary")
        self.assertEqual(self.fake.calls,
                         [("site_switch_dashboard_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_ap_interference_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/ap-interference-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["2g_maximum_interference_value"], 62)
        request = {"jsonrpc": "2.0", "id": 154, "method": "tools/call",
                   "params": {"name": "omada_site_ap_interference_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_ap_interference_summary")
        self.assertEqual(self.fake.calls,
                         [("site_ap_interference_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_application_category_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/application-category-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["has_more_category_rows"])
        request = {"jsonrpc": "2.0", "id": 155, "method": "tools/call",
                   "params": {"name": "omada_site_application_category_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_application_category_summary")
        self.assertEqual(self.fake.calls,
                         [("site_application_category_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_application_family_inventory(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/application-families", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["family_refs"], ["0", "2147483647"])
        request = {"jsonrpc": "2.0", "id": 158, "method": "tools/call",
                   "params": {"name": "omada_site_application_family_inventory",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["data"]["family_refs"],
                         ["0", "2147483647"])
        self.assertEqual(self.fake.calls,
                         [("site_application_family_inventory", site_ref)] * 2)

    def test_http_and_mcp_serialize_missing_application_catalog_total(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/application-control/application-catalog"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertIsNone(response["reported_total_row_count"])
        self.assertTrue(response["partial"])
        request = {"jsonrpc": "2.0", "id": 160, "method": "tools/call",
                   "params": {"name": "omada_site_application_control_application_catalog",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        structured = rpc["result"]["structuredContent"]
        self.assertEqual(structured["resource"], "site_application_control_application_catalog")
        self.assertIsNone(structured["reported_total_row_count"])
        self.assertTrue(structured["partial"])
        json.dumps(response, allow_nan=False)
        json.dumps(structured, allow_nan=False)
        self.assertEqual(self.fake.calls,
                         [("site_application_control_application_catalog", site_ref)] * 2)

    def test_http_and_mcp_distinguish_missing_filter_total_from_explicit_zero(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/application-control/filter-inventory/coverage"
        request = {"jsonrpc": "2.0", "id": 161, "method": "tools/call",
                   "params": {"name": "omada_site_application_control_filter_inventory_coverage",
                              "arguments": {"site_ref": site_ref}}}
        status, missing = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertIsNone(missing["reported_total_row_count"])
        self.assertTrue(missing["partial"])
        status, missing_rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        missing_structured = missing_rpc["result"]["structuredContent"]
        self.assertIsNone(missing_structured["reported_total_row_count"])
        self.assertTrue(missing_structured["partial"])

        self.fake.filter_inventory_total = 0
        request["id"] = 162
        status, zero = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(zero["reported_total_row_count"], 0)
        self.assertFalse(zero["partial"])
        status, zero_rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        zero_structured = zero_rpc["result"]["structuredContent"]
        self.assertEqual(zero_structured["reported_total_row_count"], 0)
        self.assertFalse(zero_structured["partial"])
        for value in (missing, missing_structured, zero, zero_structured):
            json.dumps(value, allow_nan=False)
        self.assertEqual(self.fake.calls,
                         [("site_application_control_filter_inventory_coverage", site_ref)] * 4)

    def test_http_and_mcp_expose_site_gateway_supported_model_references(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/gateway-supported-model-references"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["model_references"],
                         [{"model_id": 0, "model_name": ""}])
        request = {"jsonrpc": "2.0", "id": 159, "method": "tools/call",
                   "params": {"name": "omada_site_gateway_supported_model_references",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["data"]["model_references"],
                         [{"model_id": 0, "model_name": ""}])
        self.assertEqual(self.fake.calls,
                         [("site_gateway_supported_model_references", site_ref)] * 2)

    def test_http_and_mcp_expose_gateway_qos_service_reference_inventory(self) -> None:
        site_ref = "f" * 24
        path = f"/v1/sites/{site_ref}/gateway-qos/service-references/summary"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_gateway_qos_service_reference_inventory")
        self.assertEqual(response["row_count"], 2)
        self.assertNotIn("private-id", json.dumps(response))
        self.assertNotIn(site_ref, json.dumps(response))
        request = {"jsonrpc": "2.0", "id": 168, "method": "tools/call",
                   "params": {"name": "omada_site_gateway_qos_service_reference_inventory",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["row_count"], 2)
        self.assertNotIn("private-id", json.dumps(rpc))
        self.assertNotIn(site_ref, json.dumps(rpc))
        self.assertEqual(self.fake.calls, [
            ("site_gateway_qos_service_reference_inventory", site_ref),
            ("site_gateway_qos_service_reference_inventory", site_ref),
        ])

    def test_http_and_mcp_expose_site_category_application_summary(self) -> None:
        site_ref, family_id = "a" * 24, "17"
        path = f"/v1/sites/{site_ref}/application-category-summary/{family_id}/applications"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["application_count"], 2)
        request = {"jsonrpc": "2.0", "id": 156, "method": "tools/call",
                   "params": {"name": "omada_site_category_application_summary",
                              "arguments": {"site_ref": site_ref,
                                            "family_id": family_id}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_category_application_summary")
        self.assertEqual(self.fake.calls,
                         [("site_category_application_summary", site_ref, family_id)] * 2)

    def test_http_and_mcp_expose_site_category_client_summary(self) -> None:
        site_ref, family_id = "a" * 24, "17"
        path = f"/v1/sites/{site_ref}/application-category-summary/{family_id}/clients"
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["client_count"], 3)
        request = {"jsonrpc": "2.0", "id": 157, "method": "tools/call",
                   "params": {"name": "omada_site_category_client_summary",
                              "arguments": {"site_ref": site_ref,
                                            "family_id": family_id}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_category_client_summary")
        self.assertEqual(self.fake.calls,
                         [("site_category_client_summary", site_ref, family_id)] * 2)

    def test_http_and_mcp_expose_site_active_application_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/active-application-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["application_count"], 3)
        request = {"jsonrpc": "2.0", "id": 158, "method": "tools/call",
                   "params": {"name": "omada_site_active_application_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_active_application_summary")
        self.assertEqual(self.fake.calls,
                         [("site_active_application_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_active_ap_v2_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/active-ap-summary-v2", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["active_ap_count"], 2)
        request = {"jsonrpc": "2.0", "id": 169, "method": "tools/call",
                   "params": {"name": "omada_site_active_ap_v2_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_active_ap_v2_summary")
        self.assertEqual(self.fake.calls,
                         [("site_active_ap_v2_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_hotspot_statistics_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/hotspot-statistics-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["last_connection_sample_count"], 24)
        request = {"jsonrpc": "2.0", "id": 170, "method": "tools/call",
                   "params": {"name": "omada_site_hotspot_statistics_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_hotspot_statistics_summary")
        self.assertEqual(self.fake.calls,
                         [("site_hotspot_statistics_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_application_access_summaries(self) -> None:
        site_ref = "f" * 24
        for slug, operation, tool, count in (
            ("allowed", "site_allowed_application_summary",
             "omada_site_allowed_application_summary", 2),
            ("blocked", "site_blocked_application_summary",
             "omada_site_blocked_application_summary", 1),
        ):
            with self.subTest(slug=slug):
                route = f"/v1/sites/{site_ref}/application-usage/{slug}-summary?page_number=0&page_size=25"
                status, response = self.request(route, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["data"]["returned_application_count"], count)
                request = {"jsonrpc": "2.0", "id": 172 if slug == "allowed" else 173,
                           "method": "tools/call",
                           "params": {"name": tool,
                                      "arguments": {"site_ref": site_ref,
                                                    "page_number": 0, "page_size": 25}}}
                status, rpc = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(rpc["result"]["structuredContent"]["resource"], operation)
        self.assertEqual(self.fake.calls, [
            ("site_allowed_application_summary", site_ref, 0, 25),
            ("site_allowed_application_summary", site_ref, 0, 25),
            ("site_blocked_application_summary", site_ref, 0, 25),
            ("site_blocked_application_summary", site_ref, 0, 25),
        ])

    def test_http_and_mcp_expose_site_dashboard_tab_summaries(self) -> None:
        site_ref = "c" * 24
        for slug, operation, tool, expected in (
            ("tabs-summary", "site_dashboard_all_tabs_summary",
             "omada_site_dashboard_all_tabs_summary", 3),
            ("tabs-without-overall-summary", "site_dashboard_non_overall_tabs_summary",
             "omada_site_dashboard_non_overall_tabs_summary", 2),
        ):
            with self.subTest(slug=slug):
                status, response = self.request(
                    f"/v1/sites/{site_ref}/dashboard/{slug}", self.token)
                self.assertEqual(status, 200)
                self.assertEqual(response["data"]["tab_count"], expected)
                request = {"jsonrpc": "2.0", "id": 174 if expected == 3 else 175,
                           "method": "tools/call",
                           "params": {"name": tool, "arguments": {"site_ref": site_ref}}}
                status, rpc = self.request_post("/mcp", request, self.token)
                self.assertEqual(status, 200)
                self.assertEqual(rpc["result"]["structuredContent"]["resource"], operation)
        self.assertEqual(self.fake.calls, [
            ("site_dashboard_all_tabs_summary", site_ref),
            ("site_dashboard_all_tabs_summary", site_ref),
            ("site_dashboard_non_overall_tabs_summary", site_ref),
            ("site_dashboard_non_overall_tabs_summary", site_ref),
        ])

    def test_http_and_mcp_expose_site_specific_app_traffic_summary(self) -> None:
        site_ref, app_id = "b" * 24, "app_123"
        route = f"/v1/sites/{site_ref}/application-usage/{app_id}/traffic-summary"
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["traffic_total"], 99)
        request = {"jsonrpc": "2.0", "id": 176, "method": "tools/call",
                   "params": {"name": "omada_site_specific_app_traffic_summary",
                              "arguments": {"site_ref": site_ref,
                                            "application_id": app_id}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_specific_app_traffic_summary")
        self.assertEqual(self.fake.calls, [
            ("site_specific_app_traffic_summary", site_ref, app_id)] * 2)

    def test_http_and_mcp_expose_site_specific_client_traffic_summary(self) -> None:
        site_ref, client_ref = "a" * 24, "9" * 24
        route = f"/v1/sites/{site_ref}/client-application-usage/{client_ref}/traffic-summary"
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["traffic_total"], 17)
        request = {"jsonrpc": "2.0", "id": 177, "method": "tools/call",
                   "params": {"name": "omada_site_specific_client_traffic_summary",
                              "arguments": {"site_ref": site_ref, "client_ref": client_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_specific_client_traffic_summary")
        self.assertEqual(self.fake.calls, [
            ("site_specific_client_traffic_summary", site_ref, client_ref)] * 2)

    def test_http_and_mcp_expose_site_application_traffic_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/application-traffic-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["returned_application_count"], 2)
        request = {"jsonrpc": "2.0", "id": 178, "method": "tools/call",
                   "params": {"name": "omada_site_application_traffic_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_application_traffic_summary")
        self.assertEqual(self.fake.calls, [
            ("site_application_traffic_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wan_lan_status_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/wan-lan-status-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wan_port_count"], 1)
        request = {"jsonrpc": "2.0", "id": 179, "method": "tools/call",
                   "params": {"name": "omada_site_wan_lan_status_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_wan_lan_status_summary")
        self.assertEqual(self.fake.calls, [
            ("site_wan_lan_status_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_arp_detect_status_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/arp-detect-status-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["arp_detection_enabled"])
        request = {"jsonrpc": "2.0", "id": 181, "method": "tools/call",
                   "params": {"name": "omada_site_arp_detect_status_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_arp_detect_status_summary")
        self.assertEqual(self.fake.calls,
                         [("site_arp_detect_status_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_disaster_mode_status(self) -> None:
        site_ref = "c" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/disaster-mode-status", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["status_code"], 2)
        request = {"jsonrpc": "2.0", "id": 183, "method": "tools/call",
                   "params": {"name": "omada_site_disaster_mode_status",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_disaster_mode_status")
        self.assertEqual(self.fake.calls,
                         [("site_disaster_mode_status", site_ref)] * 2)

    def test_http_and_mcp_expose_site_specification_summary(self) -> None:
        site_ref = "d" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/specification-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["supported_interface_count"], 10)
        request = {"jsonrpc": "2.0", "id": 184, "method": "tools/call",
                   "params": {"name": "omada_site_specification_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_specification_summary")
        self.assertEqual(self.fake.calls,
                         [("site_specification_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_portal_logout_domain(self) -> None:
        site_ref = "e" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/portal-logout-domain", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"], {"domain": ""})
        request = {"jsonrpc": "2.0", "id": 185, "method": "tools/call",
                   "params": {"name": "omada_site_portal_logout_domain",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_portal_logout_domain")
        self.assertEqual(self.fake.calls,
                         [("site_portal_logout_domain", site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_site_portal_domain_setting_state(self) -> None:
        site_ref = "e" * 24
        status, direct = self.request(
            f"/v1/sites/{site_ref}/portal-domain-setting-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(direct["data"]["url_configured"])
        self.assertNotIn("url", direct["data"])
        request = {"jsonrpc": "2.0", "id": 186, "method": "tools/call",
                   "params": {"name": "omada_site_portal_domain_setting_state",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_portal_domain_setting_state", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wids_config(self) -> None:
        site_ref = "9" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/wireless-ids-config", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["detection_codes"], [0, 15, 17])
        request = {"jsonrpc": "2.0", "id": 186, "method": "tools/call",
                   "params": {"name": "omada_site_wids_config",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_wids_config")
        self.assertEqual(self.fake.calls,
                         [("site_wids_config", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wips_config(self) -> None:
        site_ref = "7" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/wireless-ips-config", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["lock_time_seconds"], 600)
        request = {"jsonrpc": "2.0", "id": 187, "method": "tools/call",
                   "params": {"name": "omada_site_wips_config",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_wips_config")
        self.assertEqual(self.fake.calls,
                         [("site_wips_config", site_ref)] * 2)

    def test_http_and_mcp_expose_site_acl_config_mode(self) -> None:
        site_ref = "5" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/acl-config-mode", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["mode_name"], "custom")
        request = {"jsonrpc": "2.0", "id": 188, "method": "tools/call",
                   "params": {"name": "omada_site_acl_config_mode",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_acl_config_mode")
        self.assertEqual(self.fake.calls,
                         [("site_acl_config_mode", site_ref)] * 2)

    def test_http_and_mcp_expose_site_attack_defense_summary(self) -> None:
        site_ref = "3" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/attack-defense-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["tcpConnLimit"], 1000)
        self.assertTrue(response["partial"])
        request = {"jsonrpc": "2.0", "id": 189, "method": "tools/call",
                   "params": {"name": "omada_site_attack_defense_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_attack_defense_summary")
        self.assertEqual(self.fake.calls,
                         [("site_attack_defense_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_attack_defense_defaults_summary(self) -> None:
        site_ref = "4" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/attack-defense/default-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["tcpConnEnable"])
        request = {"jsonrpc": "2.0", "id": 290, "method": "tools/call",
                   "params": {"name": "omada_site_attack_defense_defaults_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_attack_defense_defaults_summary")
        self.assertEqual(self.fake.calls,
                         [("site_attack_defense_defaults_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_wlan_group_detail_by_opaque_reference(self) -> None:
        site_ref, group_ref = "5" * 24, "6" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/wlan-groups/{group_ref}/detail", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["name"], "Office")
        request = {"jsonrpc": "2.0", "id": 291, "method": "tools/call",
                   "params": {"name": "omada_site_wlan_group_detail_summary",
                              "arguments": {"site_ref": site_ref,
                                            "wlan_group_ref": group_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_wlan_group_detail_summary")
        self.assertEqual(self.fake.calls,
                         [("site_wlan_group_detail_summary", site_ref, group_ref)] * 2)

    def test_http_and_mcp_expose_lock_to_ap_brief_inventory(self) -> None:
        site_ref = "7" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/lock-to-ap/ap-inventory", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["reported_ap_count"], 1)
        request = {"jsonrpc": "2.0", "id": 292, "method": "tools/call",
                   "params": {"name": "omada_site_lock_to_ap_brief_inventory",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_lock_to_ap_brief_inventory")
        self.assertEqual(self.fake.calls,
                         [("site_lock_to_ap_brief_inventory", site_ref)] * 2)

    def test_http_and_mcp_expose_ineligible_interference_ap_summary(self) -> None:
        site_ref = "9" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/wifi/interference-ineligible-ap-summary",
            self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["reported_ap_count"], 2)
        request = {"jsonrpc": "2.0", "id": 293, "method": "tools/call",
                   "params": {"name": "omada_site_ineligible_interference_ap_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_ineligible_interference_ap_summary")
        self.assertEqual(self.fake.calls,
                         [("site_ineligible_interference_ap_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_interference_scan_eligible_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/wifi/interference-scan-eligible-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["scan_status_counts"], {"0": 1, "2": 1})
        request = {"jsonrpc": "2.0", "id": 294, "method": "tools/call",
                   "params": {"name": "omada_site_interference_scan_eligible_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_interference_scan_eligible_summary")
        self.assertEqual(self.fake.calls,
                         [("site_interference_scan_eligible_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_alg_config(self) -> None:
        site_ref = "1" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/alg-config", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["ftp"], True)
        request = {"jsonrpc": "2.0", "id": 190, "method": "tools/call",
                   "params": {"name": "omada_site_alg_config",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_alg_config")
        self.assertEqual(self.fake.calls,
                         [("site_alg_config", site_ref)] * 2)

    def test_http_and_mcp_expose_site_firewall_settings(self) -> None:
        site_ref = "2" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/firewall-settings", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["icmp"], 100)
        self.assertTrue(response["partial"])
        request = {"jsonrpc": "2.0", "id": 191, "method": "tools/call",
                   "params": {"name": "omada_site_firewall_settings",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_firewall_settings")
        self.assertEqual(self.fake.calls,
                         [("site_firewall_settings", site_ref)] * 2)

    def test_http_and_mcp_expose_site_firewall_defaults(self) -> None:
        site_ref = "2" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/firewall-defaults", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["timeouts"]["icmp"], 30)
        request = {"jsonrpc": "2.0", "id": 204, "method": "tools/call",
                   "params": {"name": "omada_site_firewall_defaults",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_firewall_defaults")
        self.assertEqual(self.fake.calls,
                         [("site_firewall_defaults", site_ref)] * 2)

    def test_http_and_mcp_expose_site_bandwidth_control(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/bandwidth-control", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["returned_port_count"], 1)
        request = {"jsonrpc": "2.0", "id": 192, "method": "tools/call",
                   "params": {"name": "omada_site_bandwidth_control",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_bandwidth_control")
        self.assertEqual(self.fake.calls,
                         [("site_bandwidth_control", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wan_ports_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/wan-ports-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wan_port_count"], 1)
        request = {"jsonrpc": "2.0", "id": 193, "method": "tools/call",
                   "params": {"name": "omada_site_wan_ports_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_wan_ports_summary")
        self.assertEqual(self.fake.calls,
                         [("site_wan_ports_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_virtual_wan_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/virtual-wan-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_virtual_wan_summary")
        self.assertEqual(response["enabled_count"], 1)
        request = {"jsonrpc": "2.0", "id": 194, "method": "tools/call",
                   "params": {"name": "omada_site_virtual_wan_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_virtual_wan_summary")
        self.assertEqual(self.fake.calls,
                         [("site_virtual_wan_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wan_max_speed_summary(self) -> None:
        site_ref = "8" * 24
        wan_port_ref = "f" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/wan-ports/{wan_port_ref}/max-speed-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_wan_max_speed_summary")
        self.assertEqual(response["data"]["unit"], "unspecified_by_source")
        request = {"jsonrpc": "2.0", "id": 195, "method": "tools/call",
                   "params": {"name": "omada_site_wan_max_speed_summary",
                              "arguments": {"site_ref": site_ref,
                                            "wan_port_ref": wan_port_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_wan_max_speed_summary")
        self.assertEqual(self.fake.calls,
                         [("site_wan_max_speed_summary", site_ref + ":" + wan_port_ref)] * 2)

    def test_http_and_mcp_expose_site_vlan_network_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/vlan-network-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["returned_row_count"], 1)
        request = {"jsonrpc": "2.0", "id": 194, "method": "tools/call",
                   "params": {"name": "omada_site_vlan_network_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_vlan_network_summary")
        self.assertEqual(self.fake.calls,
                         [("site_vlan_network_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_scoped_lan_network_detail_summary(self) -> None:
        site_ref, network_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/lan-networks/{network_ref}/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_lan_network_detail_summary")
        self.assertEqual(direct["data"]["vlan"], 20)
        rpc = {"jsonrpc": "2.0", "id": 131, "method": "tools/call",
               "params": {"name": "omada_site_lan_network_detail_summary",
                          "arguments": {"site_ref": site_ref, "network_ref": network_ref}}}
        status, response = self.request_post("/mcp", rpc, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
            [("site_lan_network_detail_summary", site_ref + ":" + network_ref)] * 2)

    def test_http_and_mcp_expose_site_lan_network_config_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/lan-network-config-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["purpose_code_counts"], {"0": 1, "1": 1})
        request = {"jsonrpc": "2.0", "id": 206, "method": "tools/call",
                   "params": {"name": "omada_site_lan_network_config_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_lan_network_config_summary")
        self.assertEqual(self.fake.calls,
                         [("site_lan_network_config_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_lan_network_inventory(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/lan-networks/inventory", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["purpose_counts"], {"vlan": 1, "interface": 1})
        request = {"jsonrpc": "2.0", "id": 209, "method": "tools/call",
                   "params": {"name": "omada_site_lan_network_inventory",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["network_count"], 2)
        self.assertEqual(self.fake.calls,
                         [("site_lan_network_inventory", site_ref)] * 2)

    def test_http_and_mcp_expose_lan_client_inventory_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/lan-client-inventory/summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["coverage_complete"])
        request = {"jsonrpc": "2.0", "id": 231, "method": "tools/call",
                   "params": {"name": "omada_site_lan_client_inventory_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_lan_client_inventory_summary")
        self.assertEqual(self.fake.calls,
                         [("site_lan_client_inventory_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_topology_root_candidates_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/topology/root-candidates/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["root_candidate_count"], 1)
        request = {"jsonrpc": "2.0", "id": 232, "method": "tools/call",
                   "params": {"name": "omada_site_topology_root_candidates_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_topology_root_candidates_summary")
        self.assertEqual(self.fake.calls,
                         [("site_topology_root_candidates_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_isolated_preconfig_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/topology/isolated-preconfig/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["reported_total"], 1)
        request = {"jsonrpc": "2.0", "id": 233, "method": "tools/call",
                   "params": {"name": "omada_site_isolated_preconfig_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_isolated_preconfig_summary")
        self.assertEqual(self.fake.calls,
                         [("site_isolated_preconfig_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_network_bound_vlan_topology_summary(self) -> None:
        site_ref, network_ref = "8" * 24, "9" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/networks/{network_ref}/vlan-topology-summary?vlan_id=23",
            self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["vlan_id"], 23)
        request = {"jsonrpc": "2.0", "id": 234, "method": "tools/call",
                   "params": {"name": "omada_site_vlan_topology_summary",
                              "arguments": {"site_ref": site_ref,
                                            "network_ref": network_ref,
                                            "vlan_id": 23}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_vlan_topology_summary")
        self.assertEqual(self.fake.calls,
                         [("site_vlan_topology_summary",
                           f"{site_ref}:{network_ref}:23")] * 2)
        status, invalid = self.request(
            f"/v1/sites/{site_ref}/networks/{network_ref}/vlan-topology-summary?vlan_id=4095",
            self.token)
        self.assertEqual(status, 400)
        self.assertEqual(invalid["error"], "query_invalid")

    def test_http_and_mcp_expose_inventory_bound_es_network_overview(self) -> None:
        site_ref, switch_ref = "8" * 24, "9" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/switches/{switch_ref}/es-network-overview/summary",
            self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["total_port_assignment_count"], 5)
        request = {"jsonrpc": "2.0", "id": 235, "method": "tools/call",
                   "params": {"name": "omada_site_es_network_overview_summary",
                              "arguments": {"site_ref": site_ref,
                                            "switch_ref": switch_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_es_network_overview_summary")
        self.assertEqual(self.fake.calls,
                         [("site_es_network_overview_summary",
                           f"{site_ref}:{switch_ref}")] * 2)

    def test_http_and_mcp_expose_port_schedule_capable_ports(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/port-schedule-capable-ports/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["schedule_capable_port_count"], 5)
        request = {"jsonrpc": "2.0", "id": 236, "method": "tools/call",
                   "params": {"name": "omada_site_port_schedule_ports_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_port_schedule_ports_summary")
        self.assertEqual(self.fake.calls,
                         [("site_port_schedule_ports_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_longest_client_uptime_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/dashboard/longest-client-uptime-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["wirelessClient"], 9)
        request = {"jsonrpc": "2.0", "id": 210, "method": "tools/call",
                   "params": {"name": "omada_site_longest_client_uptime_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["total"], 12)
        self.assertEqual(self.fake.calls,
                         [("site_longest_client_uptime_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_internet_load_balance_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/internet/load-balance-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["application_optimized_routing_enabled"])
        request = {"jsonrpc": "2.0", "id": 207, "method": "tools/call",
                   "params": {"name": "omada_site_internet_load_balance_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_internet_load_balance_summary")
        self.assertEqual(self.fake.calls,
                         [("site_internet_load_balance_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_internet_basic_port_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/internet/basic-port-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["reported_port_count"], 2)
        request = {"jsonrpc": "2.0", "id": 208, "method": "tools/call",
                   "params": {"name": "omada_site_internet_basic_port_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_internet_basic_port_summary")
        self.assertEqual(self.fake.calls,
                         [("site_internet_basic_port_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wlan_group_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/wlan-group-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["reported_group_count"], 2)
        request = {"jsonrpc": "2.0", "id": 209, "method": "tools/call",
                   "params": {"name": "omada_site_wlan_group_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_wlan_group_summary")
        self.assertEqual(self.fake.calls,
                         [("site_wlan_group_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_wlan_group_ssids_summary(self) -> None:
        site_ref, group_ref = "8" * 24, "9" * 24
        route = f"/v1/sites/{site_ref}/wlan-groups/{group_ref}/ssids-summary"
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["returned_ssid_count"], 3)
        request = {"jsonrpc": "2.0", "id": 210, "method": "tools/call",
                   "params": {"name": "omada_site_wlan_group_ssids_summary",
                              "arguments": {"site_ref": site_ref,
                                            "wlan_group_ref": group_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_wlan_group_ssids_summary")
        self.assertEqual(self.fake.calls,
                         [("site_wlan_group_ssids_summary", site_ref, group_ref)] * 2)

    def test_http_and_mcp_expose_site_internet_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/internet-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["configured_wan_port_count"], 2)
        request = {"jsonrpc": "2.0", "id": 195, "method": "tools/call",
                   "params": {"name": "omada_site_internet_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_internet_summary")
        self.assertEqual(self.fake.calls,
                         [("site_internet_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_lte_wan_config_summary(self) -> None:
        site_ref = "8" * 24
        route = f"/v1/sites/{site_ref}/internet/lte-wan-config-summary"
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_lte_wan_config_summary")
        request = {"jsonrpc": "2.0", "id": 304, "method": "tools/call",
                   "params": {"name": "omada_site_lte_wan_config_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], response)
        self.assertEqual(self.fake.calls,
                         [("site_lte_wan_config_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_nat_exception_summary(self) -> None:
        site_ref = "8" * 24
        route = f"/v1/sites/{site_ref}/nat-exceptions/summary"
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_nat_exception_summary")
        self.assertEqual(response["enforcement_scope"],
                         "configuration_only_effective_enforcement_unknown")
        request = {"jsonrpc": "2.0", "id": 305, "method": "tools/call",
                   "params": {"name": "omada_site_nat_exception_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], response)
        self.assertEqual(self.fake.calls,
                         [("site_nat_exception_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_vpn_session_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/vpn-session-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["reported_session_count"], 2)
        request = {"jsonrpc": "2.0", "id": 196, "method": "tools/call",
                   "params": {"name": "omada_site_vpn_session_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_vpn_session_summary")
        self.assertEqual(self.fake.calls,
                         [("site_vpn_session_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_dhcp_candidate_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/dhcp-server-candidates", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["reported_total_candidate_count"], 3)
        request = {"jsonrpc": "2.0", "id": 197, "method": "tools/call",
                   "params": {"name": "omada_site_dhcp_candidate_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_dhcp_candidate_summary")
        self.assertEqual(self.fake.calls,
                         [("site_dhcp_candidate_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_network_reservation_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/dhcp-reservation-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["configured_range_count"], 3)
        request = {"jsonrpc": "2.0", "id": 198, "method": "tools/call",
                   "params": {"name": "omada_site_network_reservation_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_network_reservation_summary")
        self.assertEqual(self.fake.calls,
                         [("site_network_reservation_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_dhcp_reservation_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/dhcp-reservations-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["enabled_reservation_count"], 2)
        request = {"jsonrpc": "2.0", "id": 199, "method": "tools/call",
                   "params": {"name": "omada_site_dhcp_reservation_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_dhcp_reservation_summary")
        self.assertEqual(self.fake.calls,
                         [("site_dhcp_reservation_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_dhcp_snooping_status(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/dhcp-snooping-status", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["dhcp_snooping_enabled"])
        request = {"jsonrpc": "2.0", "id": 200, "method": "tools/call",
                   "params": {"name": "omada_site_dhcp_snooping_status",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_dhcp_snooping_status")
        self.assertEqual(self.fake.calls,
                         [("site_dhcp_snooping_status", site_ref)] * 2)

    def test_http_and_mcp_expose_site_dhcp_snoops_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/dhcp-snoops-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["device_type_counts"]["gateway"], 1)
        request = {"jsonrpc": "2.0", "id": 201, "method": "tools/call",
                   "params": {"name": "omada_site_dhcp_snoops_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_dhcp_snoops_summary")
        self.assertEqual(self.fake.calls,
                         [("site_dhcp_snoops_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_mdns_rule_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/mdns-rule-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["enabled_rule_count"], 1)
        request = {"jsonrpc": "2.0", "id": 202, "method": "tools/call",
                   "params": {"name": "omada_site_mdns_rule_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_mdns_rule_summary")
        self.assertEqual(self.fake.calls,
                         [("site_mdns_rule_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_mdns_profile_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/bonjour/profiles/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_mdns_profile_summary")
        request = {"jsonrpc": "2.0", "id": 204, "method": "tools/call",
                   "params": {"name": "omada_site_mdns_profile_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_mdns_profile_summary")
        self.assertEqual(self.fake.calls,
                         [("site_mdns_profile_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_ddns_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/ddns-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["enabled_ddns_count"], 1)
        request = {"jsonrpc": "2.0", "id": 203, "method": "tools/call",
                   "params": {"name": "omada_site_ddns_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_ddns_summary")
        self.assertEqual(self.fake.calls, [("site_ddns_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_snmp_settings_summary(self) -> None:
        site_ref = "8" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/snmp-summary", self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["snmp_v3_enabled"])
        self.assertEqual(response["data"]["security_level_code"], 2)
        request = {"jsonrpc": "2.0", "id": 205, "method": "tools/call",
                   "params": {"name": "omada_site_snmp_settings_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_snmp_settings_summary")
        self.assertEqual(self.fake.calls,
                         [("site_snmp_settings_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_controller_gateway_wan_status_summary(self) -> None:
        route = "/v1/controller/gateway-wan-status-summary?page_number=0&page_size=10"
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wan_port_count"], 1)
        request = {"jsonrpc": "2.0", "id": 180, "method": "tools/call",
                   "params": {"name": "omada_controller_gateway_wan_status_summary",
                              "arguments": {"page_number": 0, "page_size": 10}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_gateway_wan_status_summary")
        self.assertEqual(self.fake.calls, [
            ("controller_gateway_wan_status_summary", 0, 10)] * 2)

    def test_http_and_mcp_expose_site_active_client_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/active-client-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wireless_client_count"], 2)
        request = {"jsonrpc": "2.0", "id": 159, "method": "tools/call",
                   "params": {"name": "omada_site_active_client_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_active_client_summary")
        self.assertEqual(self.fake.calls,
                         [("site_active_client_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_cpu_usage_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/cpu-usage-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["maximum_cpu_util_value"], 70)
        request = {"jsonrpc": "2.0", "id": 160, "method": "tools/call",
                   "params": {"name": "omada_site_cpu_usage_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_cpu_usage_summary")
        self.assertEqual(self.fake.calls,
                         [("site_cpu_usage_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_client_bubble_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-bubble-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["average_client_rssi_value"], -60)
        request = {"jsonrpc": "2.0", "id": 161, "method": "tools/call",
                   "params": {"name": "omada_site_client_bubble_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_bubble_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_bubble_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_traffic_activity_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/traffic-activity-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["access_point_traffic"]["sample_count"], 3)
        request = {"jsonrpc": "2.0", "id": 162, "method": "tools/call",
                   "params": {"name": "omada_site_traffic_activity_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_traffic_activity_summary")
        self.assertEqual(self.fake.calls,
                         [("site_traffic_activity_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_isp_load_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/isp-load-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["mean_latency_ms"], 30)
        request = {"jsonrpc": "2.0", "id": 163, "method": "tools/call",
                   "params": {"name": "omada_site_isp_load_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_isp_load_summary")
        self.assertEqual(self.fake.calls,
                         [("site_isp_load_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_vpn_tunnel_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/vpn-tunnel-summary?vpn_type=0", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["total_tunnel_count"], 3)
        request = {"jsonrpc": "2.0", "id": 164, "method": "tools/call",
                   "params": {"name": "omada_site_vpn_tunnel_summary",
                              "arguments": {"site_ref": site_ref, "vpn_type": 0}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_vpn_tunnel_summary")
        self.assertEqual(self.fake.calls,
                         [("site_vpn_tunnel_summary", site_ref, 0)] * 2)

    def test_http_and_mcp_expose_site_open_vpn_tunnel_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/open-vpn-tunnel-summary?vpn_type=1", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["total_tunnel_count"], 2)
        request = {"jsonrpc": "2.0", "id": 165, "method": "tools/call",
                   "params": {"name": "omada_site_open_vpn_tunnel_summary",
                              "arguments": {"site_ref": site_ref, "vpn_type": 1}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_open_vpn_tunnel_summary")
        self.assertEqual(self.fake.calls,
                         [("site_open_vpn_tunnel_summary", site_ref, 1)] * 2)

    def test_http_and_mcp_expose_site_client_activity_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/client-activity-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["total_new_eap_clients"], 2)
        request = {"jsonrpc": "2.0", "id": 166, "method": "tools/call",
                   "params": {"name": "omada_site_client_activity_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_activity_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_activity_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_site_client_association_activity_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-association-activity-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["data"]["wireless_clients"], 9)
        request = {"jsonrpc": "2.0", "id": 167, "method": "tools/call",
                   "params": {"name": "omada_site_client_association_activity_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_association_activity_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_association_activity_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_bounded_site_client_traffic_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-traffic-summary?page_number=0&page_size=2",
            self.token)
        self.assertEqual(status, 200)
        self.assertTrue(response["data"]["has_more_pages"])
        request = {"jsonrpc": "2.0", "id": 168, "method": "tools/call",
                   "params": {"name": "omada_site_client_traffic_summary",
                              "arguments": {"site_ref": site_ref,
                                            "page_number": 0, "page_size": 2}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_client_traffic_summary")
        self.assertEqual(self.fake.calls,
                         [("site_client_traffic_summary", site_ref, 0, 2)] * 2)

    def test_http_and_mcp_expose_windowed_recent_client_counts(self) -> None:
        site_ref = "a" * 24
        start_ms, end_ms = 1790000000000, 1790000001000
        query = f"start_ms={start_ms}&end_ms={end_ms}"
        status, response = self.request(
            f"/v1/sites/{site_ref}/clients/recent-summary?{query}", self.token)
        self.assertEqual(status, 200, (repr(response), repr(self.fake.calls)))
        self.assertEqual(response["reported_client_count"], 7)
        request = {"jsonrpc": "2.0", "id": 169, "method": "tools/call",
                   "params": {"name": "omada_site_recent_clients_summary",
                              "arguments": {"site_ref": site_ref,
                                            "start_ms": start_ms, "end_ms": end_ms}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_recent_clients_summary")
        self.assertEqual(self.fake.calls,
                         [("site_recent_clients_summary", site_ref, start_ms, end_ms)] * 2)

    def test_http_and_mcp_expose_redacted_site_device_tag_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(f"/v1/sites/{site_ref}/device-tags/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_device_tag_summary")
        self.assertEqual(response["data"]["tag_count"], 2)
        request = {"jsonrpc": "2.0", "id": 105, "method": "tools/call",
                   "params": {"name": "omada_site_device_tag_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_device_tag_summary")
        self.assertEqual(self.fake.calls,
                         [("site_device_tag_summary", site_ref)] * 2)


    def test_authorized_routes_call_only_fixed_client_methods(self) -> None:
        status, sites = self.request("/v1/sites", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(sites["resource"], "sites")
        ref = sites["items"][0]["site_ref"]
        status, devices = self.request(f"/v1/sites/{ref}/devices", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(devices["resource"], "devices")
        status, clients = self.request(f"/v1/sites/{ref}/clients", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(clients["resource"], "clients")
        status, networks = self.request(f"/v1/sites/{ref}/networks", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(networks["resource"], "networks")
        status, ssids = self.request(f"/v1/sites/{ref}/ssids", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(ssids["resource"], "ssids")
        self.assertEqual(self.fake.calls, [("sites", None), ("devices", ref), ("clients", ref), ("networks", ref), ("ssids", ref)])

    def test_authorized_ap_radio_route_uses_fixed_part(self) -> None:
        site_ref, device_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/aps/{device_ref}/radios"
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "radios")
        self.assertEqual(self.fake.calls, [("radios", site_ref + ":" + device_ref)])
        self.assertNotIn(site_ref, self.logs.getvalue())
        self.assertNotIn(device_ref, self.logs.getvalue())

    def test_mac_auth_ssids_http_mcp_and_required_device_type(self) -> None:
        site_ref = "8" * 24
        base = f"/v1/sites/{site_ref}/wlan-ssids/mac-auth"
        self.assertEqual(self.request(base, self.token)[0], 400)
        self.assertEqual(self.request(base + "?type=4", self.token)[0], 400)
        status, body = self.request(base + "?type=3", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["items"], [
            {"wlan_name": "Office", "ssid_names": ["Staff", "Guest"]}])
        request = {"jsonrpc": "2.0", "id": 247, "method": "tools/call",
                   "params": {"name": "omada_site_mac_auth_ssid_inventory",
                              "arguments": {"site_ref": site_ref, "type": 3}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        value = rpc["result"]["structuredContent"]
        self.assertEqual(value["device_type"], 3)
        self.assertEqual(value["ssid_count"], 2)
        self.assertEqual(self.fake.calls,
                         [("site_mac_auth_ssid_inventory", site_ref, 3)] * 2)

    def test_missing_token_file_disables_routes(self) -> None:
        with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_path + ".missing"}):
            status, body = self.request("/v1/sites", self.token)
        self.assertEqual(status, 503)
        self.assertEqual(body["error"], "route_disabled")
        self.assertEqual(self.fake.calls, [])

    def test_short_token_file_disables_routes(self) -> None:
        with open(self.token_path, "w", encoding="utf-8") as handle:
            handle.write("too-short")
        status, body = self.request("/v1/sites", self.token)
        self.assertEqual(status, 503)
        self.assertEqual(body["error"], "route_disabled")
        self.assertEqual(self.fake.calls, [])

    def test_malformed_paths_are_rejected_without_client_call(self) -> None:
        for path in ("/v1/sites/not-a-ref/devices", "/v1/sites/" + "A" * 24 + "/devices",
                     "/v1/sites/not-a-ref/clients",
                     "/v1/sites/not-a-ref/networks",
                     "/v1/sites/not-a-ref/ssids",
                     "/v1/sites/" + "a" * 24 + "/clients?url=https://example.invalid",
                     "/v1/sites/" + "a" * 24 + "/devices?url=https://example.invalid",
                     "/v1/sites/" + "a" * 24 + "/aps/" + "b" * 24 + "/delete"):
            with self.subTest(path=path):
                status, body = self.request(path, self.token)
                self.assertEqual(status, 404)
                self.assertEqual(body["error"], "not_found")
        self.assertEqual(self.fake.calls, [])

    def test_token_never_appears_in_response_or_access_log(self) -> None:
        status, body = self.request("/v1/sites", "wrong-secret")
        self.assertEqual(status, 401, repr(body))
        self.assertNotIn(self.token, json.dumps(body))
        self.assertNotIn(self.token, self.logs.getvalue())

    def test_post_cannot_trigger_openapi_client(self) -> None:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request("POST", "/v1/sites", body=b"{}",
                           headers={"Authorization": "Bearer " + self.token})
        response = connection.getresponse()
        self.assertEqual(response.status, 501)
        response.read()
        connection.close()
        self.assertEqual(self.fake.calls, [])

    def test_disabled_diagnostic_actions_are_not_http_or_mcp_tools_but_saved_reads_remain(self) -> None:
        site_ref, ap_ref, gateway_ref = "a" * 24, "b" * 24, "d" * 24
        actions = (
            ("POST", f"/v1/sites/{site_ref}/aps/{ap_ref}/rf-scan/start", {}),
            ("POST", f"/v1/sites/{site_ref}/aps/{ap_ref}/full-channel-detect-start", {}),
            ("POST", f"/v1/sites/{site_ref}/full-channel-detect-start", {}),
            ("POST", f"/v1/sites/{site_ref}/aps/{ap_ref}/speed-test/start", {}),
            ("POST", f"/v1/sites/{site_ref}/gateways/{gateway_ref}/speed-test/start", {}),
            ("POST", f"/v1/sites/{site_ref}/capture/device-type/ap/{ap_ref}/start", {}),
            ("POST", f"/v1/sites/{site_ref}/switches/{ap_ref}/cable-test/start", {}),
            ("GET", f"/v1/sites/{site_ref}/capture/device-type/ap/{ap_ref}/stop", None),
            ("GET", f"/v1/sites/{site_ref}/capture/device-type/ap/{ap_ref}/download", None),
            ("DELETE", f"/v1/sites/{site_ref}/full-channel-detect", None),
            ("DELETE", f"/v1/sites/{site_ref}/full-channel-detect/history-1", None),
        )
        for method, path, body in actions:
            connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
            headers = {"Authorization": "Bearer " + self.token}
            encoded = None
            if body is not None:
                headers["Content-Type"] = "application/json"
                encoded = json.dumps(body)
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            connection.close()
            with self.subTest(method=method, path=path):
                self.assertIn(response.status, {404, 501})
                self.assertNotIn(b"errorCode", raw)
        self.assertEqual(self.fake.calls, [])

        denied_tools = (
            "omada_ap_rf_scan_start", "omada_ap_interference_detection_start",
            "omada_site_batch_interference_start", "omada_ap_speed_test_start",
            "omada_gateway_speed_test_start", "omada_package_capture_start",
            "omada_package_capture_stop", "omada_package_capture_download",
            "omada_full_channel_detect_history_delete",
            "omada_full_channel_detect_history_delete_all",
        )
        for name in denied_tools:
            status, rpc = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": 77, "method": "tools/call",
                "params": {"name": name, "arguments": {}},
            }, self.token)
            with self.subTest(tool=name):
                self.assertEqual(status, 200)
                self.assertEqual(rpc["error"]["code"], -32601)
        self.assertEqual(self.fake.calls, [])

        reads = (
            (f"/v1/sites/{site_ref}/aps/{ap_ref}/scan-status", "scan_status"),
            (f"/v1/sites/{site_ref}/aps/{ap_ref}/wifi-neighbors", "ap_wifi_neighbors"),
            (f"/v1/sites/{site_ref}/aps/{ap_ref}/speed-test-results", "ap_speed_test_results"),
            (f"/v1/sites/{site_ref}/gateways/{gateway_ref}/speed-test-results",
             "gateway_speed_test_results"),
        )
        for path, resource in reads:
            status, body = self.request(path, self.token)
            with self.subTest(read=path):
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], resource)
        self.assertEqual([name for name, _ in self.fake.calls], [
            "scan_status", "ap_wifi_neighbors", "ap_speed_test_results",
            "gateway_speed_test_results",
        ])
        self.fake.calls.clear()
        for name, arguments, resource in (
            ("omada_ap_scan_status", {"site_ref": site_ref, "device_ref": ap_ref}, "scan_status"),
            ("omada_ap_wifi_interference", {"site_ref": site_ref, "device_ref": ap_ref}, "ap_wifi_neighbors"),
            ("omada_ap_speed_test_results", {"site_ref": site_ref, "device_ref": ap_ref}, "ap_speed_test_results"),
            ("omada_gateway_speed_test_results", {"site_ref": site_ref, "device_ref": gateway_ref}, "gateway_speed_test_results"),
        ):
            status, rpc = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": 78, "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }, self.token)
            with self.subTest(mcp_read=name):
                self.assertEqual(status, 200)
                self.assertEqual(rpc["result"]["structuredContent"]["resource"], resource)

    def test_controller_system_port_reads_are_available_over_http_and_mcp(self) -> None:
        cases = (
            ("/v1/controller/settings/upgrade-port", "controller_upgrade_port"),
            ("/v1/controller/settings/portal-port", "controller_portal_port_settings"),
            ("/v1/controller/settings/controller-port", "controller_port_settings"),
            ("/v1/controller/status", "controller_status"),
            ("/v1/controller/settings/logging", "controller_logging"),
            ("/v1/controller/settings/certificate", "controller_certificate"),
        )
        for path, operation in cases:
            status, body = self.request(path, self.token)
            with self.subTest(http=path):
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], operation)
        self.assertEqual([name for name, _ in self.fake.calls], [op for _, op in cases])

        self.fake.calls.clear()
        cursor = None
        advertised: set[str] = set()
        page_id = 129
        while True:
            params = {} if cursor is None else {"cursor": cursor}
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": page_id, "method": "tools/list",
                "params": params,
            }, self.token)
            self.assertEqual(status, 200)
            advertised.update(tool["name"] for tool in response["result"]["tools"])
            cursor = response["result"].get("nextCursor")
            if cursor is None:
                break
            page_id += 1
        self.assertTrue({f"omada_{operation}" for _, operation in cases} <= advertised)
        for index, (_, operation) in enumerate(cases, start=130):
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": index, "method": "tools/call",
                "params": {"name": f"omada_{operation}", "arguments": {}},
            }, self.token)
            with self.subTest(mcp=operation):
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
        self.assertEqual([name for name, _ in self.fake.calls], [op for _, op in cases])

    def test_controller_role_reads_are_available_over_http_and_mcp(self) -> None:
        cases = (
            ("/v1/controller/roles/summary", "controller_roles"),
            ("/v1/controller/roles/available-summary", "controller_available_roles"),
        )
        for path, operation in cases:
            status, body = self.request(path, self.token)
            with self.subTest(http=path):
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], operation)
        self.assertEqual([name for name, _ in self.fake.calls], [op for _, op in cases])
        self.fake.calls.clear()
        for index, (_path, operation) in enumerate(cases, start=331):
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": index, "method": "tools/call",
                "params": {"name": f"omada_{operation}", "arguments": {}},
            }, self.token)
            with self.subTest(mcp=operation):
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
        self.assertEqual([name for name, _ in self.fake.calls], [op for _, op in cases])

    def test_global_device_summaries_are_available_over_http_and_mcp(self) -> None:
        cases = (
            ("/v1/controller/devices/known-summary", "controller_known_devices"),
            ("/v1/controller/devices/unknown-summary", "controller_unknown_devices"),
            ("/v1/controller/devices/batch-adopt-summary", "controller_device_batch_adopt_summary"),
        )
        for path, operation in cases:
            status, body = self.request(path, self.token)
            with self.subTest(http=path):
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], operation)
        self.assertEqual([name for name, _ in self.fake.calls], [op for _, op in cases])
        self.fake.calls.clear()
        for index, (_path, operation) in enumerate(cases, start=340):
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": index, "method": "tools/call",
                "params": {"name": f"omada_{operation}", "arguments": {}},
            }, self.token)
            with self.subTest(mcp=operation):
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
        self.assertEqual([name for name, _ in self.fake.calls], [op for _, op in cases])

    def test_site_pending_device_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/pending-devices/summary"
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_pending_devices_summary")
        self.assertEqual(self.fake.calls[-1], ("site_pending_devices_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 388, "method": "tools/call",
            "params": {"name": "omada_site_pending_devices_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(self.fake.calls[-1], ("site_pending_devices_summary", site_ref))

    def test_site_ap_group_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        status, body = self.request(f"/v1/sites/{site_ref}/ap-groups", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_ap_group_summary")
        self.assertEqual(self.fake.calls[-1], ("site_ap_group_summary", site_ref))

    def test_site_ap_group_assignment_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/ap-groups/aps/summary"
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_ap_group_assignment_summary")
        self.assertEqual(self.fake.calls[-1], ("site_ap_group_assignment_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 390, "method": "tools/call",
            "params": {"name": "omada_site_ap_group_assignment_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_ap_group_assignment_summary")
        self.assertEqual(self.fake.calls[-1], ("site_ap_group_assignment_summary", site_ref))

    def test_site_ap_group_info_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref, group_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/ap-groups/{group_ref}/info-summary"
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_ap_group_info_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_ap_group_info_summary", site_ref, group_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 391, "method": "tools/call",
            "params": {"name": "omada_site_ap_group_info_summary",
                       "arguments": {"site_ref": site_ref, "group_ref": group_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_ap_group_info_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_ap_group_info_summary", site_ref, group_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 389, "method": "tools/call",
            "params": {"name": "omada_site_ap_group_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_ap_group_summary")
        self.assertEqual(self.fake.calls[-1], ("site_ap_group_summary", site_ref))

    def test_site_ap_oui_vlan_rules_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        status, body = self.request(f"/v1/sites/{site_ref}/ap-oui-rules/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_ap_oui_vlan_rules_summary")
        self.assertEqual(self.fake.calls[-1], ("site_ap_oui_vlan_rules_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 390, "method": "tools/call",
            "params": {"name": "omada_site_ap_oui_vlan_rules_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_ap_oui_vlan_rules_summary")
        self.assertEqual(self.fake.calls[-1], ("site_ap_oui_vlan_rules_summary", site_ref))

    def test_site_oui_profile_list_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        status, body = self.request(f"/v1/sites/{site_ref}/oui-profiles/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_oui_profile_list_summary")
        self.assertEqual(self.fake.calls[-1], ("site_oui_profile_list_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 399, "method": "tools/call",
            "params": {"name": "omada_site_oui_profile_list_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_oui_profile_list_summary")
        self.assertEqual(self.fake.calls[-1], ("site_oui_profile_list_summary", site_ref))

    def test_site_group_profiles_coverage_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        status, body = self.request(
            f"/v1/sites/{site_ref}/group-profiles/coverage", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_group_profiles_coverage")
        self.assertEqual(self.fake.calls[-1],
                         ("site_group_profiles_coverage", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 400, "method": "tools/call",
            "params": {"name": "omada_site_group_profiles_coverage",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_group_profiles_coverage")
        self.assertEqual(self.fake.calls[-1],
                         ("site_group_profiles_coverage", site_ref))

    def test_site_vlan_ssid_usage_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref, network_ref = "a" * 24, "b" * 24
        route = f"/v1/sites/{site_ref}/networks/{network_ref}/vlan-ssids/summary?vlan_id=52"
        status, body = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_vlan_ssid_usage_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_vlan_ssid_usage_summary", site_ref, network_ref, 52))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 391, "method": "tools/call",
            "params": {"name": "omada_site_vlan_ssid_usage_summary",
                       "arguments": {"site_ref": site_ref, "network_ref": network_ref,
                                     "vlan_id": 52}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_vlan_ssid_usage_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_vlan_ssid_usage_summary", site_ref, network_ref, 52))
        status, _ = self.request(route.replace("vlan_id=52", "vlan_id=4095"), self.token)
        self.assertEqual(status, 400)

    def test_site_vlan_device_usage_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref, network_ref = "a" * 24, "b" * 24
        route = f"/v1/sites/{site_ref}/networks/{network_ref}/vlan-devices/summary?vlan_id=24"
        status, body = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_vlan_device_usage_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_vlan_device_usage_summary", site_ref, network_ref, 24))

    def test_site_vlan_affected_ports_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref, network_ref = "a" * 24, "b" * 24
        route = (f"/v1/sites/{site_ref}/networks/{network_ref}/"
                 "vlans/affected-ports-summary?vlan_id=52&page_number=0&page_size=10")
        status, body = self.request(route, self.token)
        self.assertEqual(status, 200, repr(body))
        self.assertEqual(body["resource"], "site_vlan_affected_ports_summary")
        self.assertTrue(body["partial"])
        self.assertEqual(self.fake.calls[-1],
                         ("site_vlan_affected_ports_summary", site_ref, network_ref, 52, 0, 10))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 395, "method": "tools/call",
            "params": {"name": "omada_site_vlan_affected_ports_summary",
                       "arguments": {"site_ref": site_ref, "network_ref": network_ref,
                                     "vlan_id": 52, "page_number": 0, "page_size": 10}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_vlan_affected_ports_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_vlan_affected_ports_summary", site_ref, network_ref, 52, 0, 10))

    def test_site_vlan_port_support_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref, network_ref = "a" * 24, "b" * 24
        route = (f"/v1/sites/{site_ref}/networks/{network_ref}/vlan-port-support/summary"
                 "?vlan_id=24")
        status, body = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_vlan_port_support_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_vlan_port_support_summary", site_ref, network_ref, 24))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 394, "method": "tools/call",
            "params": {"name": "omada_site_vlan_port_support_summary",
                       "arguments": {"site_ref": site_ref, "network_ref": network_ref,
                                     "vlan_id": 24}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_vlan_port_support_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_vlan_port_support_summary", site_ref, network_ref, 24))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 392, "method": "tools/call",
            "params": {"name": "omada_site_vlan_device_usage_summary",
                       "arguments": {"site_ref": site_ref, "network_ref": network_ref,
                                     "vlan_id": 24}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_vlan_device_usage_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_vlan_device_usage_summary", site_ref, network_ref, 24))

    def test_site_wifi_calling_profiles_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        status, body = self.request(
            f"/v1/sites/{site_ref}/wifi-calling/profiles/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_wifi_calling_profiles_summary")
        self.assertEqual(self.fake.calls[-1], ("site_wifi_calling_profiles_summary", site_ref))

    def test_site_wifi_calling_top_ssid_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        status, body = self.request(
            f"/v1/sites/{site_ref}/wifi-calling/top-ssid/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_wifi_calling_top_ssid_summary")
        self.assertEqual(self.fake.calls[-1], ("site_wifi_calling_top_ssid_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 394, "method": "tools/call",
            "params": {"name": "omada_site_wifi_calling_top_ssid_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_wifi_calling_top_ssid_summary")
        self.assertEqual(self.fake.calls[-1],
                         ("site_wifi_calling_top_ssid_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 393, "method": "tools/call",
            "params": {"name": "omada_site_wifi_calling_profiles_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_wifi_calling_profiles_summary")
        self.assertEqual(self.fake.calls[-1], ("site_wifi_calling_profiles_summary", site_ref))

    def test_site_client_filter_options_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        status, body = self.request(
            f"/v1/sites/{site_ref}/clients/filter-options/summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_client_filter_options_summary")
        self.assertEqual(self.fake.calls[-1], ("site_client_filter_options_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 394, "method": "tools/call",
            "params": {"name": "omada_site_client_filter_options_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_client_filter_options_summary")
        self.assertEqual(self.fake.calls[-1], ("site_client_filter_options_summary", site_ref))

    def test_site_eap_dot1x_candidates_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        route = f"/v1/sites/{site_ref}/dot1x/eap-candidates/summary"
        status, body = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_eap_dot1x_candidates_summary")
        self.assertEqual(self.fake.calls[-1], ("site_eap_dot1x_candidates_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 395, "method": "tools/call",
            "params": {"name": "omada_site_eap_dot1x_candidates_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_eap_dot1x_candidates_summary")
        self.assertEqual(self.fake.calls[-1], ("site_eap_dot1x_candidates_summary", site_ref))

    def test_site_switch_dot1x_candidates_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        route = f"/v1/sites/{site_ref}/dot1x/switch-candidates/summary"
        status, body = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "site_switch_dot1x_candidates_summary")
        self.assertEqual(self.fake.calls[-1], ("site_switch_dot1x_candidates_summary", site_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 396, "method": "tools/call",
            "params": {"name": "omada_site_switch_dot1x_candidates_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_switch_dot1x_candidates_summary")
        self.assertEqual(self.fake.calls[-1], ("site_switch_dot1x_candidates_summary", site_ref))

    def test_msp_olt_system_info_is_available_over_http_and_mcp(self) -> None:
        refs = {"msp_ref": "msp-1", "customer_ref": "customer-2",
                "site_ref": "a" * 24, "device_ref": "b" * 24}
        path = (f"/v1/msp/{refs['msp_ref']}/customers/{refs['customer_ref']}/sites/"
                f"{refs['site_ref']}/olts/{refs['device_ref']}/system-info")
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "olt_system_info_msp")
        self.assertEqual(self.fake.calls[-1][0], "olt_system_info_msp")
        self.fake.calls.clear()
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 190, "method": "tools/call",
            "params": {"name": "omada_olt_system_info_msp", "arguments": refs},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"], "olt_system_info_msp")
        self.assertEqual(self.fake.calls[-1][0], "olt_system_info_msp")

    def test_msp_device_health_details_are_available_over_http_and_mcp(self) -> None:
        common = {"msp_ref": "msp-1", "customer_ref": "customer-2", "site_ref": "a" * 24}
        cases = (
            ("msp_ap_health_detail", "aps", "device_ref"),
            ("msp_ap_mesh_statistics", "aps", "device_ref"),
            ("msp_gateway_health_detail", "gateways", "gateway_ref"),
            ("msp_switch_health_detail", "switches", "switch_ref"),
        )
        for operation, family, ref_name in cases:
            args = {**common, ref_name: "b" * 24}
            path = (f"/v1/msp/{common['msp_ref']}/customers/{common['customer_ref']}/sites/"
                    f"{common['site_ref']}/{family}/{args[ref_name]}/"
                    f"{'mesh' if operation == 'msp_ap_mesh_statistics' else 'health'}")
            status, body = self.request(path, self.token)
            with self.subTest(http=operation):
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], operation)
            self.fake.calls.clear()
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": 196, "method": "tools/call",
                "params": {"name": f"omada_{operation}", "arguments": args},
            }, self.token)
            with self.subTest(mcp=operation):
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
                self.assertEqual(self.fake.calls[-1][0], operation)

    def test_msp_olt_read_family_is_available_over_http_and_mcp(self) -> None:
        common = {"msp_ref": "msp-1", "customer_ref": "customer-2", "site_ref": "a" * 24}
        device_ref = "b" * 24
        cases = (
            ("msp_olt_detail_summary", "/olts/" + device_ref + "/summary", True),
            ("msp_olt_eth_config_summary", "/olts/" + device_ref + "/ports-config-summary", True),
            ("msp_olt_site_ports_summary", "/olt-ports-summary", False),
            ("msp_olt_pon_port_config_summary", "/olts/" + device_ref + "/pon-port-config-summary", True),
        )
        for index, (operation, suffix, with_device) in enumerate(cases, start=198):
            prefix = (f"/v1/msp/{common['msp_ref']}/customers/{common['customer_ref']}/sites/"
                      f"{common['site_ref']}")
            route = prefix + suffix
            args = dict(common)
            if with_device:
                args["device_ref"] = device_ref
            status, body = self.request(route, self.token)
            with self.subTest(http=operation):
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], operation)
            self.fake.calls.clear()
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": index, "method": "tools/call",
                "params": {"name": f"omada_{operation}", "arguments": args},
            }, self.token)
            with self.subTest(mcp=operation):
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
                self.assertEqual(self.fake.calls[-1][0], operation)

    def test_msp_device_health_timelines_are_available_over_http_and_mcp(self) -> None:
        common = {"msp_ref": "msp-1", "customer_ref": "customer-2", "site_ref": "a" * 24}
        cases = (
            ("msp_ap_health_timeline", "aps", "device_ref"),
            ("msp_gateway_health_timeline", "gateways", "gateway_ref"),
            ("msp_switch_health_timeline", "switches", "switch_ref"),
        )
        for operation, family, ref_name in cases:
            args = {**common, ref_name: "b" * 24}
            path = (f"/v1/msp/{common['msp_ref']}/customers/{common['customer_ref']}/sites/"
                    f"{common['site_ref']}/{family}/{args[ref_name]}/health/timeline")
            status, body = self.request(path, self.token)
            with self.subTest(http=operation):
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], operation)
            self.fake.calls.clear()
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": 195, "method": "tools/call",
                "params": {"name": f"omada_{operation}", "arguments": args},
            }, self.token)
            with self.subTest(mcp=operation):
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
                self.assertEqual(self.fake.calls[-1][0], operation)

    def test_device_system_reads_are_available_over_http_and_mcp(self) -> None:
        site_ref, device_ref = "a" * 24, "b" * 24
        cases = (
            ("device_adopt_result", "adopt-result"),
            ("device_mac_type", "mac-type"),
            ("device_link_topology", "link-topology"),
            ("device_radsec_support", "radsec-support"),
            ("device_upgrade_result", "upgrade-result"),
            ("device_timeline", "online-timeline"),
            ("device_inventory_summary", "device-inventory-summary"),
            ("olt_detail_summary", "summary"),
            ("olt_ports_summary", "ports-summary"),
            ("olt_onu_global_status", "onu-global-status"),
            ("olt_onu_isolation_status", "onu-isolation-status"),
            ("olt_eth_config_summary", "ports-config-summary"),
            ("olt_lag_config_summary", "lags-summary"),
            ("olt_auto_refresh_summary", "auto-refresh-summary"),
            ("olt_pon_information_summary", "pon-information-summary"),
            ("olt_pon_port_config_page_summary", "pon-port-config-page-summary"),
            ("olt_pon_port_config_summary", "pon-port-config-summary"),
            ("olt_service_port_profiles_summary", "service-port-profiles-summary"),
            ("olt_onu_auto_auth_status", "onu-auto-auth-status"),
            ("olt_onu_autofind_summary", "onu-autofind-summary"),
            ("olt_onu_autofind_inventory_summary", "onu-autofind-inventory-summary"),
            ("olt_onu_inventory_summary", "onu-inventory-summary"),
            ("olt_onu_reboot_status_summary", "onu-reboot-status-summary"),
            ("olt_system_info", "system-info"),
            ("olt_management_interfaces", "management-interfaces"),
        )
        for operation, suffix in cases:
            path = (f"/v1/sites/{site_ref}/devices/radsec-support" if operation == "device_radsec_support"
                    else f"/v1/sites/{site_ref}/device-inventory-summary" if operation == "device_inventory_summary"
                    else f"/v1/sites/{site_ref}/olts/{device_ref}/{suffix}" if operation.startswith("olt_")
                    else f"/v1/sites/{site_ref}/devices/{device_ref}/{suffix}")
            if operation == "olt_onu_inventory_summary":
                path += "?pon_port=GPON+1%2F1%2F1"
            if operation == "olt_onu_autofind_inventory_summary":
                path += "?pon_port=GPON+1%2F1%2F1&page_number=0&page_size=10"
            if operation == "olt_pon_port_config_page_summary":
                path += "?page_number=0&page_size=5"
            status, body = self.request(path, self.token)
            with self.subTest(http=operation):
                self.assertEqual(status, 200)
                self.assertEqual(body["resource"], operation)
        self.assertEqual([name for name, _ in self.fake.calls], [name for name, _ in cases])

        self.fake.calls.clear()

        cursor = None
        advertised: set[str] = set()
        while True:
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": 180, "method": "tools/list",
                "params": {} if cursor is None else {"cursor": cursor},
            }, self.token)
            self.assertEqual(status, 200)
            advertised.update(tool["name"] for tool in response["result"]["tools"])
            cursor = response["result"].get("nextCursor")
            if cursor is None:
                break
        self.assertTrue({f"omada_{operation}" for operation, _ in cases} <= advertised)
        for index, (operation, _) in enumerate(cases, start=181):
            status, response = self.request_post("/mcp", {
                "jsonrpc": "2.0", "id": index, "method": "tools/call",
            "params": {"name": f"omada_{operation}",
                           "arguments": ({"site_ref": site_ref} if operation in {"device_radsec_support", "device_inventory_summary"}
                                         else {"site_ref": site_ref, "device_ref": device_ref,
                                               **({"pon_port": "GPON 1/1/1"} if operation == "olt_onu_inventory_summary" else {}),
                                               **({"pon_port": "GPON 1/1/1", "page_number": 0, "page_size": 10} if operation == "olt_onu_autofind_inventory_summary" else {}),
                                               **({"page_number": 0, "page_size": 5} if operation == "olt_pon_port_config_page_summary" else {})})},
            }, self.token)
            with self.subTest(mcp=operation):
                self.assertEqual(status, 200)
                self.assertEqual(response["result"]["structuredContent"]["resource"], operation)
        self.assertEqual([name for name, _ in self.fake.calls], [name for name, _ in cases])

    def test_site_outage_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        start_ms, end_ms = 1_790_000_000_000, 1_790_000_030_000
        calls = []

        def outage(ref, start, end):
            calls.append((ref, start, end))
            return {"status": "ok", "resource": "site_outage_summary",
                    "site_ref": ref, "partial": False}

        self.fake.read_site_outage_summary = outage
        route = f"/v1/sites/{site_ref}/outage-summary?" + urlencode(
            {"start_ms": str(start_ms), "end_ms": str(end_ms)})
        status, response = self.request(route, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_outage_summary")
        self.assertEqual(calls, [(site_ref, start_ms, end_ms)])

        status, _ = self.request(f"/v1/sites/{site_ref}/outage-summary?start_ms={start_ms}",
                                 self.token)
        self.assertEqual(status, 400)
        self.assertEqual(len(calls), 1)

        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 190, "method": "tools/call",
            "params": {"name": "omada_site_outage_summary", "arguments": {
                "site_ref": site_ref, "start_ms": start_ms, "end_ms": end_ms}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_outage_summary")
        self.assertEqual(calls, [(site_ref, start_ms, end_ms)] * 2)

    def test_redacted_incident_reports_compare_over_http_and_mcp_without_live_reads(self) -> None:
        reports = [_incident_report(), _incident_report(event_count=9, alert_count=5)]
        status, body = self.request_post("/v1/incident-reports/compare",
                                         {"reports": reports})
        self.assertEqual(status, 401, repr(body))
        self.assertEqual(body["error"], "unauthorized")
        status, response = self.request_post(
            "/v1/incident-reports/compare", {"reports": reports}, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "incident_report_comparison")
        self.assertEqual(response["live_controller_queries"], 0)
        self.assertEqual(self.fake.calls, [])

        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 192, "method": "tools/call",
            "params": {"name": "omada_compare_incident_reports",
                       "arguments": {"reports": reports}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "incident_report_comparison")
        self.assertEqual(self.fake.calls, [])

        status, body = self.request_post("/v1/incident-reports/compare",
                                         {"reports": [_incident_report()]}, self.token)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "reports_invalid")

    def test_gateway_wan_incident_window_is_available_over_http_and_mcp(self) -> None:
        site_ref, gateway_ref = "a" * 24, "b" * 24
        start_ms, end_ms = 1_790_000_000_000, 1_790_000_030_000
        calls = []

        def report(site, gateway, start, end):
            calls.append((site, gateway, start, end))
            return {"status": "ok", "resource": "gateway_wan_incident_window",
                    "partial": True,
                    "load_balance_participation": {"status": "unknown"}}

        self.fake.read_gateway_wan_incident_window = report
        path = (f"/v1/sites/{site_ref}/gateways/{gateway_ref}/wan-incident-window?" +
                urlencode({"start_ms": str(start_ms), "end_ms": str(end_ms)}))
        status, response = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "gateway_wan_incident_window")
        self.assertEqual(response["load_balance_participation"]["status"], "unknown")
        self.assertEqual(calls, [(site_ref, gateway_ref, start_ms, end_ms)])

        status, _ = self.request(
            f"/v1/sites/{site_ref}/gateways/{gateway_ref}/wan-incident-window?start_ms={start_ms}",
            self.token)
        self.assertEqual(status, 400)
        self.assertEqual(len(calls), 1)

        status, rpc = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 191, "method": "tools/call",
            "params": {"name": "omada_gateway_wan_incident_window", "arguments": {
                "site_ref": site_ref, "gateway_ref": gateway_ref,
                "start_ms": start_ms, "end_ms": end_ms}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "gateway_wan_incident_window")
        self.assertEqual(calls, [(site_ref, gateway_ref, start_ms, end_ms)] * 2)

    def test_site_dhcp_pool_utilization_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        calls = []

        def report(ref):
            calls.append(ref)
            return {"status": "ok", "resource": "site_dhcp_pool_utilization",
                    "partial": False, "summary": {
                        "network_count": 1, "pool_capacity_address_count": 10,
                        "available_address_count": 2, "depleted_network_count": 0}}

        self.fake.read_site_dhcp_pool_utilization = report
        status, response = self.request(
            f"/v1/sites/{site_ref}/dhcp/pool-utilization", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_dhcp_pool_utilization")
        self.assertEqual(response["summary"]["available_address_count"], 2)
        self.assertEqual(calls, [site_ref])

        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 192, "method": "tools/call",
            "params": {"name": "omada_site_dhcp_pool_utilization",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_dhcp_pool_utilization")
        self.assertEqual(calls, [site_ref, site_ref])

    def test_site_ap_quality_window_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        calls = []

        def report(ref):
            calls.append(ref)
            return {"status": "ok", "resource": "site_ap_quality_window",
                    "partial": False, "summary": {"checked_ap_count": 2}}

        self.fake.read_site_ap_quality_window = report
        status, response = self.request(
            f"/v1/sites/{site_ref}/aps/quality-window", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_ap_quality_window")
        self.assertEqual(calls, [site_ref])

        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 193, "method": "tools/call",
            "params": {"name": "omada_site_ap_quality_window",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_ap_quality_window")
        self.assertEqual(calls, [site_ref, site_ref])

    def test_site_switch_health_history_is_available_over_http_and_mcp(self) -> None:
        site_ref = "d" * 24
        calls = []

        def report(ref):
            calls.append(ref)
            return {"status": "ok", "resource": "site_switch_health_history",
                    "partial": True, "devices_queried": 1, "data": []}

        self.fake.read_site_switch_health_history = report
        status, response = self.request(
            f"/v1/sites/{site_ref}/switches/health-history", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_switch_health_history")

        self.assertEqual(calls, [site_ref])

        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 194, "method": "tools/call",
            "params": {"name": "omada_site_switch_health_history",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_switch_health_history")
        self.assertEqual(calls, [site_ref, site_ref])

    def test_site_firmware_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "a" * 24
        calls = []

        def report(ref):
            calls.append(ref)
            return {"status": "ok", "resource": "site_firmware_summary",
                    "partial": False, "summary": {"checked_device_count": 2}}

        self.fake.read_site_firmware_summary = report
        status, response = self.request(
            f"/v1/sites/{site_ref}/firmware-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_firmware_summary")
        self.assertEqual(calls, [site_ref])

        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 194, "method": "tools/call",
            "params": {"name": "omada_site_firmware_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_firmware_summary")
        self.assertEqual(calls, [site_ref, site_ref])



    def test_switch_port_anomaly_summary_is_available_over_http_and_mcp(self) -> None:
        site_ref = "e" * 24
        calls = []

        def report(ref):
            calls.append(ref)
            return {"status": "ok", "resource": "site_switch_port_anomaly_summary",
                    "partial": True, "drop_counters": "not_available_in_documented_port_counter_response",
                    "source_contract": "port_status_and_tx_rx_errors_documented_in_all_three_exports; status_codes_uninterpreted",
                    "data": {"switches": []}}

        self.fake.read_site_switch_port_anomaly_summary = report
        status, response = self.request(
            f"/v1/sites/{site_ref}/switches/port-anomalies")
        self.assertEqual(status, 401, repr(response))
        self.assertEqual(calls, [])

        status, response = self.request(
            f"/v1/sites/{site_ref}/switches/port-anomalies", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_switch_port_anomaly_summary")
        self.assertEqual(
            response["source_contract"],
            "port_status_and_tx_rx_errors_documented_in_all_three_exports; status_codes_uninterpreted")
        self.assertEqual(calls, [site_ref])

        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 195, "method": "tools/call",
            "params": {"name": "omada_site_switch_port_anomaly_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "site_switch_port_anomaly_summary")
        self.assertEqual(
            response["result"]["structuredContent"]["source_contract"],
            "port_status_and_tx_rx_errors_documented_in_all_three_exports; status_codes_uninterpreted")
        self.assertEqual(calls, [site_ref, site_ref])
    def test_http_and_mcp_expose_site_stack_connections_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/stack-connections-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_stack_connections_summary")
        request = {"jsonrpc": "2.0", "id": 140, "method": "tools/call",
                   "params": {"name": "omada_site_stack_connections_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_stack_connections_summary")
        self.assertEqual(self.fake.calls,
                         [("site_stack_connections_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_selected_stack_network_summary(self) -> None:
        site_ref, stack_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/stacks/{stack_ref}/networks-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_stack_network_summary")
        request = {"jsonrpc": "2.0", "id": 307, "method": "tools/call",
                   "params": {"name": "omada_site_stack_network_summary",
                              "arguments": {"site_ref": site_ref,
                                            "stack_ref": stack_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertIn("result", response, repr(response))
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_stack_network_summary", site_ref, stack_ref)] * 2)

    def test_http_and_mcp_expose_stack_static_routing_summary(self) -> None:
        site_ref, stack_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/stacks/{stack_ref}/static-routings/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_stack_static_routing_summary")
        request = {"jsonrpc": "2.0", "id": 461, "method": "tools/call",
                   "params": {"name": "omada_site_stack_static_routing_summary",
                              "arguments": {"site_ref": site_ref,
                                            "stack_ref": stack_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_stack_static_routing_summary", site_ref, stack_ref)] * 2)

    def test_http_and_mcp_expose_stack_ospf_neighbor_summary(self) -> None:
        site_ref, stack_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/stacks/{stack_ref}/ospf-neighbors/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_stack_ospf_neighbor_summary")
        request = {"jsonrpc": "2.0", "id": 462, "method": "tools/call",
                   "params": {"name": "omada_site_stack_ospf_neighbor_summary",
                              "arguments": {"site_ref": site_ref,
                                            "stack_ref": stack_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_stack_ospf_neighbor_summary", site_ref, stack_ref)] * 2)

    def test_http_and_mcp_expose_stack_cable_test_log_summary(self) -> None:
        site_ref, stack_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/stacks/{stack_ref}/cable-test-log-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_stack_cable_test_log_summary")
        request = {"jsonrpc": "2.0", "id": 465, "method": "tools/call",
                   "params": {"name": "omada_site_stack_cable_test_log_summary",
                              "arguments": {"site_ref": site_ref, "stack_ref": stack_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_stack_cable_test_log_summary", site_ref, stack_ref)] * 2)

    def test_http_and_mcp_expose_intelli_recover_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/automatic-recovery-settings/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_intelli_recover_summary")
        request = {"jsonrpc": "2.0", "id": 463, "method": "tools/call",
                   "params": {"name": "omada_site_intelli_recover_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_intelli_recover_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_port_forwarding_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/port-forwardings/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_port_forwarding_summary")
        request = {"jsonrpc": "2.0", "id": 464, "method": "tools/call",
                   "params": {"name": "omada_site_port_forwarding_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_port_forwarding_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_redacted_stack_dhcp_user_summary(self) -> None:
        site_ref, stack_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/stacks/{stack_ref}/dhcp-users/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_stack_dhcp_user_summary")
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 451, "method": "tools/call",
            "params": {"name": "omada_site_stack_dhcp_user_summary",
                       "arguments": {"site_ref": site_ref, "stack_ref": stack_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_stack_dhcp_user_summary", site_ref, stack_ref)] * 2)

    def test_http_and_mcp_expose_redacted_stack_vlan_interface_summary(self) -> None:
        site_ref, stack_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/stacks/{stack_ref}/vlan-interfaces/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_stack_vlan_interface_summary")
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 453, "method": "tools/call",
            "params": {"name": "omada_site_stack_vlan_interface_summary",
                       "arguments": {"site_ref": site_ref, "stack_ref": stack_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_stack_vlan_interface_summary", site_ref, stack_ref)] * 2)

    def test_http_and_mcp_expose_count_only_snmp_incompatible_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/snmp/incompatible-devices/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_snmp_incompatible_summary")
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 454, "method": "tools/call",
            "params": {"name": "omada_site_snmp_incompatible_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_snmp_incompatible_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_gateway_general_config_summary(self) -> None:
        site_ref, gateway_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/gateways/{gateway_ref}/general-config-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "gateway_general_config_summary")
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 455, "method": "tools/call",
            "params": {"name": "omada_site_gateway_general_config_summary",
                       "arguments": {"site_ref": site_ref, "gateway_ref": gateway_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_gateway_general_config_summary", site_ref, gateway_ref)] * 2)

    def test_http_and_mcp_expose_switch_general_config_summary(self) -> None:
        site_ref, switch_ref = "a" * 24, "c" * 24
        path = f"/v1/sites/{site_ref}/switches/{switch_ref}/general-config-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "switch_general_config_summary")
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 456, "method": "tools/call",
            "params": {"name": "omada_site_switch_general_config_summary",
                       "arguments": {"site_ref": site_ref, "switch_ref": switch_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_switch_general_config_summary", site_ref, switch_ref)] * 2)

    def test_http_and_mcp_expose_redacted_switch_oui_vlan_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/switches/oui-vlan-rules/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(direct["resource"], "site_switch_oui_vlan_summary")
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 452, "method": "tools/call",
            "params": {"name": "omada_site_switch_oui_vlan_summary",
                       "arguments": {"site_ref": site_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_switch_oui_vlan_summary", site_ref)] * 2)
    def test_http_and_mcp_expose_redacted_client_health_detail_v2(self) -> None:
        site_ref, client_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/clients/{client_ref}/health/detail-v2"
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "client_health_detail_v2")
        self.assertEqual(body["health_version"], 2)
        self.assertEqual(body["series_point_coverage"]["past_num_explicit_null_count"], 1)
        self.assertEqual(self.fake.calls[-1],
                         ("client_health_detail_v2", site_ref + ":" + client_ref))
        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 389, "method": "tools/call",
            "params": {"name": "omada_client_health_detail_v2",
                       "arguments": {"site_ref": site_ref, "client_ref": client_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        self.assertEqual(response["result"]["structuredContent"]["resource"],
                         "client_health_detail_v2")
        self.assertEqual(
            response["result"]["structuredContent"]["series_point_coverage"][
                "past_num_missing_count"], 1)
        self.assertEqual(self.fake.calls[-1],
                         ("client_health_detail_v2", site_ref + ":" + client_ref))

    def test_http_and_mcp_expose_unclassified_client_health_scores(self) -> None:
        site_ref, client_ref = "c" * 24, "d" * 24
        path = f"/v1/sites/{site_ref}/clients/{client_ref}/health"
        status, body = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "client_health")
        self.assertTrue(body["partial"])
        self.assertEqual(body["data"]["score"], None)
        self.assertEqual(body["unclassified_minus_one_fields"], ["score"])
        self.assertEqual(self.fake.calls[-1],
                         ("client_health", site_ref + ":" + client_ref))

        status, response = self.request_post("/mcp", {
            "jsonrpc": "2.0", "id": 411, "method": "tools/call",
            "params": {"name": "omada_client_health",
                       "arguments": {"site_ref": site_ref, "client_ref": client_ref}},
        }, self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("isError", response)
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["resource"], "client_health")
        self.assertTrue(structured["partial"])
        self.assertEqual(structured["data"]["score"], None)
        self.assertEqual(structured["unclassified_minus_one_fields"], ["score"])
        self.assertEqual(self.fake.calls[-1],
                         ("client_health", site_ref + ":" + client_ref))

    def test_http_and_mcp_expose_selected_site_backup_inventory_summary(self) -> None:
        site_ref = "a" * 24
        status, response = self.request(
            f"/v1/sites/{site_ref}/backup-inventory-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_backup_inventory_summary")
        request = {"jsonrpc": "2.0", "id": 143, "method": "tools/call",
                   "params": {"name": "omada_site_backup_inventory_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "site_backup_inventory_summary")
        self.assertEqual(self.fake.calls,
                         [("site_backup_inventory_summary", site_ref)] * 2)
    def test_http_and_mcp_expose_controller_backup_inventory_summary(self) -> None:
        status, response = self.request(
            "/v1/controller/maintenance/backup-inventory-summary", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "controller_backup_inventory_summary")
        request = {"jsonrpc": "2.0", "id": 142, "method": "tools/call",
                   "params": {"name": "omada_controller_backup_inventory_summary",
                              "arguments": {}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "controller_backup_inventory_summary")
        self.assertEqual(self.fake.calls,
                         [("controller_backup_inventory_summary", None)] * 2)

    def test_multi_client_outage_overlap_uses_authenticated_http_and_mcp(self) -> None:
        site_ref, client_refs = "a" * 24, ["b" * 24, "c" * 24]
        start_ms, end_ms = 1_789_372_800_000, 1_789_372_860_000
        seen = []

        def summary(site, refs, start, end):
            seen.append((site, refs, start, end))
            return {"status": "ok", "resource": "client_outage_overlap_summary",
                    "site_ref": site, "window_start_ms": start,
                    "window_end_ms": end, "selected_client_count": len(refs),
                    "confirmed_overlaps_by_access_point": [], "partial": False}

        self.fake.read_site_client_outage_overlap_summary = summary
        query = (f"start_ms={start_ms}&end_ms={end_ms}&client_ref={client_refs[0]}"
                 f"&client_ref={client_refs[1]}")
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-outage-overlaps?{query}", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "client_outage_overlap_summary")
        self.assertEqual(seen[-1], (site_ref, client_refs, start_ms, end_ms))

        request = {"jsonrpc": "2.0", "id": 42, "method": "tools/call",
                   "params": {"name": "omada_site_client_outage_overlap_summary",
                              "arguments": {"site_ref": site_ref, "client_refs": client_refs,
                                            "start_ms": start_ms, "end_ms": end_ms}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["selected_client_count"], 2)
        self.assertEqual(seen[-1], (site_ref, client_refs, start_ms, end_ms))

        invalid = {**request, "id": 43,
                   "params": {"name": "omada_site_client_outage_overlap_summary",
                              "arguments": {"site_ref": site_ref,
                                            "client_refs": [client_refs[0]] * 2,
                                            "start_ms": start_ms, "end_ms": end_ms}}}
        status, rpc = self.request_post("/mcp", invalid, self.token)
        self.assertEqual(status, 200)
        self.assertIn("arguments_invalid", json.dumps(rpc))

    def test_client_roaming_backtrack_is_available_over_http_and_mcp(self) -> None:
        site_ref, client_ref = "a" * 24, "b" * 24
        start_ms, end_ms = 1_789_372_800_000, 1_789_372_860_000
        seen = []

        def summary(site, refs, start, end):
            seen.append((site, refs, start, end))
            return {"status": "ok", "resource": "client_roaming_backtrack_summary",
                    "site_ref": site, "selected_client_count": len(refs),
                    "back_and_forth_by_access_point_pair": [], "partial": False}

        self.fake.read_site_client_roaming_backtrack_summary = summary
        query = (f"start_ms={start_ms}&end_ms={end_ms}&client_ref={client_ref}")
        status, response = self.request(
            f"/v1/sites/{site_ref}/client-roaming-backtracks?{query}", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "client_roaming_backtrack_summary")
        self.assertEqual(seen[-1], (site_ref, [client_ref], start_ms, end_ms))

        request = {"jsonrpc": "2.0", "id": 44, "method": "tools/call",
                   "params": {"name": "omada_site_client_roaming_backtrack_summary",
                              "arguments": {"site_ref": site_ref,
                                            "client_refs": [client_ref],
                                            "start_ms": start_ms, "end_ms": end_ms}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["resource"],
                         "client_roaming_backtrack_summary")
        self.assertEqual(seen[-1], (site_ref, [client_ref], start_ms, end_ms))

        invalid = {**request, "id": 45,
                   "params": {"name": "omada_site_client_roaming_backtrack_summary",
                              "arguments": {"site_ref": site_ref, "client_refs": [],
                                            "start_ms": start_ms, "end_ms": end_ms}}}
        status, rpc = self.request_post("/mcp", invalid, self.token)
        self.assertEqual(status, 200)
        self.assertIn("arguments_invalid", json.dumps(rpc))

    def test_site_ap_uplink_path_is_available_over_http_and_mcp(self) -> None:
        site_ref, refs = "a" * 24, ["b" * 24, "c" * 24]
        seen = []

        def summary(site, selected_refs):
            seen.append((site, selected_refs))
            return {"status": "ok", "resource": "site_ap_uplink_path_summary",
                    "site_ref": site, "selected_ap_count": len(selected_refs),
                    "aps": [], "partial": False}

        self.fake.read_site_ap_uplink_path_summary = summary
        query = f"device_ref={refs[0]}&device_ref={refs[1]}"
        status, response = self.request(
            f"/v1/sites/{site_ref}/ap-uplink-paths?{query}", self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["resource"], "site_ap_uplink_path_summary")
        self.assertEqual(seen[-1], (site_ref, refs))

        request = {"jsonrpc": "2.0", "id": 46, "method": "tools/call",
                   "params": {"name": "omada_site_ap_uplink_path_summary",
                              "arguments": {"site_ref": site_ref, "device_refs": refs}}}
        status, rpc = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(rpc["result"]["structuredContent"]["selected_ap_count"], 2)
        self.assertEqual(seen[-1], (site_ref, refs))

        invalid = {**request, "id": 47,
                   "params": {"name": "omada_site_ap_uplink_path_summary",
                              "arguments": {"site_ref": site_ref, "device_refs": [refs[0]] * 2}}}
        status, rpc = self.request_post("/mcp", invalid, self.token)
        self.assertEqual(status, 200)
        self.assertIn("arguments_invalid", json.dumps(rpc))

    def test_http_and_mcp_expose_lan_switch_profile_assignment_counts(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/lan-switch-profile-assignments/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 248, "method": "tools/call",
                   "params": {"name": "omada_site_lan_switch_profile_assignments_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_lan_switch_profile_assignments_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_ssid_topology_opaque_reference_count(self) -> None:
        site_ref, ssid_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/ssids/{ssid_ref}/topology-reference-count"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 249, "method": "tools/call",
                   "params": {"name": "omada_site_ssid_topology_reference_count",
                              "arguments": {"site_ref": site_ref, "ssid_ref": ssid_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_ssid_topology_reference_count", site_ref, ssid_ref)] * 2)

    def test_http_and_mcp_expose_ipsec_failover_summary(self) -> None:
        site_ref = "a" * 24
        path = f"/v1/sites/{site_ref}/ipsec-failovers/summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 253, "method": "tools/call",
                   "params": {"name": "omada_site_ipsec_failover_summary",
                              "arguments": {"site_ref": site_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls, [("site_ipsec_failover_summary", site_ref)] * 2)

    def test_http_and_mcp_expose_gateway_sim_sms_support(self) -> None:
        site_ref, gateway_ref = "a" * 24, "b" * 24
        path = f"/v1/sites/{site_ref}/gateways/{gateway_ref}/sim-capabilities-summary"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 252, "method": "tools/call",
                   "params": {"name": "omada_site_gateway_sim_sms_support_summary",
                              "arguments": {"site_ref": site_ref,
                                            "gateway_ref": gateway_ref}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_gateway_sim_sms_support_summary", site_ref + ":" + gateway_ref)] * 2)

    def test_http_and_mcp_expose_vlan_topology_opaque_reference_count(self) -> None:
        site_ref, network_ref, vlan_id = "a" * 24, "b" * 24, 42
        path = f"/v1/sites/{site_ref}/networks/{network_ref}/vlan-topology-reference-count?vlan_id=42"
        status, direct = self.request(path, self.token)
        self.assertEqual(status, 200)
        request = {"jsonrpc": "2.0", "id": 250, "method": "tools/call",
                   "params": {"name": "omada_site_vlan_topology_reference_count",
                              "arguments": {"site_ref": site_ref, "network_ref": network_ref,
                                            "vlan_id": vlan_id}}}
        status, response = self.request_post("/mcp", request, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["structuredContent"], direct)
        self.assertEqual(self.fake.calls,
                         [("site_vlan_topology_reference_count", site_ref, network_ref, vlan_id)] * 2)

if __name__ == "__main__":
    unittest.main()


class DeviceUpgradeResultProjectionTests(unittest.TestCase):
    def test_absent_result_is_unreported_partial_not_a_success_or_empty_task(self) -> None:
        projected = project_device_upgrade_result(None, result_reported=False)
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["data"], {
            "finished": None, "success": None, "present_count": 0,
            "missing_count": 2, "invalid_count": 0, "unknown_field_count": 0,
            "result_reported": False,
        })

    def test_explicit_null_result_remains_invalid(self) -> None:
        with self.assertRaises(DeviceUpgradeResultError):
            project_device_upgrade_result(None, result_reported=True)

    def test_client_marks_absent_optional_result_partial(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref, device_ref = "a" * 24, "b" * 24
        with patch.object(client, "_device_read_context", return_value=("site", "mac")),              patch.object(client, "_access_token", return_value="token"),              patch.object(client, "_request_json", return_value={"errorCode": 0, "msg": "ok"}):
            result = client.read_device_upgrade_result(site_ref, device_ref)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["data"]["result_reported"])
        self.assertIsNone(result["data"]["finished"])
        self.assertIsNone(result["data"]["success"])
