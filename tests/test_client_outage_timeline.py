from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.client_outage_timeline import project_client_outage_timeline


class ClientOutageTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client_ref = "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-internal"
        self.client._client_macs_by_site_ref[self.site_ref] = {
            self.client_ref: "00-11-22-33-44-55"}
        self.client._device_macs_by_site_ref[self.site_ref] = {
            "c" * 24: "00-11-22-33-44-66",
            "d" * 24: "00-11-22-33-44-77"}
        self.start_ms = 1_789_372_800_000
        self.end_ms = self.start_ms + 60 * 60 * 1000

    def test_aggregator_uses_same_window_redacts_identity_and_marks_site_context(self):
        now_ms = self.end_ms + 1_000
        calls = []

        def client_timeline(site_ref, client_ref, kind, start_ms, end_ms):
            calls.append(("client", kind, start_ms, end_ms))
            event_type = {"connect": 0, "association": 0, "roaming": 2,
                          "disconnect": 1}[kind]
            event = {"time_ms": self.start_ms + 10_000,
                     "event_type": event_type, "content": "private detail"}
            if kind == "roaming":
                event["access_point_ref"] = "c" * 24
            return {"status": "ok", "data": {"sessions": [{"events": [event]}]},
                    "partial": False, "missing_fields": [], "omitted_field_count": 0}

        def health(site_ref, client_ref, start_ms, end_ms):
            calls.append(("health", start_ms, end_ms))
            return {"status": "ok", "data": {"scores": [
                {"time_ms": self.start_ms + 30_000, "score": 72}]},
                "partial": False, "missing_fields": [], "omitted_field_count": 0}

        def site_logs(site_ref, kind, start_ms, end_ms):
            calls.append((kind, start_ms, end_ms))
            return {"status": "ok", "returned_count": 3, "total_count": 3,
                    "partial": False, "module_counts": {"device": 3},
                    "pagination": {"pages_fetched": 1, "page_size": 100,
                                   "page_limit": 10, "page_limit_reached": False},
                    "first_event_ms": self.start_ms + 5_000,
                    "last_event_ms": self.end_ms - 5_000}

        def ap_health(site_ref, ap_ref, start_ms, end_ms):
            calls.append(("ap_health", ap_ref, start_ms, end_ms))
            return {"status": "ok", "data": {"scores": [
                {"time_ms": self.start_ms + 40_000, "score": 86}]},
                "partial": False, "missing_fields": [], "omitted_field_count": 0}

        with patch.object(self.client, "read_client_timeline", side_effect=client_timeline), \
                patch.object(self.client, "read_client_health_timeline", side_effect=health), \
                patch.object(self.client, "read_site_log_window_summary", side_effect=site_logs), \
                patch.object(self.client, "read_ap_health_timeline", side_effect=ap_health), \
                patch.object(self.client, "read_controller_retention", return_value={
                    "status": "ok", "partial": False,
                    "data": {"retention_values": {"client_history": 31}}}), \
                patch.object(self.client, "read_controller_client_history_retention", return_value={
                    "status": "ok", "partial": False,
                    "data": {"client_history_enabled": True}}), \
                patch.object(self.client, "list_devices", return_value={"status": "ok"}), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value.timestamp.return_value = now_ms / 1000
            result = self.client.read_client_outage_timeline(
                self.site_ref, self.client_ref, self.start_ms, self.end_ms)

        self.assertEqual(len(calls), 8)
        self.assertEqual(result["roaming_events"], [
            {"time_ms": self.start_ms + 10_000, "event_type": 2,
             "access_point_ref": "c" * 24}])
        self.assertEqual(result["health_scores"], [
            {"time_ms": self.start_ms + 30_000, "score": 72}])
        self.assertEqual(result["sources"]["health_scores"]["data_age_ms"], 3_571_000)
        self.assertIsNone(result["sources"]["site_event_context"]["events"][
            "timestamp_age_ms"])
        self.assertTrue(result["site_wide_event_context_only"])
        self.assertEqual(result["connection_cause"], "not_inferred")
        self.assertTrue(result["ap_assignment_available"])
        self.assertEqual(result["history_coverage"]["client_event_bounds_ms"], {
            "earliest": self.start_ms + 10_000, "latest": self.start_ms + 10_000})
        self.assertEqual(result["history_coverage"]["controller_retention"]["data"][
            "retention_values"]["client_history"], 31)
        self.assertEqual(result["history_coverage"]["completeness"],
                         "unknown_without_source_total_sample_evidence")
        self.assertEqual(result["history_coverage"]["ap_health_coverage"]["c" * 24][
            "earliest_timestamp_ms"], self.start_ms + 40_000)
        self.assertNotIn("private detail", str(result))
        self.assertNotIn("00-11-22-33-44-55", str(result))

    def test_client_and_health_upstream_reads_use_the_requested_window(self):
        requests = []

        def request(method, path, **kwargs):
            requests.append(path)
            if "client-timeline" in path:
                return {"result": [{"mac": "00-11-22-33-44-55",
                                    "start": self.start_ms, "end": self.end_ms,
                                    "events": [{"time": self.start_ms + 1000,
                                                "eventType": 2,
                                                "attributes": {
                                                    "old_dev_mac": "00-11-22-33-44-77",
                                                    "dev_mac": "00-11-22-33-44-66"}}]}]}
            return {"result": {"scores": [{"time": self.start_ms + 2000,
                                             "score": 71}]}}

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            event = self.client.read_client_timeline(
                self.site_ref, self.client_ref, "roaming", self.start_ms, self.end_ms)
            health = self.client.read_client_health_timeline(
                self.site_ref, self.client_ref, self.start_ms, self.end_ms)
        event_query = parse_qs(urlsplit(requests[0]).query)
        health_query = parse_qs(urlsplit(requests[1]).query)
        self.assertEqual(event_query, {"start": [str(self.start_ms)],
                                      "end": [str(self.end_ms)], "type": ["2"]})
        self.assertEqual(health_query, {"start": [str(self.start_ms)],
                                       "end": [str(self.end_ms)]})
        projected_event = event["data"]["sessions"][0]["events"][0]
        self.assertEqual(projected_event["event_type"], 2)
        self.assertEqual(projected_event["access_point_ref"], "c" * 24)
        self.assertEqual(projected_event["previous_access_point_ref"], "d" * 24)
        self.assertNotIn("00-11-22-33-44-66", repr(event))
        self.assertEqual(health["data"]["scores"][0]["time_ms"], self.start_ms + 2000)

    def test_failed_inventory_does_not_reuse_stale_ap_mapping(self):
        with patch.object(self.client, "list_devices",
                          side_effect=OpenApiError("source_unavailable")), \
                patch.object(self.client, "read_client_timeline",
                             side_effect=OpenApiError("source_unavailable")), \
                patch.object(self.client, "read_client_health_timeline",
                             side_effect=OpenApiError("source_unavailable")), \
                patch.object(self.client, "read_site_log_window_summary",
                             side_effect=OpenApiError("source_unavailable")), \
                patch.object(self.client, "read_controller_retention",
                             side_effect=OpenApiError("source_unavailable")), \
                patch.object(self.client, "read_controller_client_history_retention",
                             side_effect=OpenApiError("source_unavailable")), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value.timestamp.return_value = (self.end_ms + 1000) / 1000
            result = self.client.read_client_outage_timeline(
                self.site_ref, self.client_ref, self.start_ms, self.end_ms)

        self.assertFalse(result["ap_assignment_available"])
        self.assertNotIn(self.site_ref, self.client._device_macs_by_site_ref)

    def test_empty_samples_remain_unknown_and_page_limit_is_visible(self):
        empty_source = {"status": "ok", "data": {"sessions": []},
                        "partial": False, "missing_fields": [],
                        "omitted_field_count": 0}
        health = {"status": "ok", "data": {"scores": []}, "partial": False,
                  "missing_fields": [], "omitted_field_count": 0}
        page_limited_logs = {
            "status": "ok", "returned_count": 100, "total_count": 800,
            "partial": True, "pagination": {"pages_fetched": 10, "page_size": 10,
                                                "page_limit": 10,
                                                "page_limit_reached": True}}
        result = project_client_outage_timeline(
            self.client_ref, self.start_ms, self.end_ms,
            {kind: empty_source for kind in ("connect", "association", "roaming", "disconnect")},
            health, page_limited_logs, page_limited_logs, self.end_ms + 1000,
            ap_assignment_available=True,
            retention_result={"status": "ok", "partial": False,
                              "data": {"retention_values": {"client_history": 31}}},
            client_retention_result={"status": "ok", "partial": False,
                                     "data": {"client_history_enabled": True}})

        self.assertEqual(result["history_coverage"]["completeness"],
                         "unknown_without_source_total_sample_evidence")
        self.assertEqual(result["history_coverage"]["client_event_bounds_ms"],
                         {"earliest": None, "latest": None})
        self.assertTrue(result["partial"])
        self.assertTrue(result["history_coverage"]["site_log_coverage"]["events"][
            "pagination"]["page_limit_reached"])


if __name__ == "__main__":
    unittest.main()
