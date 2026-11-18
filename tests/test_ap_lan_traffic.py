from __future__ import annotations

import unittest

from app.ap_lan_traffic import ApLanTrafficError, project_ap_lan_traffic


FIELDS = (
    "rxPkts", "txPkts", "rx", "tx", "rxDropPkts", "txDropPkts",
    "rxErrPkts", "txErrPkts",
)


class ApLanTrafficProjectionTests(unittest.TestCase):
    def test_projects_all_documented_int64_counters_without_added_semantics(self) -> None:
        raw = {field: index for index, field in enumerate(FIELDS)}
        result = project_ap_lan_traffic(raw)
        self.assertEqual(result, {
            "status": "ok", "resource": "ap_lan_traffic", "data": raw,
            "partial": False, "missing_fields": [], "invalid_fields": [],
            "unknown_field_count": 0,
        })
        for inferred in ("rx_rate", "tx_rate", "interval_ms", "counter_reset", "health"):
            self.assertNotIn(inferred, result)

    def test_missing_lan_traffic_object_and_fields_are_partial_without_defaults(self) -> None:
        absent = project_ap_lan_traffic(None)
        self.assertTrue(absent["partial"])
        self.assertEqual(absent["data"], {})
        self.assertEqual(absent["missing_fields"], list(FIELDS))

        empty = project_ap_lan_traffic({})
        self.assertTrue(empty["partial"])
        self.assertEqual(empty["data"], {})
        self.assertEqual(empty["missing_fields"], list(FIELDS))

    def test_invalid_bool_negative_float_and_out_of_int64_values_are_omitted(self) -> None:
        result = project_ap_lan_traffic({
            "rxPkts": True, "txPkts": -1, "rx": 1.25,
            "tx": 2**63, "rxDropPkts": 0,
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"], {"rxDropPkts": 0})
        self.assertEqual(set(result["invalid_fields"]), {"rxPkts", "txPkts", "rx", "tx"})
        self.assertEqual(set(result["missing_fields"]), {"txDropPkts", "rxErrPkts", "txErrPkts"})

    def test_unknown_identity_fields_are_counted_but_never_echoed(self) -> None:
        private = {
            "mac": "AA:BB:CC:DD:EE:FF", "name": "private-ap-name",
            "ip": "192.0.2.44", "ssid": "private-network",
        }
        result = project_ap_lan_traffic({**{field: 0 for field in FIELDS}, **private})
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], len(private))
        for value in private.values():
            self.assertNotIn(value, repr(result))
        for field in private:
            self.assertNotIn(field, repr(result))

    def test_valid_int64_boundaries_and_empty_zero_values(self) -> None:
        result = project_ap_lan_traffic({field: 0 for field in FIELDS})
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {field: 0 for field in FIELDS})
        result = project_ap_lan_traffic({field: 2**63 - 1 for field in FIELDS})
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {field: 2**63 - 1 for field in FIELDS})

    def test_unbounded_or_non_object_payloads_fail_closed(self) -> None:
        for raw in ([], "raw", {"x" * 129: 1}, {0: 1}, {f"unknown{i}": i for i in range(33)}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApLanTrafficError):
                project_ap_lan_traffic(raw)


if __name__ == "__main__":
    unittest.main()
