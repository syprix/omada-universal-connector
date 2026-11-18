from __future__ import annotations

import copy
import unittest

from app.client_signal_distribution import (
    ClientSignalDistributionError,
    project_client_signal_distribution,
)


CATEGORIES = ("poorSignal", "weakSignal", "averageSignal", "stableSignal", "strongSignal")
FIELDS = ("totalClients", "clientsPercent", "clients2g", "clients5g", "clients6g")
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


def full_result() -> dict[str, dict[str, int]]:
    return {
        category: {field: index for index, field in enumerate(FIELDS)}
        for category in CATEGORIES
    }


class ClientSignalDistributionTests(unittest.TestCase):
    def test_projects_all_documented_categories_and_integer_metrics(self) -> None:
        raw = full_result()
        result = project_client_signal_distribution(raw)
        self.assertEqual(result, {
            "status": "ok", "resource": "client_signal_distribution",
            "data": raw, "partial": False, "missing_fields": [],
            "invalid_fields": [], "unknown_field_count": 0,
            "omitted_field_count": 0,
        })

    def test_preserves_raw_clients_percent_without_assumed_scale(self) -> None:
        raw = full_result()
        raw["poorSignal"]["clientsPercent"] = INT32_MAX
        raw["strongSignal"]["clientsPercent"] = INT32_MIN
        result = project_client_signal_distribution(raw)
        self.assertEqual(result["data"]["poorSignal"]["clientsPercent"], INT32_MAX)
        self.assertEqual(result["data"]["strongSignal"]["clientsPercent"], INT32_MIN)
        self.assertFalse(result["partial"])

    def test_missing_categories_or_metrics_are_partial_and_not_defaulted(self) -> None:
        raw = full_result()
        del raw["weakSignal"]
        del raw["poorSignal"]["clients6g"]
        result = project_client_signal_distribution(raw)
        self.assertNotIn("weakSignal", result["data"])
        self.assertNotIn("clients6g", result["data"]["poorSignal"])
        self.assertIn("weakSignal", result["missing_fields"])
        self.assertIn("poorSignal.clients6g", result["missing_fields"])
        self.assertTrue(result["partial"])

    def test_invalid_values_include_bool_float_and_out_of_int32(self) -> None:
        raw = full_result()
        raw["poorSignal"]["totalClients"] = True
        raw["weakSignal"]["clientsPercent"] = 1.5
        raw["averageSignal"]["clients2g"] = INT32_MAX + 1
        raw["stableSignal"]["clients5g"] = INT32_MIN - 1
        result = project_client_signal_distribution(raw)
        self.assertNotIn("totalClients", result["data"]["poorSignal"])
        self.assertNotIn("clientsPercent", result["data"]["weakSignal"])
        self.assertNotIn("clients2g", result["data"]["averageSignal"])
        self.assertNotIn("clients5g", result["data"]["stableSignal"])
        self.assertEqual(len(result["invalid_fields"]), 4)
        self.assertTrue(result["partial"])

    def test_unknown_fields_are_counted_without_exposing_names_or_values(self) -> None:
        raw = full_result()
        raw["poorSignal"]["privateDeviceName"] = "secret-ap-name"
        raw["privateCategory"] = {"ip": "192.0.2.77"}
        result = project_client_signal_distribution(raw)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertEqual(result["omitted_field_count"], 2)
        rendered = repr(result)
        for private in ("privateDeviceName", "secret-ap-name", "privateCategory", "192.0.2.77"):
            self.assertNotIn(private, rendered)
        self.assertTrue(result["partial"])

    def test_non_object_categories_are_partial_without_raw_value(self) -> None:
        raw = full_result()
        raw["poorSignal"] = "private raw payload"
        result = project_client_signal_distribution(raw)
        self.assertIn("poorSignal", result["invalid_fields"])
        self.assertNotIn("poorSignal", result["data"])
        self.assertNotIn("private raw payload", repr(result))
        self.assertTrue(result["partial"])

    def test_rejects_unbounded_top_level_and_nested_objects(self) -> None:
        for raw in (None, [], "not-an-object", {f"unknown-{i}": 0 for i in range(17)}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ClientSignalDistributionError):
                project_client_signal_distribution(raw)
        raw = full_result()
        raw["poorSignal"].update({f"extra-{i}": i for i in range(12)})
        with self.assertRaises(ClientSignalDistributionError):
            project_client_signal_distribution(raw)

    def test_unknown_nested_objects_do_not_mutate_source_or_projection(self) -> None:
        raw = full_result()
        original = copy.deepcopy(raw)
        raw["stableSignal"]["extra"] = {"nested": "secret"}
        original["stableSignal"]["extra"] = {"nested": "secret"}
        result = project_client_signal_distribution(raw)
        self.assertEqual(raw, original)
        self.assertNotIn("extra", result["data"]["stableSignal"])
        self.assertNotIn("secret", repr(result))
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
