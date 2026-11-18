from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ap_quality_window import (
    ApQualityWindowError, compare_passive_session_to_ap_quality,
    project_ap_quality_window,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig
from tools.compare_ap_quality_session import main as compare_cli


SITE = "a" * 24
AP1 = "b" * 24
AP2 = "c" * 24
START = 1_800_000_000_000
END = START + 86_400_000


def health(ref: str, scores: list[dict[str, object]]) -> dict[str, object]:
    return {"status": "ok", "resource": "ap_health_timeline", "site_ref": SITE,
            "device_ref": ref, "window_start_ms": START, "window_end_ms": END,
            "data": {"scores": scores}, "partial": False}


class ApQualityWindowTests(unittest.TestCase):
    def fixture(self):
        inventory = {"status": "ok", "resource": "devices", "count": 3,
                     "items": [{"device_ref": AP1, "device_type": "ap"},
                               {"device_ref": AP2, "device_type": "Access Point"},
                               {"device_ref": "d" * 24, "device_type": "switch"}]}
        health_by_ref = {
            AP1: health(AP1, [{"time_ms": START + 3_600_000, "score": 88},
                              {"time_ms": START + 3_700_000, "score": 76}]),
            AP2: health(AP2, [{"time_ms": START + 3_600_000, "score": 91}]),
        }
        radio_by_ref = {
            AP1: {"status": "ok", "resource": "radio_config", "device_ref": AP1,
                  "data": {"radioSetting2g": {"channel": 1, "channelWidth": 20,
                                                  "radioEnable": True},
                           "radioSetting5g": {"channel": 36, "txPower": 20,
                                                  "radioEnable": True}}},
            AP2: {"status": "ok", "resource": "radio_config", "device_ref": AP2,
                  "data": {"radioSetting2g": {"channel": 6, "channelWidth": 20,
                                                  "radioEnable": True}}},
        }
        retry_drop = {"status": "ok", "resource": "ap_retry_drop", "site_ref": SITE,
                      "window_start_seconds": START // 1000,
                      "window_end_seconds": END // 1000,
                      "data": {"retry_aps": [{"device_ref": AP1, "status": 0,
                                                "average_rate": 12.5, "sample_count": 2,
                                                "samples": [
                                                    {"time_seconds": START // 1000 + 100,
                                                     "count": 5, "rate": 11.5},
                                                    {"time_seconds": START // 1000 + 200,
                                                     "count": 8, "rate": 12.5}]}],
                               "dropped_aps": [], "partial": False}}
        return inventory, health_by_ref, radio_by_ref, retry_drop

    def test_combines_hourly_health_radio_and_retry_data_without_inference(self):
        result = project_ap_quality_window(SITE, *self.fixture())
        self.assertEqual(result["resource"], "site_ap_quality_window")
        self.assertEqual(result["summary"]["checked_ap_count"], 2)
        self.assertEqual(result["items"][0]["health"]["hourly_score_summary"][0][2], 76)
        self.assertEqual(result["items"][0]["radio"]["bands"]["2g"]["channel"], 1)
        retry = result["items"][0]["retry_drop"]
        self.assertEqual(retry["retry"]["hourly_rate_summary"][0][3], 12.5)
        self.assertEqual(result["data_scope"]["retry_drop_rate_scale"],
                         "unspecified; source rate is per hour")
        self.assertEqual(retry["band_mapping"], "not_returned_by_source")
        self.assertEqual(result["items"][1]["retry_drop"]["status"], "not_listed")
        self.assertEqual(result["data_scope"]["missing_data_is_not_zero"], True)
        self.assertTrue(result["partial"])
        self.assertNotIn("switch", str(result))

    def test_marks_bad_source_rows_partial_and_rejects_invalid_inventory(self):
        inventory, health_by_ref, radio_by_ref, retry_drop = self.fixture()
        health_by_ref[AP1]["data"]["scores"].append({"time_ms": "bad", "score": 3})
        result = project_ap_quality_window(SITE, inventory, health_by_ref,
                                           radio_by_ref, retry_drop)
        self.assertTrue(result["items"][0]["health"]["partial"])
        with self.assertRaises(ApQualityWindowError):
            project_ap_quality_window(SITE, {"status": "ok", "resource": "devices",
                                             "count": 4, "items": []}, {}, {}, None)

    def test_client_composes_only_fixed_site_bound_reads(self):
        inventory, health_by_ref, radio_by_ref, retry_drop = self.fixture()
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-1"

        def read_health(site_ref, device_ref, start_ms, end_ms):
            self.assertEqual(site_ref, SITE)
            return health(device_ref, [{"time_ms": start_ms + 3_600_000, "score": 85}]) | {
                "window_start_ms": start_ms, "window_end_ms": end_ms}

        def read_radio(site_ref, device_ref, part):
            self.assertEqual(site_ref, SITE)
            self.assertEqual(part, "radio_config")
            return radio_by_ref[device_ref]

        def read_retry(site_ref, start_seconds, end_seconds):
            value = self.fixture()[3]
            value["window_start_seconds"] = start_seconds
            value["window_end_seconds"] = end_seconds
            rows = value["data"]["retry_aps"]
            for row in rows:
                for point in row["samples"]:
                    point["time_seconds"] = start_seconds + 100
            return value
        with patch.object(client, "list_devices", return_value=inventory), \
                patch.object(client, "read_ap_health_timeline", side_effect=read_health), \
                patch.object(client, "read_ap_radio_part", side_effect=read_radio), \
                patch.object(client, "read_ap_retry_drop", side_effect=read_retry):
            result = client.read_site_ap_quality_window(SITE)
        self.assertEqual(result["resource"], "site_ap_quality_window")
        self.assertEqual(result["summary"]["checked_ap_count"], 2)

    def test_joins_a_saved_passive_session_by_exact_ap_reference(self):
        quality = project_ap_quality_window(SITE, *self.fixture())
        header = {"record_type": "session", "started_at_ms": START + 3_500_000,
                  "duration_limit_seconds": 240, "interval_seconds": 5,
                  "sample_limit": 12, "schema_version": 1,
                  "collection": "read_only_connector_poll"}
        samples = [{"record_type": "sample", "sample_index": 1,
                    "timestamp_ms": START + 3_600_000,
                    "metrics": {"rssi": -67, "snr": 25, "channel": 36},
                    "access_point_ref": AP1, "sample_status": "ok",
                    "ap_assignment_status": "mapped", "partial": False}]
        footer = {"record_type": "session_end", "finished_at_ms": START + 3_700_000,
                  "sample_count": 1, "stop_reason": "sample_limit"}
        result = compare_passive_session_to_ap_quality(quality, header, samples, footer)
        self.assertEqual(result["resource"], "ap_quality_session_comparison")
        self.assertEqual(result["summary"]["matched_ap_count"], 1)
        self.assertEqual(result["items"][0]["passive_metrics"]["rssi"]["minimum"], -67)
        self.assertEqual(result["items"][0]["passive_metrics"]["channel"]["value_counts"],
                         {36: 1})
        self.assertEqual(result["items"][0]["session_to_health_window"], "overlap")
        self.assertEqual(result["session"]["site_binding"], "not_recorded_in_session_file")

    def test_offline_cli_reads_saved_report_and_private_session(self):
        quality = project_ap_quality_window(SITE, *self.fixture())
        header = {"record_type": "session", "schema_version": 1,
                  "started_at_ms": START + 3_500_000, "duration_limit_seconds": 240,
                  "interval_seconds": 5, "sample_limit": 1,
                  "collection": "read_only_connector_poll"}
        sample = {"record_type": "sample", "sample_index": 1,
                  "timestamp_ms": START + 3_600_000,
                  "metrics": {"rssi": -68, "snr": 24, "channel": 36},
                  "access_point_ref": AP1, "ap_assignment_status": "mapped",
                  "sample_status": "ok", "partial": False}
        footer = {"record_type": "session_end", "finished_at_ms": START + 3_650_000,
                  "sample_count": 1, "stop_reason": "sample_limit"}
        with tempfile.TemporaryDirectory() as directory:
            quality_path, session_path = Path(directory) / "quality.json", Path(directory) / "session.jsonl"
            quality_path.write_text(json.dumps(quality), encoding="utf-8")
            session_path.write_text("\n".join(json.dumps(row) for row in
                                                     (header, sample, footer)) + "\n",
                                    encoding="utf-8")
            quality_path.chmod(0o600)
            session_path.chmod(0o600)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = compare_cli(["--quality-report", str(quality_path),
                                      "--session", str(session_path)])
        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["resource"], "ap_quality_session_comparison")
        self.assertEqual(result["summary"]["matched_ap_count"], 1)


if __name__ == "__main__":
    unittest.main()
