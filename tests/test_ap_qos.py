from __future__ import annotations

import unittest

from app.ap_qos import ApQosError, normalize_ap_qos_change_state, project_ap_qos


FIELDS = (
    "support2g", "support5g", "support5g2", "support6g",
    "deliveryEnable2g", "deliveryEnable5g", "deliveryEnable5g2", "deliveryEnable6g",
)


class ApQosProjectionTests(unittest.TestCase):
    def test_projects_exact_documented_booleans(self) -> None:
        raw = {field: index % 2 == 0 for index, field in enumerate(FIELDS)}
        result = project_ap_qos(raw)
        self.assertEqual(result, {
            "status": "ok", "resource": "ap_qos", "data": raw,
            "partial": False, "missing_fields": [], "invalid_fields": [],
            "unknown_field_count": 0,
        })

    def test_missing_fields_are_partial_without_invented_defaults(self) -> None:
        result = project_ap_qos({"support2g": True})
        self.assertEqual(result["data"], {"support2g": True})
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_fields"], [field for field in FIELDS if field != "support2g"])

    def test_invalid_values_are_omitted_and_marked(self) -> None:
        result = project_ap_qos({"support2g": 1, "deliveryEnable5g": None,
                                 "support6g": "true"})
        self.assertEqual(result["data"], {})
        self.assertEqual(result["invalid_fields"], ["support2g", "support6g", "deliveryEnable5g"])
        self.assertTrue(result["partial"])

    def test_unknown_fields_mark_partial_without_disclosing_name_or_value(self) -> None:
        secret_name = "privateDeviceName"
        secret_value = "internal-ap-secret"
        result = project_ap_qos({"support2g": True, secret_name: secret_value})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        rendered = repr(result)
        self.assertNotIn(secret_name, rendered)
        self.assertNotIn(secret_value, rendered)

    def test_does_not_invent_band_aliases_or_interpret_support_as_feature_state(self) -> None:
        raw = {field: True for field in FIELDS}
        result = project_ap_qos(raw)
        self.assertNotIn("support5g1", result["data"])
        self.assertNotIn("deliveryEnable5g1", result["data"])
        self.assertEqual(result["data"]["support5g2"], True)
        self.assertFalse(result["partial"])

    def test_rejects_unbounded_or_malformed_top_level_objects(self) -> None:
        for raw in (None, [], "not-an-object", {"x" * 129: True}, {7: True},
                    {f"unknown-{index}": False for index in range(33)}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApQosError):
                project_ap_qos(raw)

    def test_unknown_fields_within_bound_are_counted_but_not_copied(self) -> None:
        result = project_ap_qos({**{field: False for field in FIELDS}, "other": {"secret": "x"}})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("other", result)
        self.assertTrue(result["partial"])

    def test_change_state_requires_support_and_only_supported_band_values(self) -> None:
        state = {
            "support2g": True, "support5g": True, "support5g2": False,
            "support6g": False, "deliveryEnable2g": True,
            "deliveryEnable5g": False,
        }
        self.assertEqual(normalize_ap_qos_change_state(state), state)
        for invalid in (
            {key: value for key, value in state.items() if key != "support6g"},
            {**state, "support5g2": True},
            {**state, "support6g": True},
            {**state, "support5g": False, "support5g2": True},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ApQosError):
                normalize_ap_qos_change_state(invalid)


if __name__ == "__main__":
    unittest.main()
