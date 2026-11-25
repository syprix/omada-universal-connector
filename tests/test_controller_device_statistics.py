import unittest

from app.controller_device_statistics import (
    FIELD_MAP, ControllerDeviceStatisticsError, project_controller_device_statistics,
)


class ControllerDeviceStatisticsTests(unittest.TestCase):
    def test_maps_each_documented_integer_field_individually(self):
        for index, (source, target) in enumerate(FIELD_MAP.items()):
            with self.subTest(source=source):
                result = project_controller_device_statistics({source: index})
                self.assertEqual(result["data"]["counts"], {target: index})
                self.assertEqual(result["data"]["present_count"], 1)
                self.assertEqual(result["data"]["missing_count"], len(FIELD_MAP) - 1)
                self.assertTrue(result["partial"])

    def test_complete_scalar_and_documented_health_projection(self):
        raw = {source: index for index, source in enumerate(FIELD_MAP)}
        raw.update({source: {"good": 1, "fair": 2, "poor": 3, "noData": 4}
                    for source in ("switchHealth", "eapHealth", "gatewayHealth")})
        result = project_controller_device_statistics(raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["counts"], {
            target: index for index, target in enumerate(FIELD_MAP.values())})
        self.assertEqual(result["data"]["health_counts"], {
            "switches": {"good": 1, "fair": 2, "poor": 3, "noData": 4},
            "access_points": {"good": 1, "fair": 2, "poor": 3, "noData": 4},
            "gateways": {"good": 1, "fair": 2, "poor": 3, "noData": 4},
        })
        self.assertEqual(result["data"]["omitted_variant_field_count"], 0)

    def test_partial_or_malformed_health_objects_remain_redacted_and_partial(self):
        partial = project_controller_device_statistics({"switchHealth": {"good": 3}})
        self.assertEqual(partial["data"]["health_counts"], {"switches": {"good": 3}})
        self.assertEqual(partial["data"]["health_missing_count"], 3)
        self.assertTrue(partial["partial"])
        malformed = project_controller_device_statistics({
            "eapHealth": {"good": True, "fair": -1, "poor": "sensitive-label-value", "noData": 1,
                          "private": "sensitive-label-value"},
            "gatewayHealth": None,
        })
        self.assertEqual(malformed["data"]["health_counts"], {"access_points": {"noData": 1}})
        self.assertEqual(malformed["data"]["health_invalid_count"], 3)
        self.assertEqual(malformed["data"]["unknown_field_count"], 1)
        self.assertEqual(malformed["data"]["omitted_variant_field_count"], 1)
        self.assertTrue(malformed["partial"])
        for private in ("private", "sensitive-label-value", "switchHealth", "eapHealth", "gatewayHealth"):
            self.assertNotIn(private, str(malformed))

    def test_invalid_and_unknown_values_are_counted_without_echoing(self):
        for value in (True, -1, 2_147_483_648, "1", None):
            with self.subTest(value=value):
                result = project_controller_device_statistics({"allDevices": value})
                self.assertEqual(result["data"]["invalid_count"], 1)
                self.assertTrue(result["partial"])
        unknown = project_controller_device_statistics({"secret": "omit"})
        self.assertEqual(unknown["data"]["unknown_field_count"], 1)
        self.assertNotIn("secret", str(unknown))

    def test_rejects_non_object_and_oversized_inputs(self):
        for value in (None, [], "bad", {str(i): i for i in range(33)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(ControllerDeviceStatisticsError):
                project_controller_device_statistics(value)


if __name__ == "__main__":
    unittest.main()
