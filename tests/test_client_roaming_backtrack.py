from __future__ import annotations

import unittest

from app.client_roaming_backtrack import (
    ClientRoamingBacktrackError,
    project_client_roaming_backtrack,
)


SITE = "a" * 24
CLIENT_A = "b" * 24
CLIENT_B = "c" * 24
AP_A = "d" * 24
AP_B = "e" * 24
AP_C = "f" * 24


def timeline(event_type: int, *events: tuple[int, str, str], partial: bool = False
             ) -> dict[str, object]:
    rows = []
    for event in events:
        row: dict[str, object] = {"time_ms": event[0], "event_type": event_type}
        if event_type == 2:
            row.update(previous_access_point_ref=event[1], access_point_ref=event[2])
        rows.append(row)
    return {"status": "ok", "partial": partial, "missing_fields": [],
            "omitted_fields": [], "omitted_field_count": 0,
            "data": {"sessions": [{"events": rows}]}}


def client(ref: str, roams: list[tuple[int, str, str]], *,
           disconnects: list[tuple[int, str, str]] | None = None,
           connects: list[tuple[int, str, str]] | None = None,
           disconnect_status: str = "ok") -> dict[str, object]:
    disconnect: dict[str, object] = timeline(1, *(disconnects or []))
    if disconnect_status != "ok":
        disconnect = {"status": disconnect_status}
    return {"client_ref": ref,
            "roaming": timeline(2, *roams),
            "disconnect": disconnect,
            "connect": timeline(0, *(connects or []))}


class ClientRoamingBacktrackTests(unittest.TestCase):
    def test_counts_adjacent_reciprocal_roams_by_pair_without_client_refs(self):
        result = project_client_roaming_backtrack(SITE, 100, 1_000, [
            client(CLIENT_A, [(110, AP_A, AP_B), (140, AP_B, AP_A)]),
            client(CLIENT_B, [(210, AP_A, AP_B), (250, AP_B, AP_A)]),
        ])
        self.assertEqual(result["back_and_forth_by_access_point_pair"], [{
            "access_point_pair": [AP_A, AP_B],
            "back_and_forth_sequence_count": 2,
            "affected_client_count": 2,
            "involved_roaming_event_count": 4,
        }])
        self.assertEqual(result["connection_cause"], "not_inferred")
        self.assertFalse(result["partial"])
        self.assertNotIn(CLIENT_A, repr(result))
        self.assertNotIn(CLIENT_B, repr(result))

    def test_unrelated_roam_breaks_the_consecutive_reciprocal_pattern(self):
        result = project_client_roaming_backtrack(SITE, 100, 1_000, [
            client(CLIENT_A, [(110, AP_A, AP_B), (120, AP_B, AP_C),
                              (130, AP_B, AP_A)])])
        self.assertEqual(result["back_and_forth_by_access_point_pair"], [])
        self.assertFalse(result["partial"])

    def test_full_disconnect_and_reconnect_are_separate_from_a_roam_return(self):
        result = project_client_roaming_backtrack(SITE, 100, 1_000, [
            client(CLIENT_A, [(110, AP_A, AP_B), (140, AP_B, AP_A)],
                   disconnects=[(120, "", "")], connects=[(130, "", "")]),
            client(CLIENT_B, [(210, AP_A, AP_B), (250, AP_B, AP_A)],
                   disconnects=[(220, "", "")]),
        ])
        self.assertEqual(result["back_and_forth_by_access_point_pair"], [])
        self.assertEqual(result["separated_roaming_transition_count"], 2)
        self.assertEqual(result["reconnected_after_separation_count"], 1)
        self.assertEqual(result["separation_without_observed_reconnect_count"], 1)
        self.assertFalse(result["partial"])

    def test_unavailable_connect_source_does_not_hide_a_complete_roam_return(self):
        row = client(CLIENT_A, [(110, AP_A, AP_B), (140, AP_B, AP_A)])
        row["connect"] = {"status": "error"}
        result = project_client_roaming_backtrack(SITE, 100, 1_000, [row])
        self.assertEqual(result["back_and_forth_by_access_point_pair"][0][
            "back_and_forth_sequence_count"], 1)
        self.assertEqual(result["source_coverage"][
            "unavailable_client_timeline_count"], 1)
        self.assertTrue(result["partial"])

    def test_unknown_ap_mappings_and_missing_timeline_sources_are_reported_as_gaps(self):
        unknown = client(CLIENT_A, [(110, AP_A, AP_B), (140, AP_B, AP_A)])
        unknown["roaming"] = {"status": "ok", "partial": True,
                              "missing_fields": [], "omitted_fields": [],
                              "omitted_field_count": 0,
                              "data": {"sessions": [{"events": [
                                  {"time_ms": 110, "event_type": 2,
                                   "previous_access_point_ref": AP_A,
                                   "access_point_ref": None},
                                  {"time_ms": 140, "event_type": 2,
                                   "previous_access_point_ref": None,
                                   "access_point_ref": AP_A},
                              ]}]}}
        result = project_client_roaming_backtrack(SITE, 100, 1_000, [
            unknown,
            client(CLIENT_B, [(210, AP_A, AP_B), (250, AP_B, AP_A)],
                   disconnect_status="error"),
        ], ap_inventory_available=False)
        self.assertEqual(result["source_coverage"][
            "unknown_access_point_mapping_event_count"], 2)
        self.assertEqual(result["reciprocal_sequence_event_gap_count"], 1)
        self.assertIn("unknown_access_point_mapping", result["gap_indicators"])
        self.assertIn("client_event_gap", result["gap_indicators"])
        self.assertIn("ap_inventory_unavailable", result["gap_indicators"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["back_and_forth_by_access_point_pair"], [])

    def test_rejects_duplicate_refs_and_unbounded_windows(self):
        row = client(CLIENT_A, [])
        with self.assertRaises(ClientRoamingBacktrackError):
            project_client_roaming_backtrack(SITE, 100, 1_000, [row, row])
        with self.assertRaises(ClientRoamingBacktrackError):
            project_client_roaming_backtrack(SITE, 100, 100 + 86_400_001, [row])
        with self.assertRaises(ClientRoamingBacktrackError):
            project_client_roaming_backtrack(SITE, 100, 1_000, [])


if __name__ == "__main__":
    unittest.main()
