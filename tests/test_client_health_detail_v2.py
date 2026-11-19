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
        self.assertNotIn("hidden", str(projection))

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
        refresh.assert_called_once_with(SITE_REF)
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
