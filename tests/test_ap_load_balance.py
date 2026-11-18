from __future__ import annotations

import unittest

from app.ap_load_balance import ApLoadBalanceError, project_ap_load_balance


BANDS = ("2g", "5g", "5g2", "6g")


def complete_result() -> dict[str, bool | int]:
    result: dict[str, bool | int] = {}
    for band in BANDS:
        result[f"maxClientsEnable{band}"] = True
        result[f"maxClients{band}"] = 1
        result[f"rssiEnable{band}"] = False
        result[f"threshold{band}"] = -95
    return result


class ApLoadBalanceProjectionTests(unittest.TestCase):
    def test_projects_all_documented_band_fields_without_aliases(self) -> None:
        raw = complete_result()
        result = project_ap_load_balance(raw)
        self.assertEqual(result, {
            "status": "ok", "resource": "ap_load_balance", "data": raw,
            "partial": False, "missing_fields": [], "invalid_fields": [],
            "unknown_field_count": 0,
        })
        self.assertNotIn("maxClients5g1", result["data"])
        self.assertNotIn("threshold5g1", result["data"])

    def test_accepts_documented_inclusive_range_edges(self) -> None:
        raw = complete_result()
        raw.update({"maxClients5g": 512, "threshold2g": 0, "threshold6g": -95})
        result = project_ap_load_balance(raw)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["maxClients5g"], 512)
        self.assertEqual(result["data"]["threshold2g"], 0)
        self.assertEqual(result["data"]["threshold6g"], -95)

    def test_missing_fields_are_partial_without_defaults(self) -> None:
        raw = complete_result()
        del raw["rssiEnable5g2"]
        del raw["maxClientsEnable6g"]
        result = project_ap_load_balance(raw)
        self.assertNotIn("rssiEnable5g2", result["data"])
        self.assertNotIn("maxClientsEnable6g", result["data"])
        self.assertEqual(result["missing_fields"], ["rssiEnable5g2", "maxClientsEnable6g"])
        self.assertTrue(result["partial"])

    def test_invalid_types_and_ranges_are_omitted(self) -> None:
        cases = (
            ("maxClientsEnable2g", 1),
            ("rssiEnable5g", 0),
            ("maxClients2g", 0),
            ("maxClients6g", 513),
            ("threshold5g2", -96),
            ("threshold6g", 1),
            ("maxClients5g", True),
            ("threshold2g", -2**31),
        )
        for field, invalid_value in cases:
            with self.subTest(field=field, invalid_value=invalid_value):
                raw = complete_result()
                raw[field] = invalid_value
                result = project_ap_load_balance(raw)
                self.assertNotIn(field, result["data"])
                self.assertEqual(result["invalid_fields"], [field])
                self.assertTrue(result["partial"])

    def test_unknown_fields_are_counted_without_disclosing_names_or_values(self) -> None:
        raw = complete_result()
        raw["privateApName"] = "secret-lobby-ap"
        raw["ssid"] = "private-network"
        result = project_ap_load_balance(raw)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertTrue(result["partial"])
        rendered = repr(result)
        for secret in ("privateApName", "secret-lobby-ap", "ssid", "private-network"):
            self.assertNotIn(secret, rendered)

    def test_does_not_invent_5g1_or_transform_values(self) -> None:
        raw = complete_result()
        raw.update({"maxClients5g": 39, "maxClients5g2": 41})
        result = project_ap_load_balance(raw)
        self.assertEqual(result["data"]["maxClients5g"], 39)
        self.assertEqual(result["data"]["maxClients5g2"], 41)
        self.assertFalse(result["partial"])

    def test_rejects_unbounded_or_malformed_roots(self) -> None:
        for raw in (None, [], "not-an-object", {f"key-{i}": i for i in range(33)},
                    {"x" * 129: 1}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApLoadBalanceError):
                project_ap_load_balance(raw)


if __name__ == "__main__":
    unittest.main()
