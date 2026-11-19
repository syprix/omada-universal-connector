from __future__ import annotations

import unittest

from app.client_timeline import ClientTimelineError, project_client_timeline


START = 1_700_000_000_000
END = START + 86_400_000
EVENT_TYPES = (0, 1, 2, 3, 100, 101, 102, 200, 201, 202)
TARGET_MAC = "AA-BB-CC-DD-EE-FF"


class ClientTimelineProjectionTests(unittest.TestCase):
    def test_projects_sessions_events_and_all_documented_types(self) -> None:
        raw = [{
            "mac": "aa:bb:cc:dd:ee:ff",
            "start": START,
            "end": END,
            "events": [{"time": START + i, "eventType": event_type}
                       for i, event_type in enumerate(EVENT_TYPES)],
        }]
        result = project_client_timeline(raw, START, END, TARGET_MAC)
        self.assertFalse(result["partial"])
        projected = result["data"]["sessions"][0]
        self.assertEqual(projected["start_ms"], START)
        self.assertEqual(projected["end_ms"], END)
        self.assertEqual([event["event_type"] for event in projected["events"]],
                         list(EVENT_TYPES))
        self.assertEqual(projected["events"][0]["time_ms"], START)

    def test_private_documented_values_are_silently_redacted(self) -> None:
        result = project_client_timeline([{
            "mac": "aa:bb:cc:dd:ee:ff", "start": START, "end": END,
            "events": [{"time": START, "eventType": 2,
                        "content": "private text", "attributes": {"ap": "private-mac"}}],
        }], START, END, TARGET_MAC)
        self.assertFalse(result["partial"])
        rendered = repr(result)
        for secret in ("aa:bb:cc:dd:ee:ff", "private text", "attributes", "private-mac"):
            self.assertNotIn(secret, rendered)

    def test_roaming_event_maps_only_same_site_ap_references(self) -> None:
        result = project_client_timeline([{
            "mac": TARGET_MAC, "start": START, "end": END,
            "events": [{"time": START + 1, "eventType": 2,
                        "content": "private AP details",
                        "attributes": {"old_dev_mac": "00-11-22-33-44-66",
                                       "dev_mac": "00-11-22-33-44-77"}}],
        }], START, END, TARGET_MAC,
           {"001122334466": "a" * 24, "001122334477": "b" * 24})
        event = result["data"]["sessions"][0]["events"][0]
        self.assertEqual(event["previous_access_point_ref"], "a" * 24)
        self.assertEqual(event["access_point_ref"], "b" * 24)
        for private in ("00-11-22-33-44-66", "00-11-22-33-44-77", "private AP details"):
            self.assertNotIn(private, repr(result))

    def test_wireless_disconnect_maps_documented_access_point_reference(self) -> None:
        result = project_client_timeline([{
            "mac": TARGET_MAC, "start": START, "end": END,
            "events": [{"time": START + 1, "eventType": 1,
                        "content": "private disconnect details",
                        "attributes": {"dev_mac": "00-11-22-33-44-66"}}],
        }], START, END, TARGET_MAC, {"001122334466": "a" * 24})
        event = result["data"]["sessions"][0]["events"][0]
        self.assertEqual(event["event_type"], 1)
        self.assertEqual(event["access_point_ref"], "a" * 24)
        self.assertNotIn("00-11-22-33-44-66", repr(result))
        self.assertNotIn("private disconnect details", repr(result))

    def test_unknown_fields_redacted_and_partial(self) -> None:
        result = project_client_timeline([{
            "mac": TARGET_MAC, "start": START, "end": END, "secretField": "private",
            "events": [{"time": START, "eventType": 1, "other": "hidden"}],
        }], START, END, TARGET_MAC)
        self.assertTrue(result["partial"])
        self.assertIn("unknown_fields", result["omitted_fields"])
        self.assertNotIn("private", repr(result))
        self.assertNotIn("hidden", repr(result))

    def test_sessions_are_bound_to_requested_client_mac(self) -> None:
        result = project_client_timeline([
            {"mac": "aa:bb:cc:dd:ee:ff", "start": START, "end": END,
             "events": []},
            {"mac": "11:22:33:44:55:66", "start": START, "end": END,
             "events": []},
            {"mac": "not-a-mac", "start": START, "end": END, "events": []},
            {"mac": "aa:bb-cc:dd:ee:ff", "start": START, "end": END, "events": []},
            {"start": START, "end": END, "events": []},
        ], START, END, TARGET_MAC)
        self.assertTrue(result["partial"])
        sessions = result["data"]["sessions"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0], {"start_ms": START, "end_ms": END, "events": []})
        self.assertIn("session_identity_mismatch", result["omitted_fields"])
        self.assertIn("session_identity_unverified", result["omitted_fields"])
        self.assertIn("sessions[4].mac", result["missing_fields"])
        self.assertEqual(result["omitted_field_count"], 4)
        rendered = repr(result)
        self.assertNotIn("11:22:33:44:55:66", rendered)
        self.assertNotIn("not-a-mac", rendered)
        self.assertNotIn("aa:bb-cc:dd:ee:ff", rendered)

    def test_sessions_without_matching_identity_are_dropped_with_bounded_count(self) -> None:
        result = project_client_timeline([
            {"start": START, "end": END,
             "events": [{"time": START, "eventType": 0, "content": "private"}]},
            {"mac": None, "start": START, "end": END, "events": []},
            {"mac": "11:22:33:44:55:66", "start": START, "end": END, "events": []},
        ], START, END, TARGET_MAC)
        self.assertEqual(result["data"]["sessions"], [])
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 3)
        self.assertIn("session_identity_unverified", result["omitted_fields"])
        self.assertIn("session_identity_mismatch", result["omitted_fields"])
        rendered = repr(result)
        for forbidden in ("private", "11:22:33:44:55:66", TARGET_MAC):
            self.assertNotIn(forbidden, rendered)

    def test_missing_and_null_fields_mark_partial_without_fabricating_values(self) -> None:
        result = project_client_timeline([{
            "mac": TARGET_MAC, "start": None,
            "events": [{"time": None}, {"eventType": None}],
        }], START, END, TARGET_MAC)
        self.assertTrue(result["partial"])
        session = result["data"]["sessions"][0]
        self.assertIsNone(session["start_ms"])
        self.assertNotIn("end_ms", session)
        self.assertNotIn("events", session["events"][0])
        self.assertIsNone(session["events"][0]["time_ms"])
        self.assertNotIn("event_type", session["events"][1])
        self.assertTrue(result["missing_fields"])

    def test_out_of_window_and_invalid_types_mark_partial_and_are_omitted(self) -> None:
        result = project_client_timeline([
            {"mac": TARGET_MAC, "start": START - 1, "end": END + 1,
             "events": [{"time": END + 1, "eventType": 0},
                        {"time": START, "eventType": 999},
                        {"time": True, "eventType": True}]},
            {"mac": TARGET_MAC, "start": END, "end": START, "events": []},
        ], START, END, TARGET_MAC)
        self.assertTrue(result["partial"])
        first = result["data"]["sessions"][0]
        self.assertNotIn("start_ms", first)
        self.assertNotIn("end_ms", first)
        self.assertEqual(first["events"][0], {"event_type": 0})
        self.assertEqual(first["events"][1], {"time_ms": START})
        self.assertEqual(first["events"][2], {})
        second = result["data"]["sessions"][1]
        self.assertEqual(second, {"start_ms": END, "events": []})

    def test_empty_and_missing_result_are_distinguished(self) -> None:
        empty = project_client_timeline([], START, END, TARGET_MAC)
        self.assertFalse(empty["partial"])
        self.assertEqual(empty["data"], {"sessions": []})
        missing = project_client_timeline(None, START, END, TARGET_MAC)
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["data"], {})
        self.assertEqual(missing["missing_fields"], ["sessions"])

    def test_global_size_bounds_and_invalid_root_or_window_fail_closed(self) -> None:
        too_many_events = [{"start": START, "end": END,
                            "events": [{"time": START, "eventType": 0}] * 1025}]
        for raw, start, end in (
            ("not-list", START, END),
            ([{}] * 129, START, END),
            (too_many_events, START, END),
            ([{"start": START, "end": END, "events": [],
               **{f"x{i}": i for i in range(30)}}], START, END),
            ([{"start": START, "end": END,
               "events": [{"time": START, "eventType": 0,
                           **{f"x{i}": i for i in range(31)}}]}], START, END),
            ([], True, END),
            ([], END, START),
        ):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ClientTimelineError):
                project_client_timeline(raw, start, end, TARGET_MAC)


if __name__ == "__main__":
    unittest.main()
