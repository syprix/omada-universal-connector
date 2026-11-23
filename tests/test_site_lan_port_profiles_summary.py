import unittest

from app.site_lan_port_profiles_summary import (
    SiteLanPortProfilesError, project_site_lan_port_profiles,
)


def profile(**overrides):
    row = {
        "id": "private-id", "name": "Private Profile", "type": 2, "flag": 2,
        "networkTagsSetting": 1, "poe": 1, "dot1x": 2, "bandWidthCtrlType": 1,
        "vlanConfigEnable": True, "portIsolationEnable": False,
        "lldpMedEnable": True, "loopbackDetectEnable": True,
        "spanningTreeEnable": False, "voiceNetworkId": "private-network",
        "tagNetworkIds": ["private-tag"], "nativeBridgeVlan": 100,
    }
    row.update(overrides)
    return row


class SiteLanPortProfilesSummaryTests(unittest.TestCase):
    def test_counts_documented_profile_types_and_safe_flags(self):
        result = project_site_lan_port_profiles(
            [profile(), profile(type=0, flag=1, poe=0)], 2, 1, 10)
        self.assertEqual(result["profile_count"], 2)
        self.assertEqual(result["profile_enum_counts"]["type"], {"2": 1, "0": 1})
        self.assertEqual(result["profile_enum_counts"]["poe"], {"1": 1, "0": 1})
        self.assertEqual(result["feature_enabled_counts"]["vlanConfigEnable"],
                         {"true": 2, "false": 0, "unknown": 0})
        for secret in ("private-id", "Private Profile", "private-network", "private-tag", "100"):
            self.assertNotIn(secret, str(result))
        self.assertFalse(result["device_assignment_inferred"])
        self.assertFalse(result["partial"])

    def test_unknown_missing_fields_and_unlisted_properties_mark_partial(self):
        result = project_site_lan_port_profiles([profile(type=2, extra="unknown")], 1, 1, 1)
        self.assertTrue(result["partial"])
        missing = project_site_lan_port_profiles([{}], 1, 1, 1)
        self.assertTrue(missing["partial"])
        self.assertIn("unknown", missing["profile_enum_counts"]["type"])

    def test_rejects_invalid_enum_and_type(self):
        for row in (profile(type=9), profile(poe=True), profile(name=4)):
            with self.subTest(row=row), self.assertRaises(SiteLanPortProfilesError):
                project_site_lan_port_profiles([row], 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
