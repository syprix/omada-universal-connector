#!/usr/bin/env python3
"""Build an offline, comparative matrix from supplied Omada OpenAPI JSON/ZIP files.

The report contains documentation metadata and source-code route matches only.
It never contacts a controller and does not claim live support.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.spec_catalog import SpecCatalogError, _read_zip, _parse_spec  # noqa: E402


# Templates are those present in the connector source. Placeholders are
# canonicalized below, so differing vendor parameter names still compare.
IMPLEMENTED: dict[tuple[str, str], str] = {
    # This hand-maintained list is a partial source review. It is not generated
    # from the adapter code and does not establish runtime/live support.
    ("GET", "/openapi/v1/{controller_id}/sitetemplates"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sitetemplates/{site_template_id}/setting/service/iptv/igmp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sitetemplates/{site_template_id}/upnp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sitetemplates/{site_template_id}/ssh"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sitetemplates/{site_template_id}/setting/service/iptv/iptv"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sitetemplates/{site_template_id}/setting/service/iptv"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/global/gateways/wan-status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/scenarios"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/scenarios/difference"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/security/threat-management"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/controller/setting/client-recognition"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/devices/stat"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/controller/setting/active-timeout"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/controller/setting/ui-interface"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/controller/setting/retention"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/dst-info"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/global/controller/setting/exp-improve"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/client-detail-information"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/global/controller/setting/general"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/controller/setting/services/device-access"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/backupschedule/task"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/cloud/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/device-mgmt"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/cloud/remote/bind/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/maintenance/backup/result"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/maintenance/restore/result"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/privacy-policy"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/mail/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/mfa/status"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/cloud/status"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/privacy-policy"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/client-detail-information"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/audit-notification"): "implemented_read",
    ("GET", "/openapi/v2/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/devices/{device_mac}/device-link-topology"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/devices/tag"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/mfa/status"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/license/auto-active"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customer-roles"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/dst-info"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/remote-logging"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/settings/mail-server"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/general-setting"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/log-notification"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/retention"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/ui-interface"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/settings/user-interface"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/roles/available"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/roles/customer/roles/available"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/dashboard/client/overview-diagram"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/cluster/nodes/info"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/adopt-tip"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/roles"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switch-qos/qos-mode"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switch-qos/qos-rule/scheduler-mapping"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switch-qos/qos-rule/dscp-mapping"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/global/controller/setting/syslog"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/global/controller/setting/syslog/tip"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/global/controller/setting/network/radius-proxy"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/global/controller/setting/network/radius-server"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/system/setting/upgrade-port"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/system/setting/portal-port"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/system/setting/controller-port"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/system/setting/controller-status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/system/setting/logging"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/system/setting/certificate"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/roles"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/roles/available"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/devices/known-devices"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/devices/unknown-devices"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/devices/batch/info"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/grid/devices/pending"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/profiles/radius-server/users"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/upnp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/iot/aging-time"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/iot/radio"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/mesh"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/multicast-rate-limit"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/beacon-control"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/iot/radio/transmit-power"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/remember-device"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/client-ssid-distribution"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/poe-usage"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/card/overview"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/lpset-tunnel-stats"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/client-association-time-distribution"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/allNetworkActivity"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/client-rssi-distribution"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/ap-density"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/client-distribution"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/client-freq-distribution"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/traffic-distribution"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/past-client-num"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/current-client-num"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/gateway/isp/load"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/top-aps"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/most-active-eaps"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/dashboard/most-active-eaps"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/hotspot/dashboard/statistics"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/most-active-switches"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/top-device-memory-usage"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/switch-summary"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/top-interference"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/categoryInfo"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/categoryAppInfo/{family_id}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/categoryUserInfo/{family_id}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/mostActiveAppTraffic"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/active-clients"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/top-device-cpu-usage"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/clients-bubble"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/traffic-activities"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/isp-load"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/vpn-tunnel-stats"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/open-vpn-tunnel-stats"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/client-activity"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/client-association-activities"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/clientTraffic"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/vpn/gre-tunnel"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/vpn/ssl-vpn-server/setting"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/ssh"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/mld"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/igmp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sitetemplates"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sitetemplates/{site_template_id}/setting/service/iptv/igmp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sitetemplates/{site_template_id}/upnp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/iptv"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices/tag"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/unresolved-incidents"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/overview/statistics"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/overview/incident-distribution"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/category"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/incidents"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/full-channel-detect/grid/scan-history"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/full-channel-detect/{history_id}/ap-list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/full-channel-detect/{history_id}/grid/wifi-interference"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/full-channel-detect/{history_id}/channel-load"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/full-channel-detect/{history_id}/grid/interference"): "implemented_read",
    ("POST", "/openapi/v1/{controller_id}/sites/{site_id}/full-channel-detect/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/full-channel-detect/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/lan-networks/{network_id}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/full-channel-detect/grid/interference"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/grid/full-channel-detect/ap-list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/health/incident/{mac}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/incident/{incidentId}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/notification"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/setting"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/{mac}/influencing-clients"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/anomaly/{mac}/influencing-devices"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/cmd/countWlans"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/count-ap-groups"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/ap-groups"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/ap-oui-rules"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/networks/{network_id}/vlan/{vlan_id}/ssids"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/networks/{network_id}/vlan/{vlan_id}/devices"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/profiles/wifi-calling"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/clients/search-fields-options"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dot1x/eap/candidates"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dot1x/candidates"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/ap-groups"): "implemented_read",
    ("PATCH", "/openapi/v1/{controller_id}/global/controller/setting/network/radius-proxy"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/dashboard/overview-without-client"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/security/threat-management/severity"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/security/threat-management/severity"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/overview-diagram"): "implemented_read",
    ("GET", "/openapi/v3/{controller_id}/sites/{site_id}/topology"): "implemented_read",
    ("GET", "/openapi/v3/{controller_id}/sites/{site_id}/lan-networks"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/lan-networks/all"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/longest-uptime"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/attack-defense/default"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/ssids"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/health/client/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/experienceIndex"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rfPlanning/result"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rfPlanning/dashboard/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rfPlanning/dashboard/history"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rfPlanning/dashboard"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rfplanning/history"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/wifi-summary"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/multi-band-6g/exist"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/insight/rogueaps"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/insight/wids"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/insight/wids/blacklist"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/exist"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/capacity"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/ssids/duplicate-name"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/ssids/{ssid_id}/ap-groups"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/topology/available-network"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/topology/available-vlans"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/wireless-network/wlans/{wlan_id}"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/lockToAp/aps"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/full-channel-detect/batch/info"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switch-support"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/networks/{network_id}/dhcp-server/capabilities"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/networks/{network_id}/dhcp-server-info"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rfPlanning"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/planningHistory"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/planningHistory/{history_id}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/planningHistoryByTime"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rfPlanning/excludeAps"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/clients"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/clients/{client_mac}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/clients/{client_mac}/client-connection"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/clients/{client_mac}/health/detail"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/clients/{client_mac}/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/clients/{client_mac}/client-history"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices/{device_mac}/latest-firmware-info"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices/{device_mac}/adopt-result"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices/{device_mac}/check-mac-type"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/devices/{device_mac}/device-link-topology"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices/un-support-radsec"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices/{device_mac}/online-upgrade-result"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices/{device_mac}/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/devices/all"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/controller/client/history-enable"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/system/system-info/configs"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/olts/{device_mac}"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/olts/{device_mac}/l2-feature/eth-port/port/unit1/list"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/eth-port/and/pon-port/list"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/olts/{device_mac}/pon/pon-port/configs/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/eth-port/and/pon-port/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/onu-management/global-config/get"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/onu-management/global-config/isolation/get"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/l2-feature/eth-port/port/unit1/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/l2-feature/eth-port/port/lags/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/service-port/statistic/configs"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/pon-port/informations/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/pon-port/configs/page"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/onu-register/autofinds/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/pon-port/configs/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/profile/service-port/profiles/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/onu-register/auto-authentication/global/configs/get"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/onu-register/autofind/configs/get"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/onu-management/informations/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/pon/onu-management/informations/reboot-status/list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/olts/{device_mac}/system/system-info/configs"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/eaps/{ap_mac}/health/detail"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/aps/{ap_mac}/mesh/statistics"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/gateways/{gateway_mac}/health/detail"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/switches/{switch_mac}/health/detail"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/eaps/{ap_mac}/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/gateways/{gateway_mac}/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/msp/{msp_id}/customers/{customer_id}/sites/{site_id}/switches/{switch_mac}/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/olts/{device_mac}/system/management-system-interface/get"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/lan-networks"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/wireless-network/ssids"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/ssids/{ssid_id}"): "implemented_read",
    ("PATCH", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/ssids/{ssid_id}/enable"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/wireless-network/wlans"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/wan-status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/health/detail"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/sdm-used"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/cable-test/switches/{switch_mac}/logs"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/cable-test/switches/{switch_mac}/full-results"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/cable-test/switches/{switch_mac}/increment-results"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/cable-test/switches/{switch_mac}/ports"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/dhcp/user-list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/ospf-neighbors"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/port-lag-networks"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/exist-network"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/networks"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/interfaces/brief"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/routingTable"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/staticRoutings"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/vrfs"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/vlan-interface/switches/{switch_mac}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/stat/switches/{switch_mac}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/port-tag"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/network/ipv6"): "implemented_read",
    ("PATCH", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/network/ipv6"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/health/gateways/{gateway_mac}/wans/details"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/ports/overview"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/ports/counters"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/applicationControl/status"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/applicationControl/status"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/qos/gateway/voip-prioritization"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/qos/gateway/voip-prioritization"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/qos/gateway/tag-outbound-traffic"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/qos/gateway/tag-outbound-traffic"): "implemented_controlled_write_unverified_live",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/ports/{port}/name"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/ports/poe-info"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/ports/{port}/poe-mode"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/networks-detail"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/acls/osg-acls"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/acls/osw-acls"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/acls/eap-acls"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/dhcp/user-list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/dns-cache"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/dns-cache"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/dns-proxy"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/lan/dns"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/logs/events"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/logs/alerts"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/radio-config"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/available-channel"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/mesh/statistics"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/eaps/{ap_mac}/health/detail"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/eaps/{ap_mac}/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/radios"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/rf-scan-result"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/aps/{ap_mac}/rf-scan-result"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/full-channel-detect/wlan-interference"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/full-channel-detect/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/full-channel-detect/channel-load"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/speed-test-result"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/snmp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/vlan"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/aps/{ap_mac}/override"): "implemented_read",
    ("PATCH", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/radio-config"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wifi/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wifi/sub/health/timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/band-steering"): "implemented_read",
    ("PATCH", "/openapi/v1/{controller_id}/sites/{site_id}/band-steering"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/lldp"): "implemented_read",
    ("PATCH", "/openapi/v1/{controller_id}/sites/{site_id}/lldp"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/led"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/led"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rrm/config"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/rrm/config"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/roaming"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/channel-limit"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rrm/incompatible"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/channels"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/client-signal-distribution"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/allowApp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/blockApp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/tabs"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/without-overall-tabs"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/specificAppInfo/{application_id}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/specificClientInfo/{client_mac}"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/applicationControl/traffics"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wan-lan-status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/arpDetects/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/disaster"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/specification"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/portal-logout"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/network-security/wireless-ids"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/network-security/wireless-ips"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/acls/osg-config-mode"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/attack-defense"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/nat/alg"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/firewall"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/firewall/timeout/default"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/bandwidth-control"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/internet/ports-config"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/networks/vlans"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/internet"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/vpn/stats/tunnel"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/networks/devices"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/networks/server-for-reservation"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/dhcp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dhcpSnoops/status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dhcpSnoops"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/mdns"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/ddns"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/service/snmp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/dashboard/retry-dropped-rate"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/ofdma"): "implemented_read",
    ("PATCH", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/ofdma"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/qos"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/trunk-setting"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/load-balance"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/ant-switch"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/antenna-gain"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/power-saving"): "implemented_read",
    ("GET", "/openapi/v2/{controller_id}/sites/{site_id}/aps/{ap_mac}/vlan"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/wired-uplink"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/wired-downlink"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/ports"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/port-vlans"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/bridge"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/grid/mesh/candiParents"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/general-config"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/ip-setting"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/ipv6-setting"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/p2pInfo"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/l3access"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/paring-window-result"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/management-wlan"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/lag"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/lldp"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/lan-status"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/ports"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/speedTestResult"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/speedTest"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/uplink-config"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/dhcp/user-list"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/internet"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/internet/load-balance"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/internet/basic-info"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/wlans"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/wireless-network/wlans/{wlan_id}/ssids"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/lan-traffic-info"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/channel-limit"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/channel-limit"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/afc-config"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/afc-config"): "implemented_controlled_write_unverified_live",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/afc"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/aps/{ap_mac}/mesh/statistics"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/clients/{client_mac}/client-timeline"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/lldp-neighbors"): "implemented_read",
    ("GET", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/health/detail"): "implemented_read",
    ("PUT", "/openapi/v1/{controller_id}/sites/{site_id}/switches/{switch_mac}/ports/{port}/status"): "implemented_controlled_write_unverified_live",
}
METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
PLACEHOLDER = re.compile(r"\{[^{}]+\}")


def canonical_path(path: str) -> str:
    return PLACEHOLDER.sub("{}", path)


def _parameter(parameter: Any) -> dict[str, Any]:
    if not isinstance(parameter, dict):
        return {"invalid": True}
    schema = parameter.get("schema") if isinstance(parameter.get("schema"), dict) else {}
    content = parameter.get("content") if isinstance(parameter.get("content"), dict) else {}
    return {
        "name": parameter.get("name") if isinstance(parameter.get("name"), str) else None,
        "in": parameter.get("in") if isinstance(parameter.get("in"), str) else None,
        "required": parameter.get("required") is True,
        "style": parameter.get("style") if isinstance(parameter.get("style"), str) else None,
        "explode": parameter.get("explode") if isinstance(parameter.get("explode"), bool) else None,
        "schema_type": schema.get("type") if isinstance(schema.get("type"), str) else None,
        "content_types": sorted(x for x in content if isinstance(x, str)),
    }


def _variants(path_item: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    params: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in (path_item.get("parameters", []), operation.get("parameters", [])):
        if isinstance(raw, list):
            for item in raw:
                parsed = _parameter(item)
                key = (str(parsed.get("in") or ""), str(parsed.get("name") or ""))
                params[key] = parsed
    body = operation.get("requestBody")
    body_obj = body if isinstance(body, dict) else {}
    body_content = body_obj.get("content")
    body_content = body_content if isinstance(body_content, dict) else {}
    responses = operation.get("responses")
    response_codes = sorted(str(k) for k in responses) if isinstance(responses, dict) else []
    servers = operation.get("servers")
    server_urls = sorted(s["url"] for s in servers if isinstance(s, dict) and isinstance(s.get("url"), str)) if isinstance(servers, list) else []
    return {
        "parameters": [params[k] for k in sorted(params)],
        "request_body": {
            "present": isinstance(body, dict),
            "required": body_obj.get("required") is True,
            "content_types": sorted(x for x in body_content if isinstance(x, str)),
        },
        "response_codes": response_codes,
        "servers": server_urls,
    }


def _load_document(path: Path) -> dict[str, Any]:
    max_bytes = 16 * 1024 * 1024
    if path.stat().st_size > max_bytes:
        raise SpecCatalogError("input_too_large")
    if path.suffix.lower() == ".zip":
        raw = _read_zip(path, max_bytes)
    else:
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise SpecCatalogError("input_too_large")
    catalog = _parse_spec(raw)
    document = json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise SpecCatalogError("openapi_document_invalid")
    return {"catalog": catalog, "document": document}


def build_matrix(sources: list[tuple[str, str | Path]]) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    operations_by_source: list[dict[tuple[str, str], dict[str, Any]]] = []
    for label, source in sources:
        path = Path(source)
        loaded = _load_document(path)
        catalog, document = loaded["catalog"], loaded["document"]
        found: dict[tuple[str, str], dict[str, Any]] = {}
        paths = document.get("paths", {})
        for route, path_item in paths.items():
            if not isinstance(route, str) or not isinstance(path_item, dict):
                continue
            for method, detail in path_item.items():
                if not isinstance(method, str) or method.lower() not in METHODS or not isinstance(detail, dict):
                    continue
                key = (method.upper(), route)
                found[key] = {
                    "operation_id": detail.get("operationId") if isinstance(detail.get("operationId"), str) else None,
                    "summary": detail.get("summary") if isinstance(detail.get("summary"), str) else None,
                    "tags": sorted(x for x in detail.get("tags", []) if isinstance(x, str)) if isinstance(detail.get("tags", []), list) else [],
                    "variants": _variants(path_item, detail),
                }
        # Compare equivalent templates across vendor documents even when the
        # placeholder names differ (for example {omadacId} vs {controller_id}).
        canonical_found: dict[tuple[str, str], dict[str, Any]] = {}
        for (method, route), operation in found.items():
            canonical_found[(method, canonical_path(route))] = {
                **operation, "source_path": route,
            }
        operations_by_source.append(canonical_found)
        parsed.append({"label": label, "file_name": path.name, "sha256": catalog.source_sha256,
                       "openapi_version": catalog.openapi_version,
                       "document_version": catalog.info_version,
                       "documented_operation_count": len(found),
                       "documentation_status": "documented_not_live_verified"})

    identities = sorted(set().union(*(set(x) for x in operations_by_source)), key=lambda x: (x[1], x[0]))
    implemented_canonical = {
        (method, canonical_path(path)): value for (method, path), value in IMPLEMENTED.items()
    }
    rows = []
    for method, path in identities:
        template = (method, path)
        status = implemented_canonical.get(template, "unknown_not_reviewed")
        per_source = []
        signatures: set[str] = set()
        for source_ops in operations_by_source:
            operation = source_ops.get(template)
            if operation is None:
                per_source.append({"documented": False})
            else:
                signature = json.dumps(operation["variants"], sort_keys=True, separators=(",", ":"))
                signatures.add(signature)
                per_source.append({"documented": True, **operation})
        rows.append({"method": method, "path": path, "canonical_path": path,
                     "connector_source_status": status,
                     "live_status": "unknown_not_checked_by_this_offline_tool",
                     "variant_count": len(signatures), "sources": per_source})
    return {
        "scope": "offline_documentation_comparison_and_connector_source_route_match_only",
        "live_verification_performed": False,
        "connector_source_mapping_note": (
            "IMPLEMENTED is a manually maintained partial source-review mapping; "
            "it is not an automatic source-code verification and does not establish live support."),
        "connector_source_mapping_is_automatic_verification": False,
        "sources": parsed,
        "source_order": [x[0] for x in sources],
        "operation_count_union": len(rows),
        "operations": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", nargs=2, action="append", metavar=("LABEL", "ZIP_OR_JSON"), required=True)
    parser.add_argument("--output", required=True, help="JSON report destination")
    args = parser.parse_args()
    try:
        report = build_matrix([(label, source) for label, source in args.source])
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, SpecCatalogError, zipfile.BadZipFile) as exc:
        print(f"full_api_matrix: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
