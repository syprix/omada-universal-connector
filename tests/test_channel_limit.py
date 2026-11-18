from __future__ import annotations

import unittest

from app.channel_limit import (
    ChannelLimitError,
    project_ap_channel_limit,
    project_site_channel_limit,
)


class ChannelLimitProjectionTests(unittest.TestCase):
    def test_site_projection_keeps_only_documented_nested_boolean(self) -> None:
        result = project_site_channel_limit({"channelLimit": {"enable": True}})
        self.assertEqual(result["data"], {"enable": True})
        self.assertFalse(result["partial"])
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["omitted_field_count"], 0)
        self.assertNotIn("deprecated", result)

    def test_site_missing_invalid_and_unknown_fields_are_partial_without_echo(self) -> None:
        result = project_site_channel_limit({
            "channelLimit": {"enable": 1, "privateName": "secret"},
            "rawSiteId": "site-private-id",
        })
        self.assertEqual(result["data"], {})
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 3)
        self.assertEqual(result["omitted_fields"], ["channelLimit.enable", "unknown_fields"])
        rendered = repr(result)
        for private in ("privateName", "secret", "rawSiteId", "site-private-id"):
            self.assertNotIn(private, rendered)

    def test_site_absent_or_malformed_nested_object_is_partial(self) -> None:
        absent = project_site_channel_limit({})
        self.assertEqual(absent["missing_fields"], ["channelLimit.enable"])
        malformed = project_site_channel_limit({"channelLimit": None})
        self.assertTrue(malformed["partial"])
        self.assertEqual(malformed["omitted_fields"], ["channelLimit"])

    def test_ap_projection_preserves_documented_enum_without_interpreting_it(self) -> None:
        for enum in (0, 1, 2):
            result = project_ap_channel_limit({
                "supportChannelLimit": False,
                "channelLimitType": enum,
                "defaultInstType5g": True,
                "defaultInstType6g": False,
            })
            self.assertEqual(result["data"]["channelLimitType"], enum)
            self.assertFalse(result["partial"])
            self.assertNotIn("hardware_support_state", result)
            self.assertNotIn("firmware_support_state", result)

    def test_ap_missing_invalid_and_unknown_fields_are_partial_without_private_data(self) -> None:
        result = project_ap_channel_limit({
            "supportChannelLimit": 1,
            "channelLimitType": 4,
            "defaultInstType5g": True,
            "privateField": "secret-value",
        })
        self.assertEqual(result["data"], {"defaultInstType5g": True})
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 4)
        self.assertEqual(result["omitted_fields"], [
            "channelLimitType", "supportChannelLimit", "unknown_fields",
        ])
        self.assertIn("defaultInstType6g", result["missing_fields"])
        self.assertNotIn("privateField", repr(result))
        self.assertNotIn("secret-value", repr(result))

    def test_ap_rejects_boolean_as_integer_and_out_of_range_values(self) -> None:
        for enum in (True, -1, 3, "2"):
            with self.subTest(enum=enum):
                result = project_ap_channel_limit({"channelLimitType": enum})
                self.assertTrue(result["partial"])
                self.assertNotIn("channelLimitType", result["data"])
                self.assertIn("channelLimitType", result["omitted_fields"])

    def test_rejects_non_object_and_oversized_inputs(self) -> None:
        for projector, value in (
            (project_site_channel_limit, None),
            (project_site_channel_limit, []),
            (project_site_channel_limit, {f"x{i}": i for i in range(33)}),
            (project_ap_channel_limit, "not-an-object"),
            (project_ap_channel_limit, {f"x{i}": i for i in range(33)}),
        ):
            with self.subTest(projector=projector.__name__), self.assertRaises(ChannelLimitError):
                projector(value)


if __name__ == "__main__":
    unittest.main()
