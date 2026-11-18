from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.wan_incident_window import (
    WanIncidentWindowError, build_wan_incident_window,
)


SITE = "a" * 24
GATEWAY = "b" * 24
START = 1_800_000_000_000
END = START + 60_000


def sources():
    return {
        "current": {"status": "ok", "items": [
            {"link_status": 712, "internet_state": 99, "health_level": 4},
            {"link_status": 712, "internet_state": 99},
        ]},
        "health": {"status": "ok", "window_start_ms": START,
                   "window_end_ms": END, "data": {
            "partial": False,
            "wan_latency": {"values": [
                {"time_ms": START + 1000, "value": 18},
                {"time_ms": END + 1000, "value": 500},
            ]},
            "wan_status": {"packet_loss_values": [
                {"time_ms": START + 2000, "value": 0.1},
            ]},
            "incident": {"incident_count": 3},
        }},
        "timeline": {"status": "ok", "window_start_ms": START,
                     "window_end_ms": END, "partial": False,
                     "data": {"scores": [
                         {"time_ms": START + 1000, "score": 80},
                         {"time_ms": END + 1000, "score": 20},
                     ]}},
        "saved": {"status": "ok", "resource": "gateway_speed_test_results",
                  "data": {"count": 1, "partial": False}},
    }


class WanIncidentWindowTests(unittest.TestCase):
    def test_report_separates_current_and_historical_and_avoids_inference(self):
        value = sources()
        report = build_wan_incident_window(
            site_ref=SITE, gateway_ref=GATEWAY, start_ms=START, end_ms=END,
            as_of_ms=END + 5000, current_status=value["current"],
            health=value["health"], health_timeline=value["timeline"],
            saved_speed_test=value["saved"])
        self.assertEqual(report["current_state"]["undecoded_status_code_counts"], {
            "link_status": {"712": 2}, "internet_state": {"99": 2},
            "health_level": {"4": 1}})
        self.assertIsNone(report["current_state"]["age_ms"])
        self.assertEqual(report["historical_health_observations"]["wan_latency"]["latency"]
                         ["sample_count"], 1)
        self.assertEqual(report["historical_health_observations"]["wan_latency"]["latency"]
                         ["omitted_out_of_window_count"], 1)
        self.assertEqual(report["health_score_timeline"]["sample_count"], 1)
        self.assertEqual(report["undated_incident_count"], 3)
        self.assertFalse(report["saved_speed_test_observations"]["included_in_time_window"])
        self.assertEqual(report["load_balance_participation"]["status"], "unknown")
        self.assertEqual(report["interpretation"], "observations_only_no_outage_or_switch_inference")
        self.assertTrue(report["partial"])

    def test_unknown_load_balance_object_is_never_projected(self):
        value = sources()
        report = build_wan_incident_window(
            site_ref=SITE, gateway_ref=GATEWAY, start_ms=START, end_ms=END,
            as_of_ms=END, current_status=value["current"], health=value["health"],
            health_timeline=value["timeline"], saved_speed_test=value["saved"],
            load_balance_status={"status": "ok", "result": {"secret": "private"}})
        self.assertEqual(report["load_balance_participation"]["source_result"],
                         "opaque_object_withheld")
        self.assertNotIn("private", repr(report))

    def test_health_window_mismatch_is_reported_without_joining(self):
        value = sources()
        value["health"]["window_end_ms"] = END - 1
        report = build_wan_incident_window(
            site_ref=SITE, gateway_ref=GATEWAY, start_ms=START, end_ms=END,
            as_of_ms=END, current_status=value["current"], health=value["health"],
            health_timeline=value["timeline"], saved_speed_test=value["saved"])
        self.assertEqual(report["historical_health_observations"], {})
        self.assertIsNone(report["undated_incident_count"])
        self.assertTrue(report["partial"])

    def test_time_window_and_numeric_fields_are_strict(self):
        value = sources()
        with self.assertRaises(WanIncidentWindowError):
            build_wan_incident_window(
                site_ref=SITE, gateway_ref=GATEWAY, start_ms=START,
                end_ms=START + 86_400_001, as_of_ms=END,
                current_status=value["current"], health=value["health"],
                health_timeline=value["timeline"], saved_speed_test=value["saved"])
        value["health"]["data"]["wan_latency"]["values"].append(
            {"time_ms": START + 3000, "value": float("nan")})
        report = build_wan_incident_window(
            site_ref=SITE, gateway_ref=GATEWAY, start_ms=START, end_ms=END,
            as_of_ms=END, current_status=value["current"], health=value["health"],
            health_timeline=value["timeline"], saved_speed_test=value["saved"])
        summary = report["historical_health_observations"]["wan_latency"]["latency"]
        self.assertEqual(summary["omitted_invalid_count"], 1)
        self.assertTrue(summary["partial"])

    def test_client_bundles_only_four_existing_readers_with_same_window(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        calls = []
        with (patch.object(client, "read_gateway_wan_status", side_effect=lambda *a:
                           calls.append(("current", a)) or sources()["current"]),
              patch.object(client, "read_gateway_health", side_effect=lambda *a:
                           calls.append(("health", a)) or sources()["health"]),
              patch.object(client, "read_gateway_health_timeline", side_effect=lambda *a:
                           calls.append(("timeline", a)) or sources()["timeline"]),
              patch.object(client, "read_gateway_speed_test_results", side_effect=lambda *a:
                           calls.append(("saved", a)) or sources()["saved"]),
              patch("app.openapi.datetime") as datetime_mock):
            datetime_mock.now.return_value.timestamp.return_value = END / 1000 + 10
            result = client.read_gateway_wan_incident_window(
                SITE, GATEWAY, START, END)
        self.assertEqual([name for name, _ in calls],
                         ["current", "health", "timeline", "saved"])
        self.assertEqual(calls[1][1], (SITE, GATEWAY, START, END))
        self.assertEqual(calls[2][1], (SITE, GATEWAY, START, END))
        self.assertEqual(result["resource"], "gateway_wan_incident_window")

    def test_client_rejects_invalid_window_before_reading(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        with self.assertRaises(OpenApiError):
            client.read_gateway_wan_incident_window(SITE, GATEWAY, END, START)


if __name__ == "__main__":
    unittest.main()
