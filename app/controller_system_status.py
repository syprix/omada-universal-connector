"""Strict summaries for fixed controller cloud and maintenance status reads."""
from __future__ import annotations

import re
from typing import Any


class ControllerSystemStatusError(ValueError):
    """Raised when a controller status response is not a bounded object."""


def _project_enum(result: Any, field: str, values: dict[int, str]) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerSystemStatusError("response_invalid")
    data: dict[str, object] = {}
    missing = 0
    invalid = 0
    if field not in result:
        missing = 1
    else:
        raw = result[field]
        if type(raw) is int and raw in values:
            data["status"] = values[raw]
        else:
            invalid = 1
    unknown = len(set(result) - {field})
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_controller_backup_result(result: Any) -> dict[str, object]:
    return _project_enum(result, "status", {0: "idle_or_finished", 1: "running"})


def project_controller_restore_result(result: Any) -> dict[str, object]:
    return _project_enum(result, "status", {
        0: "finished", 1: "prepared", 2: "running", 3: "failed",
    })


def project_controller_remote_binding(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerSystemStatusError("response_invalid")
    enabled = result.get("enable")
    data = {"enabled": enabled} if isinstance(enabled, bool) else {}
    missing = int("enable" not in result)
    invalid = int("enable" in result and not isinstance(enabled, bool))
    unknown = len(set(result) - {"enable"})
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_controller_privacy_policy(result: Any) -> dict[str, object]:
    """Expose the documented policy switch without returning policy text."""
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerSystemStatusError("response_invalid")
    raw = result.get("status")
    enabled = raw == 1 if type(raw) is int and raw in (0, 1) else None
    missing = int("status" not in result)
    invalid = int("status" in result and enabled is None)
    unknown = len(set(result) - {"status"})
    data = {"enabled": enabled} if enabled is not None else {}
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_controller_mail_status(result: Any) -> dict[str, object]:
    """Summarize mail configuration without returning addresses or secrets."""
    if not isinstance(result, dict) or len(result) > 32:
        raise ControllerSystemStatusError("response_invalid")
    allowed = {"id", "sender", "receiver", "ssl", "smtpServer", "smtpPort",
               "auth", "username", "authCode", "resource"}
    required = {"sender", "receiver", "ssl", "auth"}
    missing = invalid = 0
    unknown = len(set(result) - allowed)
    data: dict[str, object] = {}

    for field, output in (("sender", "sender_configured"),
                          ("receiver", "receiver_configured"),
                          ("username", "username_configured"),
                          ("smtpServer", "server_configured"),
                          ("authCode", "authorization_code_present"),
                          ("id", "server_id_present")):
        if field not in result:
            if field in required:
                missing += 1
            continue
        value = result[field]
        if value is None and field not in required:
            data[output] = False
        elif isinstance(value, str) and len(value) <= 4096:
            data[output] = bool(value)
        else:
            invalid += 1

    for field, output in (("ssl", "secure_transport_enabled"),
                          ("auth", "authentication_enabled")):
        if field not in result:
            missing += int(field in required)
        elif isinstance(result[field], bool):
            data[output] = result[field]
        else:
            invalid += 1

    if "smtpPort" in result:
        port = result["smtpPort"]
        if port is None:
            data["smtp_port_present"] = False
        elif type(port) is int and -(2 ** 31) <= port < 2 ** 31:
            data["smtp_port_present"] = True
        else:
            invalid += 1
    if "resource" in result:
        resource = result["resource"]
        if resource is None:
            data["resource_present"] = False
        elif type(resource) is int and -(2 ** 31) <= resource < 2 ** 31:
            data["resource_present"] = True
        else:
            invalid += 1

    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_controller_mfa_status(result: Any) -> dict[str, object]:
    """Expose only the system-wide two-factor authentication switch."""
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerSystemStatusError("response_invalid")
    value = result.get("enable")
    valid = type(value) is bool
    missing = int("enable" not in result)
    invalid = int("enable" in result and not valid)
    unknown = len(set(result) - {"enable"})
    data = {"enabled": value} if valid else {}
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_msp_cloud_access_status(result: Any) -> dict[str, object]:
    """Summarize MSP cloud status without returning its owner value."""
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerSystemStatusError("response_invalid")
    allowed = {"enable", "owner", "status"}
    missing = invalid = 0
    unknown = len(set(result) - allowed)
    data: dict[str, object] = {}
    for field, output in (("enable", "enabled"), ("status", "connection")):
        if field not in result:
            missing += 1
        elif field == "enable" and isinstance(result[field], bool):
            data[output] = result[field]
        elif field == "status" and type(result[field]) is int and result[field] in {-1, 0, 1}:
            data[output] = {-1: "disabled", 0: "disconnected", 1: "connected"}[result[field]]
        else:
            invalid += 1
    owner = result.get("owner")
    if owner is not None:
        if isinstance(owner, str) and len(owner) <= 512:
            data["owner_present"] = bool(owner)
        else:
            invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_msp_dst_info(result: Any) -> dict[str, object]:
    """Project the CBC MSP daylight-saving status through the bounded DST contract."""
    try:
        from .controller_dst_info import ControllerDstError, project_controller_dst
    except ImportError:  # direct execution in the image
        from controller_dst_info import ControllerDstError, project_controller_dst
    try:
        return project_controller_dst(result)
    except ControllerDstError:
        raise ControllerSystemStatusError("response_invalid") from None


def project_msp_remote_logging(result: Any) -> dict[str, object]:
    """Project the documented MSP remote-logging status without its destination."""
    try:
        from .controller_remote_logging import (
            ControllerRemoteLoggingError, project_controller_remote_logging,
        )
    except ImportError:  # direct execution in the image
        from controller_remote_logging import (
            ControllerRemoteLoggingError, project_controller_remote_logging,
        )
    try:
        return project_controller_remote_logging(result)
    except ControllerRemoteLoggingError:
        raise ControllerSystemStatusError("response_invalid") from None


def project_msp_mail_server(result: Any) -> dict[str, object]:
    """Summarize the documented MSP mail-server settings without returning values."""
    if not isinstance(result, dict) or len(result) > 20:
        raise ControllerSystemStatusError("response_invalid")
    required = {"authEnable", "port", "smtpServer", "sslEnable"}
    known = required | {"smtpEnable", "username", "password", "senderAddress", "receiver"}
    settings: dict[str, object] = {}
    missing = invalid = 0
    for name, target in (("smtpEnable", "server_enabled"),
                         ("sslEnable", "secure_transport_enabled"),
                         ("authEnable", "authentication_enabled")):
        if name not in result:
            missing += int(name in required)
        elif type(result[name]) is bool:
            settings[target] = result[name]
        else:
            invalid += 1
    if "port" not in result:
        missing += 1
    elif type(result["port"]) is int and 1 <= result["port"] <= 65535:
        settings["port_configured"] = True
    else:
        settings["port_configured"] = False
        invalid += 1
    string_fields = (
        ("smtpServer", "server_configured", True, 128),
        ("username", "username_configured", False, 128),
        ("password", "password_configured", False, 128),
        ("senderAddress", "sender_configured", False, 4096),
        ("receiver", "receiver_configured", False, 4096),
    )
    for name, target, is_required, maximum in string_fields:
        if name not in result:
            missing += int(is_required)
            continue
        value = result[name]
        if not isinstance(value, str) or len(value) > maximum:
            settings[target] = False
            invalid += 1
        elif name in {"smtpServer", "username", "password"} and any(
                ord(char) < 33 or ord(char) > 126 for char in value):
            settings[target] = False
            invalid += 1
        elif name in {"senderAddress", "receiver"} and value and not re.fullmatch(
                r"[-0-9a-zA-Z.+_]+@[-0-9a-zA-Z.+_]+\.[a-zA-Z0-9]{2,}", value):
            settings[target] = False
            invalid += 1
        else:
            settings[target] = bool(value)
    unknown = len(set(result) - known)
    return {"data": {"settings": settings, "present_count": len(settings),
                     "missing_required_count": missing, "invalid_count": invalid,
                     "unknown_field_count": unknown},
            "partial": bool(missing or invalid or unknown)}


def project_msp_general_settings(result: Any) -> dict[str, object]:
    """Return bounded timezone and DST facts without exposing the MSP display name."""
    if not isinstance(result, dict) or len(result) > 4:
        raise ControllerSystemStatusError("response_invalid")
    known = {"name", "timeZone", "dst"}
    settings: dict[str, object] = {}
    invalid = 0
    for field, target, maximum in (("name", "name_configured", 35),
                                   ("timeZone", "time_zone", 128)):
        if field not in result:
            continue
        value = result[field]
        if isinstance(value, str) and len(value) <= maximum:
            settings[target] = bool(value) if field == "name" else value
        else:
            invalid += 1
    dst: dict[str, object] = {}
    if "dst" in result:
        try:
            from .controller_dst_info import ControllerDstError, project_controller_dst
        except ImportError:  # direct execution in the image
            from controller_dst_info import ControllerDstError, project_controller_dst
        try:
            dst = project_controller_dst(result["dst"])
        except ControllerDstError:
            invalid += 1
    missing = len(known) - sum(field in result for field in known)
    unknown = len(set(result) - known)
    return {"data": {"settings": settings, "dst": dst,
                     "missing_field_count": missing, "invalid_field_count": invalid,
                     "unknown_field_count": unknown},
            "partial": bool(missing or invalid or unknown or dst.get("partial", False))}


def project_msp_log_notification_settings(result: Any) -> dict[str, object]:
    """Summarize notification settings without returning event names or endpoints."""
    if not isinstance(result, dict) or len(result) > 8:
        raise ControllerSystemStatusError("response_invalid")
    known = {"webhookConfig", "logNotifications", "alertEmailSetting"}
    settings: dict[str, object] = {}
    invalid = unknown = 0
    present_sections = 0

    if "webhookConfig" in result:
        present_sections += 1
        value = result["webhookConfig"]
        if not isinstance(value, dict) or len(value) > 4:
            invalid += 1
        else:
            if "webhookEnable" in value:
                if type(value["webhookEnable"]) is bool:
                    settings["webhook_enabled"] = value["webhookEnable"]
                else:
                    invalid += 1
            if "webhookId" in value:
                if isinstance(value["webhookId"], str) and len(value["webhookId"]) <= 128:
                    settings["webhook_id_present"] = bool(value["webhookId"])
                else:
                    invalid += 1
            unknown += len(set(value) - {"webhookEnable", "webhookId"})

    counts = {field: 0 for field in ("alert", "event", "email", "webhook")}
    if "logNotifications" in result:
        present_sections += 1
        items = result["logNotifications"]
        if not isinstance(items, list) or len(items) > 500:
            invalid += 1
        else:
            settings["notification_count"] = len(items)
            for item in items:
                if not isinstance(item, dict) or len(item) > 8:
                    invalid += 1
                    continue
                unknown += len(set(item) - {"key", "shortMsg", "alert", "event", "email", "webhook"})
                for field in counts:
                    if field not in item:
                        continue
                    if type(item[field]) is bool:
                        counts[field] += int(item[field])
                    else:
                        invalid += 1
            settings.update({f"{field}_enabled_count": count
                             for field, count in counts.items()})

    if "alertEmailSetting" in result:
        present_sections += 1
        value = result["alertEmailSetting"]
        if not isinstance(value, dict) or len(value) > 4:
            invalid += 1
        else:
            for field, target in (("alertEmailEnable", "alert_email_enabled"),
                                  ("delayEnable", "email_delay_enabled")):
                if field in value:
                    if type(value[field]) is bool:
                        settings[target] = value[field]
                    else:
                        invalid += 1
            if "delay" in value:
                delay = value["delay"]
                if type(delay) is int and 0 <= delay <= 99999:
                    settings["email_delay_configured"] = True
                else:
                    settings["email_delay_configured"] = False
                    invalid += 1
            unknown += len(set(value) - {"alertEmailEnable", "delayEnable", "delay"})

    unknown += len(set(result) - known)
    settings["present_sections"] = present_sections
    return {"data": {"settings": settings, "invalid_field_count": invalid,
                     "unknown_field_count": unknown},
            "partial": bool(invalid or unknown)}


def project_msp_data_retention(result: Any) -> dict[str, object]:
    """Reuse the bounded retention projection for the matching CBC MSP schema."""
    try:
        from .controller_retention import ControllerRetentionError, project_controller_retention
    except ImportError:  # direct execution in the image
        from controller_retention import ControllerRetentionError, project_controller_retention
    try:
        return project_controller_retention(result)
    except ControllerRetentionError:
        raise ControllerSystemStatusError("response_invalid") from None


def _project_msp_ui_interface(result: Any, required_fields: set[str]) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 20:
        raise ControllerSystemStatusError("response_invalid")
    booleans = {"use24hour", "fixedMenu", "showPDevices", "refreshBtnEnable",
                "websocketEnable", "controllerNotification", "privateLabelingEnable"}
    enums = {"language": {1, 4, 7, 8, 10, 12, 13, 15, 17, 18, 21},
             "theme": {0, 1}, "refreshRate": {0, 1, 2, 3, 4}}
    private_strings = {"privateLabelingUrl", "privateLabelingFileId", "privateLabelingFileName"}
    known = booleans | set(enums) | private_strings
    settings: dict[str, object] = {}
    invalid = 0
    for field in booleans:
        if field not in result:
            continue
        if type(result[field]) is bool:
            settings[re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower()] = result[field]
        else:
            invalid += 1
    for field, allowed in enums.items():
        if field not in result:
            continue
        value = result[field]
        if type(value) is int and value in allowed:
            settings[re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower() + "_code"] = value
        else:
            invalid += 1
    for field in private_strings:
        if field not in result:
            continue
        value = result[field]
        maximum = 4096 if field == "privateLabelingUrl" else 255 if field == "privateLabelingFileName" else 128
        if isinstance(value, str) and len(value) <= maximum:
            settings[re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower() + "_present"] = bool(value)
        else:
            invalid += 1
    missing = sum(field not in result for field in required_fields)
    unknown = len(set(result) - known)
    return {"data": {"settings": settings, "missing_required_count": missing,
                     "invalid_count": invalid, "unknown_field_count": unknown},
            "partial": bool(missing or invalid or unknown)}


def project_msp_ui_interface(result: Any) -> dict[str, object]:
    """Redact private-label URLs and IDs from the full documented MSP UI schema."""
    return _project_msp_ui_interface(result, {
        "fixedMenu", "refreshBtnEnable", "refreshRate", "use24hour", "websocketEnable",
    })


def project_msp_user_interface(result: Any) -> dict[str, object]:
    """Redact private-label URLs and IDs from the documented reduced MSP UI schema."""
    return _project_msp_ui_interface(result, {"refreshRate"})


def project_msp_available_roles(result: Any) -> dict[str, object]:
    """Summarize the documented MSP role catalog without returning role names or IDs."""
    if not isinstance(result, list) or len(result) > 500:
        raise ControllerSystemStatusError("response_invalid")
    type_counts = {str(i): 0 for i in range(3)}
    source_counts = {str(i): 0 for i in range(3)}
    defaults = custom = invalid = unknown = 0
    for item in result:
        if not isinstance(item, dict) or len(item) > 8:
            invalid += 1
            continue
        unknown += len(set(item) - {"id", "name", "type", "defaultRole", "source"})
        for field in ("id", "name"):
            if field in item and (not isinstance(item[field], str) or len(item[field]) > 128):
                invalid += 1
        role_type = item.get("type")
        if type(role_type) is int and role_type in (0, 1, 2):
            type_counts[str(role_type)] += 1
        elif "type" in item:
            invalid += 1
        source = item.get("source")
        if type(source) is int and source in (0, 1, 2):
            source_counts[str(source)] += 1
            custom += int(source == 2)
        elif "source" in item:
            invalid += 1
        default = item.get("defaultRole")
        if type(default) is bool:
            defaults += int(default)
        elif "defaultRole" in item:
            invalid += 1
    return {"data": {"role_count": len(result), "role_type_counts": type_counts,
                     "source_counts": source_counts, "default_role_count": defaults,
                     "msp_created_role_count": custom, "invalid_count": invalid,
                     "unknown_field_count": unknown},
            "partial": bool(invalid or unknown)}


def project_msp_dashboard_overall(result: Any) -> dict[str, object]:
    """Project the documented MSP client diagram as bounded aggregate counts."""
    if not isinstance(result, dict) or len(result) > 12:
        raise ControllerSystemStatusError("response_invalid")
    fields = {"totalClientNum": "total", "wiredUser": "wired",
              "wirelessUser": "wireless", "wirelessGuest": "wireless_guest"}
    data: dict[str, object] = {}
    missing = invalid = 0
    for source, target in fields.items():
        if source not in result:
            missing += 1
            continue
        value = result[source]
        if type(value) is int and 0 <= value <= 2_147_483_647:
            data[target] = value
        else:
            invalid += 1
    unknown = len(set(result) - set(fields))
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_msp_cluster_nodes(result: Any) -> dict[str, object]:
    """Summarize CBC cluster size and managed-capacity counts without node names."""
    if not isinstance(result, list) or len(result) > 200:
        raise ControllerSystemStatusError("response_invalid")
    known = {"nodeName", "currentNode", "role", "systemTime", "status",
             "managedSites", "managedDevices"}
    totals = {"managed_sites": 0, "managed_devices": 0}
    count_fields = {"managedSites": "managed_sites", "managedDevices": "managed_devices"}
    missing = invalid = unknown = status_reported = role_reported = 0
    for node in result:
        if not isinstance(node, dict) or len(node) > 16:
            invalid += 1
            continue
        unknown += len(set(node) - known)
        for name in ("nodeName", "currentNode", "role", "status"):
            if name in node:
                value = node[name]
                if not isinstance(value, str) or len(value) > 128:
                    invalid += 1
                elif value:
                    status_reported += int(name == "status")
                    role_reported += int(name == "role")
        if "systemTime" in node and (type(node["systemTime"]) is not int or
                                      not 0 <= node["systemTime"] <= 9_223_372_036_854_775_807):
            invalid += 1
        for source, target in count_fields.items():
            if source not in node:
                missing += 1
                continue
            value = node[source]
            if type(value) is not int or not 0 <= value <= 2_147_483_647:
                invalid += 1
            else:
                totals[target] += value
    if any(value > 2_147_483_647 for value in totals.values()):
        invalid += 1
        totals = {key: min(value, 2_147_483_647) for key, value in totals.items()}
    return {"data": {"node_count": len(result), **totals,
                     "nodes_reporting_role": role_reported,
                     "nodes_reporting_status": status_reported},
            "missing_field_count": missing, "invalid_field_count": invalid,
            "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_msp_adopt_tip(result: Any) -> dict[str, object]:
    """Project the documented MSP adoption tip as two bounded int32 counts."""
    if not isinstance(result, dict) or len(result) > 8:
        raise ControllerSystemStatusError("response_invalid")
    fields = {"adoptDeviceNum": "adopted_device_count",
              "recommendDeviceNum": "recommended_device_count"}
    data: dict[str, object] = {}
    missing = invalid = 0
    for source, target in fields.items():
        if source not in result:
            missing += 1
            continue
        value = result[source]
        if type(value) is int and 0 <= value <= 2_147_483_647:
            data[target] = value
        else:
            invalid += 1
    unknown = len(set(result) - set(fields))
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_msp_roles(result: Any) -> dict[str, object]:
    """Aggregate the documented MSP role privileges without role IDs or names."""
    if not isinstance(result, list) or len(result) > 500:
        raise ControllerSystemStatusError("response_invalid")
    access_fields = {
        "mspDashboard", "mspDevice", "mspLog", "mspLicense", "mspUsers",
        "mspRoles", "mspSamlUsers", "mspSamlRoles", "mspSamlSsos",
        "mspSetting", "mspWebhook", "mspCluster", "aiAssi",
    }
    two_level_fields = {"mspAdopt", "mspAddDevices", "mspAddAdoptDevice",
                        "mspExportData", "mspSites"}
    known_fields = access_fields | two_level_fields | {"mspLicenseBind"}
    levels = {name: {"blocked": 0, "view_only": 0, "modify_or_access": 0}
              for name in sorted(access_fields | two_level_fields)}
    defaults = type_reported = privilege_present = invalid = unknown = 0
    for role in result:
        if not isinstance(role, dict) or len(role) > 8:
            invalid += 1
            continue
        unknown += len(set(role) - {"id", "name", "defaultRole", "privilege"})
        if "id" in role and (not isinstance(role["id"], str) or len(role["id"]) > 128):
            invalid += 1
        if "name" in role:
            if type(role["name"]) is int and 0 <= role["name"] <= 2_147_483_647:
                type_reported += 1
            else:
                invalid += 1
        if "defaultRole" in role:
            if type(role["defaultRole"]) is bool:
                defaults += int(role["defaultRole"])
            else:
                invalid += 1
        if "privilege" not in role:
            continue
        privilege_present += 1
        privilege = role["privilege"]
        if not isinstance(privilege, dict) or len(privilege) > 32:
            invalid += 1
            continue
        unknown += len(set(privilege) - known_fields)
        for field, value in privilege.items():
            if field == "mspLicenseBind":
                if type(value) is not int or not -(2 ** 31) <= value < 2 ** 31:
                    invalid += 1
                continue
            allowed = {0, 1, 2} if field in access_fields else {0, 2}
            if field not in levels or type(value) is not int or value not in allowed:
                invalid += 1
                continue
            target = {0: "blocked", 1: "view_only", 2: "modify_or_access"}[value]
            levels[field][target] += 1
    return {"data": {"role_count": len(result), "default_role_count": defaults,
                     "role_type_reported_count": type_reported,
                     "roles_with_privileges": privilege_present,
                     "permission_level_counts": levels,
                     "privilege_metadata_reported_count": sum(
                         1 for role in result if isinstance(role, dict) and
                         isinstance(role.get("privilege"), dict) and
                         "mspLicenseBind" in role["privilege"])},
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(invalid or unknown)}
