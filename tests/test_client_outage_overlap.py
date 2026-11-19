from __future__ import annotations

import unittest

from app.client_outage_overlap import (
    ClientOutageOverlapError,
    project_client_outage_overlap,
)


SITE = "a" * 24
CLIENT_A = "b" * 24
CLIENT_B = "c" * 24
CLIENT_C = "d" * 24
AP_A = "e" * 24
AP_B = "f" * 24


def timeline(*events: tuple[int, int, str | None], partial: bool = False) -> dict[str, object]:
    rows = []
    for timestamp, event_type, ap_ref in events:
        item: dict[str, object] = {"time_ms": timestamp, "event_type": event_type}
        if ap_ref is not None:
            item["access_point_ref"] = ap_ref
        rows.append(item)
    return {"status": "ok", "partial": partial,
            "data": {"sessions": [{"events": rows}]}}


def client(ref: str, connect: dict[str, object],
           disconnect: dict[str, object]) -> dict[str, object]:
    return {"client_ref": ref, "connect": connect, "disconnect": disconnect}


class ClientOutageOverlapTests(unittest.TestCase):
    def test_counts_distinct_client_pair_only_when_closed_intervals_overlap_on_same_ap(self) -> None:
        result = project_client_outage_overlap(SITE, 100, 1_000, [
            client(CLIENT_A, timeline((300, 0, AP_A)), timeline((100, 1, AP_A))),
            client(CLIENT_B, timeline((500, 0, AP_A)), timeline((200, 1, AP_A))),
            client(CLIENT_C, timeline((600, 0, AP_B)), timeline((250, 1, AP_B))),
        ])
        self.assertEqual(result["confirmed_overlaps_by_access_point"], [
            {"access_point_ref": AP_A,
             "confirmed_overlapping_client_pair_count": 1,
             "affected_client_count": 2},
        ])
        self.assertEqual(result["connection_cause"], "not_inferred")
        self.assertFalse(result["partial"])

    def test_no_overlap_when_intervals_are_disjoint_or_switch_aps(self) -> None:
        result = project_client_outage_overlap(SITE, 100, 1_000, [
            client(CLIENT_A, timeline((300, 0, AP_A)), timeline((100, 1, AP_A))),
            client(CLIENT_B, timeline((600, 0, AP_A)), timeline((400, 1, AP_A))),
        ])
        self.assertEqual(result["confirmed_overlaps_by_access_point"], [])

        result = project_client_outage_overlap(SITE, 100, 1_000, [
            client(CLIENT_A, timeline((500, 0, AP_A)), timeline((100, 1, AP_A))),
            client(CLIENT_B, timeline((500, 0, AP_B)), timeline((200, 1, AP_B))),
        ])
        self.assertEqual(result["confirmed_overlaps_by_access_point"], [])

    def test_unknown_mapping_and_unclosed_intervals_are_reported_separately(self) -> None:
        result = project_client_outage_overlap(SITE, 100, 1_000, [
            client(CLIENT_A, timeline((300, 0, None)), timeline((100, 1, None))),
            client(CLIENT_B, timeline(), timeline((200, 1, AP_A))),
        ])
        self.assertEqual(result["unknown_access_point_mapping_interval_count"], 1)
        self.assertEqual(result["unknown_access_point_mapping_event_count"], 1)
        self.assertEqual(result["unclosed_disconnect_interval_count"], 1)
        self.assertEqual(result["confirmed_overlaps_by_access_point"], [])
        self.assertTrue(result["partial"])

    def test_partial_unavailable_and_empty_sources_remain_visible(self) -> None:
        result = project_client_outage_overlap(SITE, 100, 1_000, [
            client(CLIENT_A, timeline((300, 0, AP_A), partial=True), timeline((100, 1, AP_A))),
            client(CLIENT_B, {"status": "error", "error": "permission_denied"},
                   {"status": "error", "error": "permission_denied"}),
        ])
        self.assertEqual(result["source_coverage"]["partial_client_count"], 2)
        self.assertEqual(result["source_coverage"]["unavailable_client_timeline_count"], 1)
        self.assertEqual(result["source_coverage"]["client_without_samples_count"], 0)
        self.assertTrue(result["partial"])

    def test_many_intervals_are_scanned_and_client_pair_is_counted_once(self):
        disconnect_a = [(1_000 + i * 10 + 1, 1, AP_A) for i in range(400)]
        connect_a = [(1_000 + i * 10 + 3, 0, AP_A) for i in range(400)]
        disconnect_b = [(1_000 + i * 10 + 4, 1, AP_A) for i in range(399)]
        connect_b = [(1_000 + i * 10 + 6, 0, AP_A) for i in range(399)]
        disconnect_b.append((1_000 + 399 * 10 + 2, 1, AP_A))
        connect_b.append((1_000 + 399 * 10 + 4, 0, AP_A))
        result = project_client_outage_overlap(SITE, 100, 10_000, [
            client(CLIENT_A, timeline(*connect_a), timeline(*disconnect_a)),
            client(CLIENT_B, timeline(*connect_b), timeline(*disconnect_b)),
        ])
        self.assertEqual(result["confirmed_overlaps_by_access_point"], [{
            "access_point_ref": AP_A,
            "confirmed_overlapping_client_pair_count": 1,
            "affected_client_count": 2,
        }])

    def test_blocked_or_other_event_codes_are_not_interpreted_as_disconnects(self) -> None:
        result = project_client_outage_overlap(SITE, 100, 1_000, [
            client(CLIENT_A, timeline((300, 0, AP_A)), timeline((100, 3, AP_A))),
            client(CLIENT_B, timeline((400, 0, AP_A)), timeline((200, 3, AP_A))),
        ])
        self.assertEqual(result["confirmed_overlaps_by_access_point"], [])
        self.assertEqual(result["source_coverage"]["invalid_or_unexpected_event_count"], 2)

    def test_rejects_unbounded_or_duplicate_client_selection(self) -> None:
        with self.assertRaises(ClientOutageOverlapError):
            project_client_outage_overlap(SITE, 100, 1_000, [
                client(CLIENT_A, timeline(), timeline()),
            ])
        with self.assertRaises(ClientOutageOverlapError):
            project_client_outage_overlap(SITE, 100, 1_000, [
                client(CLIENT_A, timeline(), timeline()),
                client(CLIENT_A, timeline(), timeline()),
            ])
        with self.assertRaises(ClientOutageOverlapError):
            project_client_outage_overlap(SITE, 100, 100 + 86_400_001, [
                client(CLIENT_A, timeline(), timeline()),
                client(CLIENT_B, timeline(), timeline()),
            ])


if __name__ == "__main__":
    unittest.main()
