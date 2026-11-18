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

    def test_complete_scalar_projection_and_variant_object_counts(self):
        raw = {source: index for index, source in enumerate(FIELD_MAP)}
        result = project_controller_device_statistics(raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["counts"], {
            target: index for index, target in enumerate(FIELD_MAP.values())})
        with_variants = project_controller_device_statistics({
            **raw, "switchHealth": {"good": 1}, "eapHealth": {}, "gatewayHealth": None})
        self.assertEqual(with_variants["data"]["omitted_variant_field_count"], 3)
        self.assertTrue(with_variants["partial"])
        self.assertNotIn("switchHealth", str(with_variants))

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
