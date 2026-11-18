from __future__ import annotations

import unittest

from app.client_history import ClientHistoryError, project_client_history


TARGET_MAC = "AA:BB:CC:DD:EE:FF"
OTHER_MAC = "11:22:33:44:55:66"


def _row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "mac": TARGET_MAC,
        "download": 12,
        "upload": 34,
        "duration": 56,
        "lastSeen": 1_700_000_000_000,
        "port": 7,
        "vid": 20,
        "reasonType": -1,
        "guest": False,
        "associationTime": 8,
        "associated": 1_700_000_000_001,
        "id": "private-row-id",
        "name": "private-client-name",
        "ssid": "private-network-name",
        "reason": "private-free-text",
        "deviceName": "private-ap-name",
        "ip": "192.0.2.77",
        "ipv6List": ["2001:db8::1"],
        "authInfo": [{"authType": 1, "info": "private-auth-info"}],
    }
    row.update(updates)
    return row


class ClientHistoryProjectionTests(unittest.TestCase):
    def test_projects_documented_scalar_allowlist_and_redacts_identity(self) -> None:
        result = project_client_history([_row()], TARGET_MAC)
        self.assertFalse(result["partial"])
        self.assertEqual(result["resource"], "client_history")
        self.assertEqual(result["data"], {"count": 1, "rows": [{
            "download": 12, "upload": 34, "duration": 56,
            "lastSeen": 1_700_000_000_000, "port": 7, "vid": 20,
            "reasonType": -1, "guest": False, "associationTime": 8,
            "associated": 1_700_000_000_001,
        }]})
        for private in ("private-row-id", TARGET_MAC, "private-client-name",
                        "private-network-name", "private-free-text", "private-ap-name",
                        "192.0.2.77", "2001:db8::1", "private-auth-info"):
            self.assertNotIn(private, repr(result))

    def test_binds_mac_normalized_internally_and_omits_other_client_rows(self) -> None:
        row = _row(mac="aa-bb-cc-dd-ee-ff")
        other = _row(mac=OTHER_MAC, name="must-not-leak")
        result = project_client_history([row, other], TARGET_MAC)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["count"], 1)
        self.assertEqual(result["omitted_count"], 1)
        self.assertNotIn(OTHER_MAC, repr(result))
        self.assertNotIn("must-not-leak", repr(result))

    def test_missing_or_invalid_mac_rows_are_omitted_and_partial(self) -> None:
        rows = [_row(mac="not-a-mac"), {"download": 1}, "private-invalid-row"]
        result = project_client_history(rows, TARGET_MAC)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"], {"count": 0, "rows": []})
        self.assertEqual(result["omitted_count"], 3)
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertNotIn("not-a-mac", repr(result))
        self.assertNotIn("private-invalid-row", repr(result))

    def test_missing_and_invalid_documented_values_mark_partial(self) -> None:
        result = project_client_history([_row(download=True, guest=1)], TARGET_MAC)
        self.assertTrue(result["partial"])
        self.assertNotIn("download", result["data"]["rows"][0])
        self.assertNotIn("guest", result["data"]["rows"][0])
        self.assertGreater(result["invalid_field_count"], 0)
        sparse = project_client_history([{"mac": TARGET_MAC, "guest": True}], TARGET_MAC)
        self.assertTrue(sparse["partial"])
        self.assertEqual(sparse["data"], {"count": 1, "rows": [{"guest": True}]})
        self.assertGreater(sparse["missing_field_count"], 0)

    def test_int32_int64_and_bool_checks_are_strict(self) -> None:
        for updates in (
            {"download": 2**63},
            {"upload": -(2**63) - 1},
            {"port": 2**31},
            {"vid": True},
            {"reasonType": 1.5},
            {"associationTime": 2**31 - 1 + 1},
            {"associated": False},
        ):
            with self.subTest(updates=updates):
                result = project_client_history([_row(**updates)], TARGET_MAC)
                self.assertTrue(result["partial"])
                self.assertGreater(result["invalid_field_count"], 0)

    def test_unknown_fields_and_private_nested_values_are_not_echoed(self) -> None:
        result = project_client_history([_row(
            controllerNote="private-unknown",
            authInfo=[{"authType": 2, "info": "private-auth", "rawToken": "secret-marker"}],
            ipv6List=["2001:db8::99"],
        )], TARGET_MAC)
        self.assertTrue(result["partial"])
        self.assertGreater(result["unknown_field_count"], 0)
        for private in ("controllerNote", "private-unknown", "rawToken", "secret-marker",
                        "private-auth", "2001:db8::99"):
            self.assertNotIn(private, repr(result))

    def test_empty_complete_list_is_valid_and_invalid_inputs_fail_closed(self) -> None:
        empty = project_client_history([], TARGET_MAC)
        self.assertFalse(empty["partial"])
        self.assertEqual(empty["data"], {"count": 0, "rows": []})
        with self.assertRaises(ClientHistoryError):
            project_client_history(None, TARGET_MAC)
        with self.assertRaises(ClientHistoryError):
            project_client_history([], "not-a-mac")

    def test_oversized_complete_row_list_is_rejected_not_truncated(self) -> None:
        with self.assertRaises(ClientHistoryError) as caught:
            project_client_history([_row() for _ in range(4001)], TARGET_MAC)
        self.assertEqual(caught.exception.code, "client_history_response_too_large")


if __name__ == "__main__":
    unittest.main()
