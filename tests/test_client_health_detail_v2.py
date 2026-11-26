from __future__ import annotations

import unittest
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.client_health_detail_v2 import (
    ClientHealthDetailV2Error,
    project_client_health_detail_v2,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF = "a" * 24
CLIENT_REF = "b" * 24


class ClientHealthDetailV2ProjectionTests(unittest.TestCase):
    def test_source_matrix_limits_documented_support_scope(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        sources = {source["label"]: source for source in matrix["sources"]}
        expected = {
            "Hardware Controller 6.3.0": True,
            "CBC Standard 6.3.0": True,
            "ER7212PC 6.2.14": False,
        }
        for label, documented in expected.items():
            with self.subTest(source=label):
                self.assertEqual(
                    sources[label]["operations"]["client_health_detail_v2"]["documented"],
                    documented)
                self.assertEqual(
                    sources[label]["operations"]["client_health_detail_v2"]["live_support"],
                    "unknown")

    def test_projects_documented_metrics_and_redacts_incident_objects(self) -> None:
        result = project_client_health_detail_v2({
            "score": 87,
            "onboardingTime": {
                "summaryScore": 78, "support": True,
                "averageAssocTime": 120, "assocTime": [
                    {"time": 1000, "pastNum": 40},
                    {"time": 2000, "pastNum": 80}],
                "incidents": [{"count": 3, "incidentId": "secret", "macs": ["00:11:22:33:44:55"]}],
            },
            "bandRssi": {"averageNum5g": -61,
                         "pastNums5g": [{"time": 1500, "pastNum": -60}]},
            "dataRate": {"averageTxRate": 10000000000,
                          "pastTxRate": [{"time": 1800, "pastNum": 2500000000}]},
            "snr": {"averageNum": 24, "pastNums": []},
            "connectScore": {"connectStatus": 1},
            "linkErrorScore": {"pastNums": [{"time": 1700, "pastNum": 0}]},
            "incident": {"incidentNum": 2},
        })
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["score"], 87)
        self.assertEqual(result["dimension_count"], 7)
        self.assertEqual(result["dimensions"]["onboarding_time"]["series"]["association_time"], {
            "sample_count": 2, "first_time_ms": 1000, "last_time_ms": 2000,
            "minimum": 40, "maximum": 80, "average": 60,
        })
        self.assertEqual(result["incident_entry_count"], 1)
        self.assertEqual(result["dimensions"]["onboarding_time"]["incident_occurrence_count"], 3)
        self.assertNotIn("secret", str(result))
        self.assertNotIn("00:11:22:33:44:55", str(result))

    def test_series_values_use_documented_inclusive_integer_ranges(self) -> None:
        result = project_client_health_detail_v2({
            "snr": {"pastNums": [
                {"time": 1000, "pastNum": -(2**31)},
                {"time": 2000, "pastNum": 2**31 - 1},
            ]},
            "dataRate": {"pastTxRate": [
                {"time": 1000, "pastNum": -(2**63)},
                {"time": 2**63 - 1, "pastNum": 2**63 - 1},
            ]},
        })
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["dimensions"]["snr"]["series"]["values"]["minimum"], -(2**31))
        self.assertEqual(result["dimensions"]["snr"]["series"]["values"]["maximum"], 2**31 - 1)
        tx = result["dimensions"]["data_rate"]["series"]["transmit_rate"]
        self.assertEqual(tx["minimum"], -(2**63))
        self.assertEqual(tx["maximum"], 2**63 - 1)
        self.assertEqual(tx["last_time_ms"], 2**63 - 1)

    def test_value_above_int32_is_valid_only_in_documented_long_rate_series(self) -> None:
        above_int32 = 2**31
        result = project_client_health_detail_v2({
            "snr": {"pastNums": [{"time": 1000, "pastNum": above_int32}]},
            "dataRate": {
                "pastTxRate": [{"time": 1000, "pastNum": above_int32}],
                "pastRxRate": [{"time": 1000, "pastNum": above_int32}],
            },
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_entry_or_field_count"], 1)
        self.assertEqual(result["dimensions"]["snr"]["series"]["values"]["sample_count"], 0)
        rates = result["dimensions"]["data_rate"]["series"]
        self.assertEqual(rates["transmit_rate"]["maximum"], above_int32)
        self.assertEqual(rates["receive_rate"]["maximum"], above_int32)

    def test_series_rejects_bool_and_malformed_shapes_without_coercion(self) -> None:
        result = project_client_health_detail_v2({
            "snr": {"pastNums": [True, {"time": 1000, "pastNum": True}]},
            "linkErrorScore": {"pastNums": {"time": 1000, "pastNum": 1}},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_entry_or_field_count"], 2)
        self.assertEqual(result["dimensions"]["snr"]["series"]["values"]["sample_count"], 0)
        self.assertNotIn("pastNum", str(result))
        self.assertNotIn("1000", str(result))

    def test_series_coverage_distinguishes_missing_null_and_non_null_without_changing_projection(self) -> None:
        result = project_client_health_detail_v2({
            "snr": {"pastNums": [
                {"time": 1000},
                {"time": 2000, "pastNum": None},
                {"time": 3000, "pastNum": 0},
                {"time": 4000, "pastNum": "malformed"},
                {"time": "bad", "pastNum": None},
                {"time": 5000, "pastNum": None, "unexpected": True},
            ]},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_entry_or_field_count"], 6)
        self.assertEqual(result["dimensions"]["snr"]["series"]["values"], {
            "sample_count": 1, "first_time_ms": 3000, "last_time_ms": 3000,
            "minimum": 0, "maximum": 0, "average": 0,
        })
        self.assertEqual(result["series_point_coverage"], {
            "inspected_structurally_valid_count": 4,
            "past_num_missing_count": 1,
            "past_num_explicit_null_count": 1,
            "past_num_present_non_null_count": 2,
        })
        self.assertNotIn("malformed", str(result))
        self.assertNotIn("1000", str(result))

    def test_series_coverage_stops_at_existing_64_point_cap(self) -> None:
        for sample_count, omitted in ((64, 0), (65, 1)):
            with self.subTest(sample_count=sample_count):
                result = project_client_health_detail_v2({
                    "snr": {"pastNums": [
                        {"time": index + 1, "pastNum": None}
                        for index in range(sample_count)]},
                })
                self.assertEqual(result["series_point_coverage"], {
                    "inspected_structurally_valid_count": 64,
                    "past_num_missing_count": 0,
                    "past_num_explicit_null_count": 64,
                    "past_num_present_non_null_count": 0,
                })
                self.assertEqual(result["omitted_series_limit"], omitted)
                self.assertTrue(result["partial"])
                self.assertEqual(result["dimensions"]["snr"]["series"]["values"],
                                 {"sample_count": 0})

    def test_bounds_series_and_incidents_and_marks_partial(self) -> None:
        projection = project_client_health_detail_v2({
            "snr": {"pastNums": [
                {"time": index, "pastNum": index} for index in range(70)],
                "incidents": [{"count": 1, "incidentId": "hidden"} for _ in range(35)]},
        })
        self.assertTrue(projection["partial"])
        self.assertEqual(projection["omitted_series_limit"], 6)
        self.assertEqual(projection["omitted_incident_entry_count"], 3)
        self.assertEqual(projection["dimensions"]["snr"]["series"]["values"]["sample_count"], 64)
        self.assertEqual(projection["incident_entry_count"], 32)
        self.assertIsNone(projection["dimensions"]["snr"]["incident_occurrence_count"])
        self.assertNotIn("hidden", str(projection))

    def test_empty_or_null_incident_collection_means_zero_but_empty_record_count_is_unknown(self) -> None:
        projection = project_client_health_detail_v2({
            "snr": {"incidents": []},
            "dataRate": {"incidents": None},
        })
        self.assertEqual(projection["status"], "ok")
        self.assertEqual(projection["incident_entry_count"], 0)
        for dimension in ("snr", "data_rate"):
            self.assertEqual(projection["dimensions"][dimension]["incident_entry_count"], 0)
            self.assertEqual(projection["dimensions"][dimension]["incident_occurrence_count"], 0)

        missing = project_client_health_detail_v2({
            "snr": {"incidents": [{"incidentId": "private"}]},
        })
        self.assertEqual(missing["incident_entry_count"], 1)
        self.assertIsNone(missing["dimensions"]["snr"]["incident_occurrence_count"])
        self.assertTrue(missing["partial"])
        self.assertNotIn("private", str(missing))

    def test_invalid_or_null_occurrence_count_keeps_entry_and_unknown_total(self) -> None:
        for count in (None, "bad", True, -1, 1_000_001):
            with self.subTest(count_type=type(count).__name__):
                projection = project_client_health_detail_v2({
                    "snr": {"incidents": [{"count": count}]},
                })
                self.assertEqual(projection["incident_entry_count"], 1)
                self.assertIsNone(projection["dimensions"]["snr"]["incident_occurrence_count"])
                self.assertTrue(projection["partial"])
        zero = project_client_health_detail_v2({"snr": {"incidents": [{"count": 0}]}})
        self.assertEqual(zero["incident_entry_count"], 1)
        self.assertEqual(zero["dimensions"]["snr"]["incident_occurrence_count"], 0)

    def test_unknown_fields_and_invalid_shapes_are_not_reported_as_complete(self) -> None:
        projection = project_client_health_detail_v2({"score": 87, "private": "do-not-return"})
        self.assertEqual(projection["status"], "partial")
        self.assertEqual(projection["unknown_field_count"], 1)
        self.assertNotIn("do-not-return", str(projection))
        projection = project_client_health_detail_v2({"score": True, "snr": {"pastNums": "bad"}})
        self.assertEqual(projection["status"], "partial")
        self.assertEqual(projection["invalid_entry_or_field_count"], 1)
        with self.assertRaises(ClientHealthDetailV2Error):
            project_client_health_detail_v2([])

    def test_schema_integer_scores_are_returned_without_assuming_a_scale(self) -> None:
        result = project_client_health_detail_v2({
            "score": 120,
            "snr": {"summaryScore": -3, "averageNum": 22},
        })
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["score"], 120)
        self.assertEqual(result["dimensions"]["snr"]["summary_score"], -3)


class ClientHealthDetailV2ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._client_macs_by_site_ref[SITE_REF] = {CLIENT_REF: "00:11:22:33:44:55"}

    def test_inventory_bound_24h_read_and_source_allowlist(self) -> None:
        end_ms = 1_800_000_000_000
        paths: list[str] = []
        def request(method: str, path: str, **kwargs: object) -> dict[str, object]:
            self.assertEqual(method, "GET")
            paths.append(path)
            return {"errorCode": 0, "result": {"score": 81, "snr": {"averageNum": 22}}}
        with patch.object(self.client, "list_clients") as refresh, \
                patch.object(self.client, "_access_token", return_value="access"), \
                patch.object(self.client, "_request_json", side_effect=request), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = datetime.fromtimestamp(end_ms / 1000, timezone.utc)
            result = self.client.read_client_health_detail_v2(SITE_REF, CLIENT_REF)
        refresh.assert_not_called()
        self.assertEqual(paths, [
            "/openapi/v2/ctrl/sites/site_1/clients/00:11:22:33:44:55/health/detail"
            "?start=1799913600000&end=1800000000000"])
        self.assertEqual(result["window_end_ms"] - result["window_start_ms"], 86_400_000)
        self.assertEqual(result["dimensions"]["snr"]["average"], 22)

    def test_series_outside_requested_window_is_discarded_and_marks_partial(self) -> None:
        end_ms = 1_800_000_000_000
        with patch.object(self.client, "list_clients"), \
                patch.object(self.client, "_access_token", return_value="access"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"snr": {"pastNums": [
                        {"time": end_ms + 1, "pastNum": 25}]}}}), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = datetime.fromtimestamp(end_ms / 1000, timezone.utc)
            result = self.client.read_client_health_detail_v2(SITE_REF, CLIENT_REF)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_entry_or_field_count"], 1)
        self.assertEqual(result["dimensions"]["snr"]["series"]["values"],
                         {"sample_count": 0})

    def test_request_path_is_controller_and_window_bound(self) -> None:
        good = ("/openapi/v2/ctrl/sites/site_1/clients/00-11-22-33-44-55/health/detail"
                "?start=1000&end=86401000")
        self.assertTrue(self.client._client_health_detail_v2_request_valid(good))
        for path in (
            good.replace("/ctrl/", "/other/"),
            good.replace("end=86401000", "end=86401001"),
            good + "&includeDetails=true",
            good.replace("00-11-22-33-44-55", "00:11:22:33:44:ZZ"),
        ):
            with self.subTest(path=path):
                self.assertFalse(self.client._client_health_detail_v2_request_valid(path))
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good + "&x=1")

    def test_invalid_reference_does_not_request_upstream(self) -> None:
        with patch.object(self.client, "list_clients") as refresh:
            with self.assertRaisesRegex(OpenApiError, "client_ref_invalid"):
                self.client.read_client_health_detail_v2(SITE_REF, "invalid")
        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
