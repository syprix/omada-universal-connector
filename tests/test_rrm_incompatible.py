from __future__ import annotations

import json
import unittest

from app.rrm_incompatible import (
    MAX_ENTRIES,
    RrmIncompatibleProjectionError,
    project_rrm_incompatible_rows,
)


REF_A = "a" * 24
REF_B = "b" * 24
MAC_A = "00:11:22:33:44:55"
MAC_B = "AA-BB-CC-DD-EE-FF"


class RrmIncompatibleProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seen: list[str] = []
        self.mapping = {"001122334455": REF_A, "aabbccddeeff": REF_B}

        def resolve(normalized_mac: str) -> str | None:
            self.seen.append(normalized_mac)
            return self.mapping.get(normalized_mac)

        self.resolve = resolve

    @staticmethod
    def row(mac: str = MAC_A, **fields: object) -> dict[str, object]:
        return {"mac": mac, "name": "Private AP label", "statusCategory": 1,
                "status": -7, "version": "secret-fw", "type": "EAP",
                "model": "private-model", "modelVersion": "3.0",
                "showModel": "Private model label", **fields}

    def test_projects_only_opaque_ref_and_documented_status_scalars(self) -> None:
        result = project_rrm_incompatible_rows(
            [self.row(), self.row(MAC_B, statusCategory=4, status=2**31 - 1)], self.resolve)
        self.assertEqual(result, {
            "status": "ok", "resource": "rrm_incompatible_aps", "count": 2,
            "items": [
                {"device_ref": REF_A, "status_category": 1, "status_code": -7,
                 "partial": False},
                {"device_ref": REF_B, "status_category": 4, "status_code": 2**31 - 1,
                 "partial": False},
            ],
            "unknown_entry_count": 0, "unknown_field_count": 0, "partial": False,
        })
        self.assertEqual(self.seen, ["001122334455", "aabbccddeeff"])
        serialized = json.dumps(result)
        for value in (MAC_A, MAC_B, "Private AP label", "secret-fw", "private-model",
                      "Private model label"):
            self.assertNotIn(value, serialized)

    def test_unknown_detailed_status_is_not_interpreted(self) -> None:
        result = project_rrm_incompatible_rows(
            [self.row(status=9_999_999)], self.resolve)
        self.assertEqual(result["items"], [{
            "device_ref": REF_A, "status_category": 1,
            "status_code": 9_999_999, "partial": False,
        }])

    def test_missing_and_invalid_status_fields_become_partial_unknowns(self) -> None:
        rows = [
            {"mac": MAC_A},
            self.row(statusCategory=5),
            self.row(statusCategory=True),
            self.row(status=2**31),
            self.row(status=False),
        ]
        result = project_rrm_incompatible_rows(rows, self.resolve)
        self.assertEqual(result["count"], 5)
        self.assertTrue(result["partial"])
        self.assertTrue(all(row["partial"] for row in result["items"]))
        self.assertEqual(result["items"][0]["status_category"], None)
        self.assertEqual(result["items"][0]["status_code"], None)
        self.assertEqual(result["items"][1]["status_category"], None)
        self.assertEqual(result["items"][2]["status_category"], None)
        self.assertEqual(result["items"][3]["status_code"], None)
        self.assertEqual(result["items"][4]["status_code"], None)

    def test_uninventoried_or_malformed_macs_are_unknown_and_never_emitted(self) -> None:
        raw_unknown = "22:33:44:55:66:77"
        result = project_rrm_incompatible_rows([
            self.row(raw_unknown), self.row("not-a-mac"), {"status": 2},
        ], self.resolve)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["unknown_entry_count"], 3)
        self.assertTrue(result["partial"])
        serialized = json.dumps(result)
        self.assertNotIn(raw_unknown, serialized)
        self.assertNotIn("not-a-mac", serialized)
        self.assertEqual(self.seen, ["223344556677"])

    def test_unknown_fields_are_counted_without_returning_their_names_or_values(self) -> None:
        result = project_rrm_incompatible_rows(
            [self.row(privateSecret="do-not-copy")], self.resolve)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        serialized = json.dumps(result)
        self.assertNotIn("privateSecret", serialized)
        self.assertNotIn("do-not-copy", serialized)

    def test_bad_resolver_output_or_exception_cannot_create_identity(self) -> None:
        result = project_rrm_incompatible_rows(
            [self.row()], lambda _: MAC_A)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["unknown_entry_count"], 1)

        def broken(_: str) -> str:
            raise RuntimeError("raw identity should not escape")

        result = project_rrm_incompatible_rows([self.row()], broken)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["unknown_entry_count"], 1)
        self.assertNotIn("raw identity", json.dumps(result))

    def test_invalid_page_inputs_and_oversized_rows_fail_closed(self) -> None:
        for rows, resolver, maximum in (
            ({}, self.resolve, MAX_ENTRIES),
            ([], None, MAX_ENTRIES),
            ([], self.resolve, 0),
            ([], self.resolve, MAX_ENTRIES + 1),
            ([self.row()] * (MAX_ENTRIES + 1), self.resolve, MAX_ENTRIES),
        ):
            with self.subTest(rows=type(rows).__name__, maximum=maximum), self.assertRaises(
                    RrmIncompatibleProjectionError):
                project_rrm_incompatible_rows(rows, resolver, max_entries=maximum)

        oversized_row = self.row()
        oversized_row.update({f"x{i}": i for i in range(40)})
        result = project_rrm_incompatible_rows([oversized_row], self.resolve)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["unknown_entry_count"], 1)
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
