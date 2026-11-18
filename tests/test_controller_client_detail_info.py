import unittest

from app.controller_client_detail_info import (project_controller_client_detail_info,
                                               project_msp_client_detail_info)


class ControllerClientDetailInfoTests(unittest.TestCase):
    def test_projects_only_documented_flags(self):
        result = project_controller_client_detail_info({
            "clientRecognitionEnable": True, "clientHealthEnable": False,
            "clientHistoryEnable": True, "clientDataTrendEnable": False,
            "followMsp": True,
        })
        self.assertEqual(result["data"]["settings"], {
            "client_recognition_enable": True,
            "client_health_enable": False,
            "client_history_enable": True,
            "client_data_trend_enable": False,
            "follow_msp": True,
        })
        self.assertFalse(result["partial"])

    def test_invalid_unknown_and_missing_values_mark_partial(self):
        result = project_controller_client_detail_info(
            {"clientRecognitionEnable": 1, "private": "secret"})
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertEqual(result["data"]["missing_count"], 4)
        self.assertNotIn("secret", str(result))
        self.assertTrue(result["partial"])


class MspClientDetailInfoTests(unittest.TestCase):
    def test_projects_only_documented_msp_flags(self):
        result = project_msp_client_detail_info({
            "clientHealthEnable": True, "clientHistoryEnable": False,
            "clientDataTrendEnable": True, "clientRecognitionEnable": True,
        })
        self.assertEqual(result["data"]["settings"], {
            "client_health_enable": True, "client_history_enable": False,
            "client_data_trend_enable": True,
        })
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_bad_result_and_non_boolean_values_are_bounded(self):
        result = project_msp_client_detail_info({"clientHealthEnable": 1})
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertNotIn("secret", str(result))
        with self.assertRaises(ValueError):
            project_msp_client_detail_info([])


if __name__ == "__main__":
    unittest.main()
