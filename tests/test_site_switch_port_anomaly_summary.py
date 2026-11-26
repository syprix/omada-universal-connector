from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_switch_port_anomaly_summary import (
    SwitchPortAnomalySummaryError, summarize_site_switch_port_anomalies,
)


SITE = "a" * 24
SWITCH = "b" * 24
OTHER = "c" * 24
MAC = "AA-BB-CC-DD-EE-FF"
OTHER_MAC = "11:22:33:44:55:66"
PRIVATE = ("private-switch-name", "private-port-name", "private-site-id")


def inventory() -> list[dict[str, object]]:
    return [
        {"device_ref": SWITCH, "device_type": "Switch", "state": 1,
         "device_name": PRIVATE[0]},
        {"device_ref": OTHER, "device_type": "Gateway", "state": 1},
    ]


def overview(mac: str = MAC, port: int = 1, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "switchMac": mac, "port": port, "connectedStatus": 0,
        "portStatus": {"linkStatus": 0}, "portName": PRIVATE[1],
        "switchName": PRIVATE[0], "site": PRIVATE[2],
    }
    row.update(extra)
    return row


def counters(mac: str = MAC, port: int = 1, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "switchMac": mac, "port": port, "txErrors": 2, "rxErrors": 0,
        "txBytes": 100, "rxBytes": 200,
    }
    row.update(extra)
    return row


class SiteSwitchPortAnomalySummaryTests(unittest.TestCase):
    def summarize(self, overview_rows=None, counter_rows=None, **kwargs):
        return summarize_site_switch_port_anomalies(
            inventory(), {SWITCH: MAC}, overview_rows, counter_rows, **kwargs)

    def test_joins_inventory_port_state_and_error_counters_without_identities(self) -> None:
        result = self.summarize([overview()], [counters()])
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["partial"])
        self.assertEqual(result["resource"], "site_switch_port_anomaly_summary")
        self.assertEqual(result["interpretation"], "review_signals_not_diagnoses")
        self.assertEqual(
            result["source_contract"],
            "port_status_and_tx_rx_errors_documented_in_all_three_exports; status_codes_uninterpreted")
        self.assertEqual(result["live_support"], "unknown")
        self.assertEqual(result["drop_counters"],
                         "not_available_in_documented_port_counter_response")
        self.assertEqual(result["temporal_alignment"],
                         "inventory_and_port_feeds_are_separate_sequential_reads")
        switch = result["data"]["switches"][0]
        self.assertEqual(switch["switch_ref"], SWITCH)
        self.assertEqual(switch["inventory_state"], 1)
        self.assertEqual(switch["ports"][0], {
            "port": 1, "connected_status_code": 0, "link_status_code": 0,
            "signals": ["nonzero_txErrors"],
            "txErrors": 2, "rxErrors": 0,
        })
        for private in (*PRIVATE, MAC, OTHER_MAC):
            self.assertNotIn(private, str(result))

    def test_nonzero_errors_and_link_down_are_review_signals_only(self) -> None:
        result = self.summarize([overview(portStatus={"linkStatus": 1})],
                                [counters(txErrors=0, rxErrors=0)])
        port = result["data"]["switches"][0]["ports"][0]
        self.assertEqual(port["signals"], [])
        self.assertEqual(port["link_status_code"], 1)
        self.assertEqual(port["txErrors"], 0)
        self.assertEqual(port["rxErrors"], 0)

    def test_disabled_ports_are_not_flagged_as_link_down_and_invalid_totals_are_omitted(self) -> None:
        result = self.summarize([overview(connectedStatus=2)],
                                [counters(txErrors=-1, rxErrors=0)])
        port = result["data"]["switches"][0]["ports"][0]
        self.assertEqual(port["signals"], [])
        self.assertNotIn("txErrors", port)
        self.assertEqual(port["rxErrors"], 0)
        self.assertTrue(result["partial"])

    def test_missing_counters_mark_partial_and_do_not_default_to_zero(self) -> None:
        result = self.summarize([overview()], [])
        self.assertTrue(result["partial"])
        port = result["data"]["switches"][0]["ports"][0]
        self.assertNotIn("txErrors", port)
        self.assertNotIn("rxErrors", port)
        self.assertEqual(result["coverage"]["missing_error_counter_fields"], 2)

    def test_missing_port_status_fields_mark_partial(self) -> None:
        result = self.summarize([{"switchMac": MAC, "port": 1}], [counters()])
        self.assertTrue(result["partial"])
        self.assertEqual(result["coverage"]["missing_status_fields"], 2)
        self.assertNotIn("connected_status_code", result["data"]["switches"][0]["ports"][0])

    def test_ambiguous_inventory_and_duplicate_ports_are_explicit(self) -> None:
        inv = inventory() + [{"device_ref": "d" * 24, "device_type": "Switch"}]
        result = summarize_site_switch_port_anomalies(
            inv, {SWITCH: MAC, "d" * 24: MAC}, [overview()], [counters()])
        self.assertTrue(result["partial"])
        self.assertEqual(result["ambiguous_switch_count"], 2)
        duplicate = self.summarize([overview(), overview()], [counters()])
        self.assertTrue(duplicate["partial"])
        self.assertEqual(duplicate["coverage"]["duplicate_overview_ports"], 1)

    def test_device_limit_and_source_failures_are_reported(self) -> None:
        refs = [f"{i:024x}" for i in range(1, 35)]
        inv = [{"device_ref": ref, "device_type": "Switch"} for ref in refs]
        macs = {ref: f"02:00:00:00:00:{i:02x}" for i, ref in enumerate(refs, 1)}
        result = summarize_site_switch_port_anomalies(
            inv, macs, None, None, overview_error="upstream_unavailable",
            counter_error="upstream_timeout")
        self.assertTrue(result["partial"])
        self.assertEqual(result["switches_scanned"], 32)
        self.assertEqual(result["switches_omitted_device_limit"], 2)
        self.assertEqual(result["source_errors"], {
            "port_overview": "upstream_unavailable", "port_counters": "upstream_timeout"})

    def test_invalid_bounded_input_is_rejected(self) -> None:
        with self.assertRaises(SwitchPortAnomalySummaryError):
            summarize_site_switch_port_anomalies([], {}, [None] * 4097, [])

    def test_client_uses_one_inventory_and_two_site_wide_bounded_feeds(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-1"
        listing = {"status": "ok", "items": inventory()[:1]}
        client._switch_macs_by_site_ref[SITE] = {SWITCH: MAC}
        pages = {
            client._SWITCH_PORTS_PATH.format(controller_id="ctrl", site_id="site-1"):
                [overview()],
            client._SWITCH_PORT_COUNTERS_PATH.format(controller_id="ctrl", site_id="site-1"):
                [counters()],
        }
        with patch.object(client, "list_devices", return_value=listing) as devices, \
                patch.object(client, "_access_token", return_value="fixture-token"), \
                patch.object(client, "_read_pages", side_effect=lambda path, _token: pages[path]) as read:
            result = client.read_site_switch_port_anomaly_summary(SITE)
        devices.assert_called_once_with(SITE)
        self.assertEqual(read.call_count, 2)
        self.assertEqual(result["review_signal_port_count"], 1)
        self.assertFalse(result["partial"])


if __name__ == "__main__":
    unittest.main()
