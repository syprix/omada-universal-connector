from __future__ import annotations

import copy
import unittest

from app.wifi_subhealth import WifiSubhealthError, project_wifi_subhealth


START = 1_710_000_000_000
END = START + 86_400_000
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


def score_detail() -> dict[str, object]:
    return {
        "summaryScore": 42,
        "support": True,
        "scores": [{"time": START, "score": -7}, {"time": END, "score": 13}],
    }


def channel_detail(*, with_averages: bool = True) -> dict[str, object]:
    detail: dict[str, object] = score_detail()
    if with_averages:
        detail.update({
            "averageInterf2g": -91,
            "averageInterf5g": -88,
            "averageInterf6g": -86,
            "averageNoiseFloor": -101,
        })
    return detail


def quality_detail() -> dict[str, object]:
    detail: dict[str, object] = {"summaryScore": 50, "support": True}
    for index, name in enumerate(("assocTime", "authTime", "dhcpTime", "dnsTime")):
        detail[name] = [{"time": START + index, "pastNum": index - 5}]
    detail.update({
        "averageAssocTime": 1,
        "averageAuthTime": 2,
        "averageDhcpTime": 3,
        "averageDnsTime": 4,
    })
    return detail


def full_result(*, include_quality: bool = True) -> dict[str, object]:
    result: dict[str, object] = {
        "wifiHealthScore": 73,
        "accessTimeScoreDetail": score_detail(),
        "channelUtilScoreDetail": score_detail(),
        "accessCapacityScoreDetail": score_detail(),
        "rssiScoreDetail": score_detail(),
        "channelInterUtilDetail": channel_detail(),
    }
    if include_quality:
        result["wirelessClientQualityDetail"] = quality_detail()
    return result


class WifiSubhealthProjectionTests(unittest.TestCase):
    def project(self, raw: object, start: int = START, end: int = END):
        return project_wifi_subhealth(raw, start, end)

    def test_projects_all_six_allowlisted_details_without_scale_mapping(self) -> None:
        raw = full_result()
        result = self.project(raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["resource"], "wifi_subhealth")
        self.assertEqual(result["window"], {"start_ms": START, "end_ms": END})
        self.assertEqual(set(result["data"]), {
            "wifiHealthScore",
            "accessTimeScoreDetail", "channelUtilScoreDetail", "accessCapacityScoreDetail",
            "rssiScoreDetail", "channelInterUtilDetail", "wirelessClientQualityDetail",
        })
        self.assertEqual(result["data"]["accessTimeScoreDetail"]["scores"], [
            {"time_ms": START, "score": -7}, {"time_ms": END, "score": 13},
        ])
        self.assertEqual(result["data"]["channelInterUtilDetail"]["averageNoiseFloor"], -101)
        self.assertEqual(result["data"]["wirelessClientQualityDetail"]["assocTime"], [
            {"time_ms": START, "pastNum": -5},
        ])
        self.assertEqual(result["data"]["wirelessClientQualityDetail"]["averageDnsTime"], 4)

    def test_er_style_missing_client_quality_and_channel_averages_are_partial(self) -> None:
        raw = full_result(include_quality=False)
        raw["channelInterUtilDetail"] = channel_detail(with_averages=False)
        result = self.project(raw)
        self.assertNotIn("wirelessClientQualityDetail", result["data"])
        self.assertIn("wirelessClientQualityDetail", result["missing_fields"])
        for field in ("averageInterf2g", "averageInterf5g", "averageInterf6g", "averageNoiseFloor"):
            self.assertIn(f"channelInterUtilDetail.{field}", result["missing_fields"])
            self.assertNotIn(field, result["data"]["channelInterUtilDetail"])
        self.assertTrue(result["partial"])

    def test_incidents_are_fully_discarded_and_not_unknown(self) -> None:
        raw = full_result()
        incident = {"id": "private-id", "mac": "AA:BB:CC:DD:EE:FF", "content": "secret free text"}
        for name in ("accessTimeScoreDetail", "channelUtilScoreDetail",
                     "accessCapacityScoreDetail", "rssiScoreDetail",
                     "channelInterUtilDetail", "wirelessClientQualityDetail"):
            raw[name]["incidents"] = [incident]
        result = self.project(raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["unknown_field_count"], 0)
        rendered = repr(result)
        for secret in ("incidents", "private-id", "AA:BB:CC:DD:EE:FF", "secret free text"):
            self.assertNotIn(secret, rendered)

    def test_invalid_and_missing_values_mark_partial_and_bool_is_not_integer(self) -> None:
        raw = full_result()
        raw["wifiHealthScore"] = True
        raw["accessTimeScoreDetail"]["support"] = 1
        raw["accessTimeScoreDetail"]["scores"] = [
            {"time": START, "score": False},
            {"time": START + 1},
            {"score": 2},
        ]
        raw["channelInterUtilDetail"]["averageInterf2g"] = "-90"
        result = self.project(raw)
        self.assertIn("wifiHealthScore", result["invalid_fields"])
        self.assertIn("accessTimeScoreDetail.support", result["invalid_fields"])
        self.assertIn("accessTimeScoreDetail.scores[].score", result["invalid_fields"])
        self.assertIn("accessTimeScoreDetail.scores[].score", result["missing_fields"])
        self.assertIn("accessTimeScoreDetail.scores[].time", result["missing_fields"])
        self.assertIn("channelInterUtilDetail.averageInterf2g", result["invalid_fields"])
        self.assertTrue(result["partial"])
        self.assertNotIn("wifiHealthScore", result["data"])
        self.assertNotIn("averageInterf2g", result["data"]["channelInterUtilDetail"])

    def test_time_window_and_int32_bounds_are_enforced_without_rescaling(self) -> None:
        raw = full_result()
        raw["rssiScoreDetail"]["scores"] = [
            {"time": START - 1, "score": 1},
            {"time": END + 1, "score": 2},
            {"time": START + 2, "score": INT32_MIN},
            {"time": START + 3, "score": INT32_MAX},
        ]
        raw["channelInterUtilDetail"]["averageNoiseFloor"] = INT32_MIN
        result = self.project(raw)
        self.assertEqual(result["data"]["rssiScoreDetail"]["scores"], [
            {"time_ms": START + 2, "score": INT32_MIN},
            {"time_ms": START + 3, "score": INT32_MAX},
        ])
        self.assertEqual(result["data"]["channelInterUtilDetail"]["averageNoiseFloor"], INT32_MIN)
        self.assertIn("rssiScoreDetail.scores[].time", result["invalid_fields"])
        self.assertTrue(result["partial"])
        for bad in ((True, END), (START, END + 1), (END, START)):
            with self.subTest(window=bad), self.assertRaises(WifiSubhealthError):
                self.project(full_result(), *bad)

    def test_unknown_fields_are_counted_but_private_values_are_redacted(self) -> None:
        raw = full_result()
        raw["privateTop"] = "top-secret"
        raw["rssiScoreDetail"]["privateDetail"] = "detail-secret"
        raw["channelUtilScoreDetail"]["scores"][0]["privatePoint"] = "point-secret"
        result = self.project(raw)
        self.assertEqual(result["unknown_field_count"], 3)
        self.assertTrue(result["partial"])
        rendered = repr(result)
        for secret in ("privateTop", "top-secret", "privateDetail", "detail-secret",
                       "privatePoint", "point-secret"):
            self.assertNotIn(secret, rendered)

    def test_bounds_root_details_points_and_total_point_count(self) -> None:
        for raw in (None, [], "raw", {f"extra{i}": i for i in range(17)}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(WifiSubhealthError):
                self.project(raw)

        raw = full_result()
        raw["accessTimeScoreDetail"]["scores"] = [{"time": START, "score": 1}] * 513
        with self.assertRaises(WifiSubhealthError):
            self.project(raw)

        raw = full_result()
        for name in ("accessTimeScoreDetail", "channelUtilScoreDetail",
                     "accessCapacityScoreDetail", "rssiScoreDetail"):
            raw[name]["scores"] = [{"time": START, "score": 1}] * 512
        with self.assertRaises(WifiSubhealthError):
            self.project(raw)

        raw = full_result()
        raw["accessTimeScoreDetail"].update({f"extra{i}": i for i in range(31)})
        with self.assertRaises(WifiSubhealthError):
            self.project(raw)

    def test_source_is_not_mutated_and_unknown_scale_is_not_added(self) -> None:
        raw = full_result()
        original = copy.deepcopy(raw)
        result = self.project(raw)
        self.assertEqual(raw, original)
        serialized = repr(result)
        for invented in ("percentage", "threshold", "quality_label", "score_scale"):
            self.assertNotIn(invented, serialized)


if __name__ == "__main__":
    unittest.main()
