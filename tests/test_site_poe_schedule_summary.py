from __future__ import annotations

import unittest

from app.site_poe_schedule_summary import summarize_site_poe_schedule


REF = "a" * 24
MAC = "aa:bb:cc:dd:ee:ff"


class SitePoeScheduleSummaryTests(unittest.TestCase):
    def test_joins_only_documented_watt_values_and_redacts_identity(self) -> None:
        result = summarize_site_poe_schedule(
            [{"device_ref": REF, "device_type": "switch", "name": "private"}],
            {REF: MAC},
            [{"mac": MAC, "name": "private", "poePort": {"poePortIds": [1, 2]}}],
            [{"mac": MAC, "totalPowerUsed": 40, "totalPower": 120,
              "name": "private", "poePorts": [{"portId": 1}]}],
            [{"switchMac": MAC, "port": 1, "supportPoe": True,
              "poeDisplayType": 1, "poe": 1, "poeStatus": 1.0,
              "power": 40.0, "voltage": 52.0, "current": 0.7}],
            [{"id": "schedule-secret", "name": "secret schedule", "status": True,
              "turnOnTime": "profile-secret", "poePortsMap": {MAC: [1, 2]},
              "nextExecute": 123}],
            [{"profileId": "profile-secret", "name": "secret profile"}],
        )
        switch = result["data"]["switches"][0]
        self.assertEqual(switch["power_budget"], {
            "used_watts": 40, "rated_capacity_watts": 120, "available_watts": 80})
        self.assertEqual(switch["poe_capable_ports"], [1, 2])
        self.assertEqual(switch["port_telemetry"]["reported_port_count"], 1)
        self.assertEqual(switch["port_telemetry"]["measurement_presence_counts"], {
            "power": 1, "voltage": 1, "current": 1})
        self.assertEqual(switch["schedules"], [{
            "enabled": True, "scheduled_ports": [1, 2],
            "time_range_resolved": True, "next_execute_present": True}])
        self.assertNotIn("watts", result["port_measurement_units"])
        for secret in (MAC, "private", "schedule-secret", "secret schedule", "profile-secret"):
            self.assertNotIn(secret, repr(result))

    def test_does_not_invent_budget_or_resolve_ambiguous_switch(self) -> None:
        result = summarize_site_poe_schedule(
            [{"device_ref": REF, "device_type": "switch"}], {REF: MAC}, None,
            [{"mac": MAC, "totalPowerUsed": 4}], None, None, None)
        switch = result["data"]["switches"][0]
        self.assertNotIn("power_budget", switch)
        self.assertEqual(result["status"], "partial")

    def test_ambiguous_mac_is_not_joined(self) -> None:
        second = "b" * 24
        result = summarize_site_poe_schedule(
            [{"device_ref": REF, "device_type": "switch"},
             {"device_ref": second, "device_type": "switch"}],
            {REF: MAC, second: MAC}, [],
            [{"mac": MAC, "totalPowerUsed": 4, "totalPower": 9}], [], [], [])
        self.assertEqual(result["ambiguous_switch_count"], 2)
        self.assertNotIn("power_budget", result["data"]["switches"][0])
        self.assertNotIn(MAC, repr(result))


if __name__ == "__main__":
    unittest.main()
