from __future__ import annotations

import json
import math
import unittest

from app.ap_retry_drop import (
    MAX_AP_ROWS_PER_KIND,
    MAX_SAMPLES_PER_AP,
    ApRetryDropProjectionError,
    project_ap_retry_drop,
)


REF1 = "a" * 24
REF2 = "b" * 24


def mac_colons(canonical: str) -> str:
    return ":".join(canonical[index:index + 2] for index in range(0, 12, 2))


class ApRetryDropProjectionTests(unittest.TestCase):
    def test_projects_seconds_and_opaque_refs_while_redacting_identifiers(self) -> None:
        mac = "aabbccddeeff"
        private = (mac_colons(mac), "private AP", "192.0.2.14", "model-secret", "version-secret")
        result = {
            "retryEaps": [{
                "apMac": private[0], "name": private[1], "model": private[3],
                "modelVersion": private[4], "status": 0, "avg": 0.4,
                "retries": [
                    {"time": 99, "retryTimes": 7, "retryRate": 0.2},
                    {"time": 100, "retryTimes": 8, "retryRate": 0.3},
                    {"time": 200, "retryTimes": 9, "retryRate": 0.4},
                ],
            }],
            "droppedEaps": [{
                "apMac": private[0], "name": private[1], "model": private[3],
                "modelVersion": private[4], "status": 1, "avg": 0.05,
                "dropouts": [{"time": 99, "dropTimes": 1, "dropRate": 0.05},
                             {"time": 150, "dropTimes": 2, "dropRate": 0.1}],
            }],
        }

        projected = project_ap_retry_drop(result, 100, 200, {mac: REF1})

        self.assertEqual(projected["retry_aps"][0]["device_ref"], REF1)
        self.assertEqual(projected["retry_aps"][0]["samples"], [
            {"time_seconds": 100, "count": 8, "rate": 0.3},
            {"time_seconds": 200, "count": 9, "rate": 0.4},
        ])
        self.assertEqual(projected["dropped_aps"][0]["samples"], [
            {"time_seconds": 150, "count": 2, "rate": 0.1}])
        self.assertEqual(projected["omitted_out_of_window_sample_count"], 2)
        self.assertEqual(projected["omitted_identifying_field_count"], 8)
        self.assertTrue(projected["partial"])
        rendered = json.dumps(projected)
        for value in private:
            self.assertNotIn(value, rendered)
        self.assertNotIn("apMac", rendered)

    def test_unknown_ambiguous_and_duplicate_aps_are_omitted_and_counted(self) -> None:
        known = "001122334455"
        unknown = "aabbccddeeff"
        ambiguous = "102030405060"
        row = lambda mac: {"apMac": mac_colons(mac), "retries": []}
        projected = project_ap_retry_drop(
            {"retryEaps": [row(known), row(known), row(unknown), row(ambiguous)],
             "droppedEaps": []},
            1, 2,
            {known: REF1, ambiguous: [REF1, REF2]},
        )
        self.assertEqual([item["device_ref"] for item in projected["retry_aps"]], [REF1])
        self.assertEqual(projected["omitted_duplicate_ap_count"], 1)
        self.assertEqual(projected["omitted_unknown_ap_count"], 1)
        self.assertEqual(projected["omitted_ambiguous_ap_count"], 1)
        self.assertTrue(projected["partial"])

    def test_bounded_ap_and_sample_lists_report_actual_truncation(self) -> None:
        macs = [f"{index:012x}" for index in range(MAX_AP_ROWS_PER_KIND + 2)]
        mapping = {mac: f"{index:024x}" for index, mac in enumerate(macs)}
        rows = [{"apMac": mac_colons(mac), "retries": []} for mac in macs]
        projected = project_ap_retry_drop({"retryEaps": rows, "droppedEaps": []}, 0, 10, mapping)
        self.assertEqual(projected["retry_ap_count"], MAX_AP_ROWS_PER_KIND + 2)
        self.assertEqual(len(projected["retry_aps"]), MAX_AP_ROWS_PER_KIND)
        self.assertEqual(projected["omitted_retry_aps_limit_count"], 2)
        self.assertTrue(projected["partial"])

        samples = [{"time": 1, "retryTimes": 3, "retryRate": 0.5}]
        samples *= MAX_SAMPLES_PER_AP + 4
        projected = project_ap_retry_drop(
            {"retryEaps": [{"apMac": mac_colons(macs[0]), "retries": samples}],
             "droppedEaps": []}, 0, 10, {macs[0]: mapping[macs[0]]})
        self.assertEqual(projected["retry_aps"][0]["sample_count"], MAX_SAMPLES_PER_AP + 4)
        self.assertEqual(len(projected["retry_aps"][0]["samples"]), MAX_SAMPLES_PER_AP)
        self.assertEqual(projected["retry_aps"][0]["omitted_sample_count"], 4)
        self.assertTrue(projected["partial"])

    def test_missing_series_and_top_level_fields_mark_partial(self) -> None:
        projected = project_ap_retry_drop({"retryEaps": [{"apMac": mac_colons("001122334455")} ]},
                                          1, 10, {"001122334455": REF1})
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["missing_fields"], ["droppedEaps"])
        self.assertEqual(projected["retry_aps"][0]["missing_fields"], ["retries"])

    def test_invalid_time_mapping_shapes_status_and_numeric_values_fail_closed(self) -> None:
        valid_base = {"apMac": mac_colons("001122334455"), "retries": []}
        invalid_results = (
            {"retryEaps": None, "droppedEaps": []},
            {"retryEaps": [{**valid_base, "status": 2}], "droppedEaps": []},
            {"retryEaps": [{"apMac": valid_base["apMac"], "retries": [
                {"time": 1.0, "retryTimes": 1, "retryRate": 0.2}]}], "droppedEaps": []},
            {"retryEaps": [{"apMac": valid_base["apMac"], "retries": [
                {"time": 1, "retryTimes": True, "retryRate": 0.2}]}], "droppedEaps": []},
            {"retryEaps": [{"apMac": valid_base["apMac"], "retries": [
                {"time": 1, "retryTimes": 1, "retryRate": math.inf}]}], "droppedEaps": []},
            {"retryEaps": [{**valid_base, "avg": 10**400}], "droppedEaps": []},
        )
        for result in invalid_results:
            with self.subTest(result=str(result)[:80]), self.assertRaises(ApRetryDropProjectionError):
                project_ap_retry_drop(result, 0, 10, {"001122334455": REF1})

        for start, end in ((True, 10), (10, 1), (-1, 10), (0, 2**63)):
            with self.subTest(start=start, end=end), self.assertRaises(ApRetryDropProjectionError):
                project_ap_retry_drop({"retryEaps": [], "droppedEaps": []}, start, end, {})
        with self.assertRaises(ApRetryDropProjectionError):
            project_ap_retry_drop({"retryEaps": [], "droppedEaps": []}, 0, 1, {"AABBCCDDEEFF": REF1})


if __name__ == "__main__":
    unittest.main()
