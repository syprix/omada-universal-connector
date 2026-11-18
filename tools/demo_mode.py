#!/usr/bin/env python3
"""Run the existing WLAN text report against fixed synthetic data, offline."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.channel_dashboard import project_site_dashboard_channels
from app.client_signal_distribution import project_client_signal_distribution
from app.rogue_ap_results import summarize_rogue_ap_results
from app.wifi_health import project_wifi_health
from app.wifi_subhealth import project_wifi_subhealth
from app.wids_summary import summarize_wids_blacklist, summarize_wids_results
from tools import wifi_diagnose

SITE_REF = "a" * 24
START_MS = 1_800_000_000_000
END_MS = START_MS + 86_400_000


def _payloads() -> dict[str, object]:
    common = {"summaryScore": 82, "support": True,
              "scores": [{"time": END_MS, "score": 82}]}
    details = {
        "wifiHealthScore": 82,
        "accessTimeScoreDetail": dict(common),
        "channelUtilScoreDetail": dict(common),
        "accessCapacityScoreDetail": dict(common),
        "rssiScoreDetail": dict(common),
        "channelInterUtilDetail": {
            **common, "averageInterf2g": 14, "averageInterf5g": 9,
            "averageInterf6g": 4, "averageNoiseFloor": -91,
        },
        "wirelessClientQualityDetail": {
            "summaryScore": 82, "support": True,
            "assocTime": [{"time": END_MS, "pastNum": 3}],
            "authTime": [{"time": END_MS, "pastNum": 2}],
            "dhcpTime": [{"time": END_MS, "pastNum": 1}],
            "dnsTime": [{"time": END_MS, "pastNum": 1}],
            "averageAssocTime": 3, "averageAuthTime": 2,
            "averageDhcpTime": 1, "averageDnsTime": 1,
        },
    }
    channels = project_site_dashboard_channels({
        "2g channel stat": [{"channel": 6, "apNum": 2, "clientNum": 4,
                             "channelUtilization": 24}],
        "5g channel stat": [{"channel": 36, "apNum": 2, "clientNum": 5,
                             "channelUtilization": 12}],
        "6g channel stat": [{"channel": 5, "apNum": 1, "clientNum": 2,
                             "channelUtilization": 7}],
    })
    signal = project_client_signal_distribution({
        category: {"totalClients": count, "clientsPercent": count * 10,
                   "clients2g": count // 2, "clients5g": count // 2,
                   "clients6g": 0}
        for category, count in (("poorSignal", 1), ("weakSignal", 2),
                                ("averageSignal", 3), ("stableSignal", 5),
                                ("strongSignal", 4))
    })
    channels["site_ref"] = SITE_REF
    signal["site_ref"] = SITE_REF
    results: dict[str, object] = {
        "/v1/sites": {"status": "ok", "items": [{"site_ref": SITE_REF}]},
    }
    routes = {
        "wifi_health_timeline": {"status": "ok", "resource": "wifi_health",
                                 "data": project_wifi_health(
                                     {"scores": [{"time": END_MS, "score": 82}]},
                                     START_MS, END_MS)},
        "wifi_health_details": project_wifi_subhealth(details, START_MS, END_MS),
        "wifi_channels": channels,
        "client_signal_distribution": signal,
        "site_6ghz_ap_presence": {"status": "ok", "resource": "site_6ghz_ap_presence",
                                  "data": {"has_6ghz_ap": True}},
        "site_rogue_ap_results": summarize_rogue_ap_results([]),
        "site_wids_summary": summarize_wids_results([], 0),
        "site_wids_blacklist_summary": summarize_wids_blacklist([], 0),
        "band_steering": {"status": "ok", "resource": "band_steering",
                           "data": {"mode": 1}},
        "rrm_settings": {"status": "ok", "resource": "rrm_settings",
                         "data": {"mode": 1, "timeRangeEnable": False,
                                  "resource": 0, "timeRangeAction": 1},
                         "partial": False, "omitted_field_count": 0},
        "roaming_settings": {"status": "ok", "resource": "roaming_settings",
                             "data": {"fastRoamingEnable": True,
                                      "aiRoamingEnable": False,
                                      "dualBand11kReportEnable": True,
                                      "forceDisassociationEnable": False,
                                      "nonStickRoamingEnable": True},
                             "partial": False, "omitted_field_count": 0},
        "site_topology_network_summary": {
            "status": "ok", "resource": "site_topology_network_summary",
            "data": {"unknown_field_count": 0, "split_network_count": 2,
                     "default_network_count": 1, "configuring_network_count": 0,
                     "unknown_network_field_count": 0, "ssid_count": 3,
                     "ssid_vlan_enabled_count": 1, "ssid_configuring_count": 0,
                     "ssid_client_count_sum": 6, "ssid_vlan_id_count": 2,
                     "unknown_ssid_field_count": 0, "partial": False},
            "partial": False,
        },
    }
    for name, path in wifi_diagnose._DIAGNOSTIC_ROUTES:
        payload = routes[name]
        results[path.format(site_ref=SITE_REF)] = {**payload, "site_ref": SITE_REF}
    return results


def run_demo() -> str:
    payloads = _payloads()
    seen: list[str] = []

    def synthetic_request(path: str) -> object:
        seen.append(path)
        if path not in payloads:
            raise wifi_diagnose.CliError("response_invalid")
        return payloads[path]

    report = wifi_diagnose.run(SITE_REF, token_file="", requester=synthetic_request)
    expected = {"/v1/sites", *(path.format(site_ref=SITE_REF)
                                for _name, path in wifi_diagnose._DIAGNOSTIC_ROUTES)}
    if set(seen) != expected or len(seen) != len(expected):
        raise wifi_diagnose.CliError("response_invalid")
    return ("DEMO — alle Werte sind synthetisch; keine Controller- oder Netzwerkanfrage.\n\n" +
            wifi_diagnose._render_text(report))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", choices=("wifi-site",), default="wifi-site")
    try:
        parser.parse_args(argv)
        print(run_demo())
        return 0
    except wifi_diagnose.CliError:
        print("Demo fehlgeschlagen; es wurden keine externen Anfragen ausgeführt.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
