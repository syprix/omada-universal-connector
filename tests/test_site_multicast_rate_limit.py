import unittest

from app.site_multicast_rate_limit import (
    SiteMulticastRateLimitError, project_site_multicast_rate_limit,
)


class SiteMulticastRateLimitTests(unittest.TestCase):
    def test_projects_bounded_switches_rates_and_aggregate(self):
        result = project_site_multicast_rate_limit({"mcastRateLimit": {
            "enable": True, "arpEnable": True, "arpPps": 100,
            "igmpEnable": False, "igmpPps": 40, "dhcpEnable": True,
            "dhcpPps": 250,
        }})
        self.assertEqual(result["data"], {
            "enabled": True, "arp_enabled": True, "igmp_enabled": False,
            "dhcp_enabled": True, "arp_packets_per_second": 100,
            "igmp_packets_per_second": 40, "dhcp_packets_per_second": 250,
            "enabled_limiter_count": 2, "valid_switch_count": 4,
        })
        self.assertFalse(result["partial"])

    def test_invalid_and_unknown_fields_are_counted_without_echoing_values(self):
        result = project_site_multicast_rate_limit({"mcastRateLimit": {
            "enable": "yes", "arpPps": True, "privateAddress": "secret",
        }})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("secret", repr(result))
        with self.assertRaises(SiteMulticastRateLimitError):
            project_site_multicast_rate_limit({str(i): i for i in range(5)})


if __name__ == "__main__":
    unittest.main()
