from __future__ import annotations

import unittest

from app.ap_ofdma import ApOfdmaError, can_write_ofdma_band, project_ap_ofdma


FIELDS = (
    "ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g",
    "supportOfdma2g", "supportOfdma5g", "supportOfdma5g2", "supportOfdma6g",
)


class ApOfdmaTests(unittest.TestCase):
    @staticmethod
    def complete(**updates):
        value = {field: True for field in FIELDS}
        value.update(updates)
        return value

    def test_projects_only_eight_documented_boolean_fields(self) -> None:
        source = self.complete(
            ofdmaEnable2g=False, supportOfdma6g=False,
            name="private-ap-name", mac="AA-BB-CC-DD-EE-FF", ip="192.0.2.8",
            firmware="private-firmware", model="private-model")
        result = project_ap_ofdma(source)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["resource"], "ap_ofdma")
        self.assertEqual(set(result["data"]), set(FIELDS))
        self.assertFalse(result["data"]["ofdmaEnable2g"])
        self.assertFalse(result["data"]["supportOfdma6g"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["invalid_fields"], [])
        self.assertEqual(result["unknown_field_count"], 5)
        for private in ("private-ap-name", "AA-BB-CC-DD-EE-FF", "192.0.2.8",
                        "private-firmware", "private-model", "firmware", "name", "mac"):
            self.assertNotIn(private, str(result))
        for inferred in ("hardware_support", "firmware_support", "unsupported_reason"):
            self.assertNotIn(inferred, result)

    def test_missing_boolean_fields_are_partial_and_safe_write_is_blocked(self) -> None:
        result = project_ap_ofdma({"ofdmaEnable5g": True, "supportOfdma5g": True})
        self.assertEqual(set(result["data"]), {"ofdmaEnable5g", "supportOfdma5g"})
        self.assertEqual(result["missing_fields"], [
            "ofdmaEnable2g", "ofdmaEnable5g2", "ofdmaEnable6g",
            "supportOfdma2g", "supportOfdma5g2", "supportOfdma6g",
        ])
        self.assertTrue(result["partial"])
        self.assertFalse(can_write_ofdma_band(result, "5g"))

    def test_invalid_values_are_omitted_not_coerced_and_mark_partial(self) -> None:
        source = self.complete(
            ofdmaEnable2g=1,
            supportOfdma5g=None,
            ofdmaEnable6g="true")
        result = project_ap_ofdma(source)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_fields"], [
            "ofdmaEnable2g", "ofdmaEnable6g", "supportOfdma5g",
        ])
        self.assertNotIn("ofdmaEnable2g", result["data"])
        self.assertNotIn("supportOfdma5g", result["data"])
        self.assertNotIn("ofdmaEnable6g", result["data"])
        self.assertFalse(can_write_ofdma_band(result, "2g"))

    def test_unknown_fields_make_partial_and_are_not_copied(self) -> None:
        result = project_ap_ofdma(self.complete(
            privateAttribute="must-not-appear", nested={"secret": "must-not-appear"}))
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertNotIn("privateAttribute", str(result))
        self.assertNotIn("nested", str(result))
        self.assertNotIn("must-not-appear", str(result))
        self.assertFalse(can_write_ofdma_band(result, "2g"))

    def test_full_state_only_allows_write_when_requested_band_is_supported(self) -> None:
        result = project_ap_ofdma(self.complete(
            supportOfdma2g=True, supportOfdma5g=False,
            supportOfdma5g2=True, supportOfdma6g=False))
        self.assertFalse(result["partial"])
        self.assertTrue(can_write_ofdma_band(result, "2g"))
        self.assertFalse(can_write_ofdma_band(result, "5g"))
        self.assertTrue(can_write_ofdma_band(result, "5g2"))
        self.assertFalse(can_write_ofdma_band(result, "6g"))
        for invalid_band in ("5G", "wifi", "", None):
            self.assertFalse(can_write_ofdma_band(result, invalid_band))

    def test_malformed_or_oversized_results_fail_closed(self) -> None:
        for raw in (None, [], "private", 42):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(ApOfdmaError):
                project_ap_ofdma(raw)
        too_many = self.complete(**{f"unknown_{index}": True for index in range(25)})
        with self.assertRaises(ApOfdmaError):
            project_ap_ofdma(too_many)
        too_long_key = self.complete(**{"x" * 129: True})
        with self.assertRaises(ApOfdmaError):
            project_ap_ofdma(too_long_key)

    def test_write_gate_revalidates_projection_shape_instead_of_trusting_it(self) -> None:
        result = project_ap_ofdma(self.complete())
        self.assertTrue(can_write_ofdma_band(result, "2g"))
        malformed = dict(result, partial=True)
        self.assertFalse(can_write_ofdma_band(malformed, "2g"))
        altered = dict(result, data=dict(result["data"], supportOfdma2g=1))
        self.assertFalse(can_write_ofdma_band(altered, "2g"))
        missing_field = dict(result, data={k: v for k, v in result["data"].items()
                                           if k != "supportOfdma2g"})
        self.assertFalse(can_write_ofdma_band(missing_field, "2g"))


if __name__ == "__main__":
    unittest.main()
