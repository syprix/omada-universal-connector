from __future__ import annotations

import unittest

from app.rf_planning_detail import RfPlanningDetailError, project_rf_planning_detail


def radio():
    return {"origChan": "36", "rcmdChan": "44", "origChanWidth": "80",
            "rcmdChanWidth": "40", "origPower": 18, "rcmdPower": 15,
            "origBand": 1, "rcmdBand": 1, "errCode": 0}


def fixture():
    return {
        "channelDeployEnable": True, "channelWidthDeployEnable": True,
        "bandDeployEnable": False, "powerAdjustEnable": True,
        "time": 1_800_000_000_000, "currentConfig": 1,
        "successDevices": 2, "failDevices": 0,
        "data": [{"name": "private-ap", "ip": "192.0.2.9",
                  "optimizeSuccess": True, "support5g2": False,
                  "radio2g": radio(), "radio5g": radio(),
                  "radio5g2": radio(), "radio6g": radio(),
                  "failMsg": "private diagnostic text", "failMsgType": -1,
                  "triggerReason": 1}],
    }


class RfPlanningDetailTests(unittest.TestCase):
    def test_projects_existing_radio_recommendations_and_redacts_identity(self) -> None:
        result = project_rf_planning_detail(fixture())
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["time_ms"], 1_800_000_000_000)
        self.assertEqual(result["data"]["aps"][0]["radio5g"]["rcmd_chan"], "44")
        for secret in ("private-ap", "192.0.2.9", "private diagnostic text"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_values_and_unexpected_fields_mark_partial(self) -> None:
        raw = fixture()
        raw["data"][0]["radio5g"]["rcmdPower"] = True
        raw["data"][0]["unexpected"] = "secret"
        result = project_rf_planning_detail(raw)
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["omitted_field_count"], 2)
        self.assertNotIn("secret", repr(result))

    def test_bounds_fail_closed(self) -> None:
        raw = fixture()
        raw["data"] = [{}] * 129
        with self.assertRaises(RfPlanningDetailError):
            project_rf_planning_detail(raw)
        with self.assertRaises(RfPlanningDetailError):
            project_rf_planning_detail({f"extra{i}": i for i in range(25)})


if __name__ == "__main__":
    unittest.main()
