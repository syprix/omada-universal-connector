from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.config_snapshots import ConfigSnapshotError, compare_snapshots, project_capture
from tools.config_snapshot import _read_snapshot, _write_snapshot


SITE = "a" * 24
AP = "b" * 24
SSID = "c" * 24
NETWORK = "d" * 24


class _FakeClient:
    def __init__(self, *, channel: int = 36, vlan: int = 20,
                 ssid_enabled: bool = True) -> None:
        self.calls: list[str] = []
        self.channel, self.vlan, self.ssid_enabled = channel, vlan, ssid_enabled

    def list_sites(self):
        self.calls.append("sites")
        return {"status": "ok", "items": [{"site_ref": SITE}]}

    def list_devices(self, site_ref):
        self.calls.append("devices")
        return {"status": "ok", "site_ref": site_ref, "items": [{"device_ref": AP}]}

    def read_ap_radio_part(self, site_ref, device_ref, part):
        self.calls.append("radio")
        return {"status": "ok", "resource": part, "site_ref": site_ref,
                "device_ref": device_ref,
                "data": {"radioSetting5g": {"channel": self.channel,
                                               "txPower": 17,
                                               "secret": "never-copy"}}}

    def list_ssids(self, site_ref):
        self.calls.append("ssids")
        return {"status": "ok", "site_ref": site_ref, "items": [{"ssid_ref": SSID}]}

    def read_ssid_configuration(self, site_ref, ssid_ref):
        self.calls.append("ssid")
        return {"status": "ok", "resource": "ssid_configuration",
                "site_ref": site_ref, "data": {
                    "ssid_ref": ssid_ref, "enabled": self.ssid_enabled,
                    "security_mode": 3, "network_binding_ref": NETWORK,
                    "ssid_name": "private-name", "password": "secret",
                }}

    def list_networks(self, site_ref):
        self.calls.append("networks")
        return {"status": "ok", "site_ref": site_ref, "items": [{"network_ref": NETWORK}]}

    def read_site_lan_network_detail_summary(self, site_ref, network_ref):
        self.calls.append("lan")
        return {"status": "ok", "resource": "site_lan_network_detail_summary",
                "site_ref": site_ref, "network_ref": network_ref,
                "partial": False, "data": {
                    "purpose": "vlan", "vlan": self.vlan,
                    "gateway_subnet": "192.168.1.0/24",
                    "dhcp": {"enabled": True, "pool_range_count": 1},
                }}

    def read_dns_cache_settings(self, site_ref):
        self.calls.append("dns_cache")
        return {"status": "ok", "resource": "dns_cache_settings",
                "site_ref": site_ref, "data": {"enabled": True, "ttl_seconds": 600}}

    def read_dns_proxy_settings(self, site_ref):
        self.calls.append("dns_proxy")
        return {"status": "ok", "resource": "dns_proxy_settings",
                "site_ref": site_ref, "data": {
                    "enabled": True, "mode": "doh",
                    "dns_override_configured": True,
                    "resolver": "private.example",
                }}


def _capture(client: _FakeClient, *, at: str = "2026-11-18T10:00:00+00:00"):
    value = project_capture(
        site_label="home", site_ref=SITE, client=client,
        ap_ref=AP, ap_label="hall-ap", ssid_ref=SSID, ssid_label="guest-wifi",
        network_ref=NETWORK, network_label="guest-lan")
    value["captured_at"] = at
    return value


class ConfigSnapshotTests(unittest.TestCase):
    def test_capture_keeps_only_allowlisted_redacted_configuration(self) -> None:
        result = _capture(_FakeClient())
        rendered = json.dumps(result)
        for private in (SITE, AP, SSID, NETWORK, "private-name", "secret",
                        "192.168.1.0/24", "private.example"):
            self.assertNotIn(private, rendered)
        self.assertEqual(result["schema_version"], 1)
        sections = {(item["kind"], item["label"]): item["values"]
                    for item in result["sections"]}
        self.assertEqual(sections[("radio", "hall-ap")]["radio_5g"]["channel"], 36)
        self.assertEqual(sections[("ssid", "guest-wifi")]["network_binding_present"], True)
        self.assertEqual(sections[("lan", "guest-lan")]["vlan"], 20)
        self.assertEqual(sections[("dns", "site")]["proxy_mode"], "doh")

    def test_capture_uses_existing_bounded_read_methods_and_checks_site(self) -> None:
        client = _FakeClient()
        _capture(client)
        self.assertEqual(client.calls, ["sites", "devices", "radio", "ssids", "ssid",
                                        "networks", "lan", "dns_cache", "dns_proxy"])
        client.list_sites = lambda: {"status": "ok", "items": []}
        with self.assertRaisesRegex(ConfigSnapshotError, "site_ref_unknown"):
            project_capture(site_label="home", site_ref=SITE, client=client)

    def test_compare_marks_real_changes_and_missing_values_unknown(self) -> None:
        before = _capture(_FakeClient())
        after = _capture(_FakeClient(channel=40, vlan=30, ssid_enabled=False),
                         at="2026-11-18T11:00:00+00:00")
        before["sections"][0]["values"].pop("txPowerLevel", None)
        after["sections"][0]["values"].pop("txPowerLevel", None)
        result = compare_snapshots(before, after)
        sections = {(item["kind"], item["label"]): item
                    for item in result["sections"]}
        radio = sections[("radio", "hall-ap")]["fields"]
        radio = {item["field"]: item for item in radio}
        self.assertEqual(radio["radio_5g"]["status"], "changed")
        lan = {item["field"]: item for item in sections[("lan", "guest-lan")]["fields"]}
        ssid = {item["field"]: item for item in sections[("ssid", "guest-wifi")]["fields"]}
        self.assertEqual(lan["vlan"]["status"], "changed")
        self.assertEqual(ssid["enabled"]["status"], "changed")

    def test_partial_or_absent_sections_are_not_compared_as_unchanged(self) -> None:
        before = _capture(_FakeClient())
        after = _capture(_FakeClient())
        before["sections"] = [item for item in before["sections"] if item["kind"] != "lan"]
        radio_after = next(item for item in after["sections"] if item["kind"] == "radio")
        radio_after["partial"] = True
        result = compare_snapshots(before, after)
        radio = next(item for item in result["sections"] if item["kind"] == "radio")
        self.assertTrue(all(row["status"] == "not_comparable" for row in radio["fields"]))
        lan = next(item for item in result["sections"] if item["kind"] == "lan")
        self.assertEqual(lan["status"], "not_comparable")

    def test_scope_mismatch_invalid_data_and_duplicate_sections_fail_closed(self) -> None:
        before = _capture(_FakeClient())
        after = _capture(_FakeClient())
        after["site_label"] = "office"
        with self.assertRaisesRegex(ConfigSnapshotError, "snapshot_scope_mismatch"):
            compare_snapshots(before, after)
        after = _capture(_FakeClient())
        after["sections"].append(after["sections"][0])
        with self.assertRaisesRegex(ConfigSnapshotError, "snapshot_invalid"):
            compare_snapshots(before, after)
        with self.assertRaisesRegex(ConfigSnapshotError, "site_label_invalid"):
            project_capture(site_label="../home", site_ref=SITE, client=_FakeClient())
        with self.assertRaisesRegex(ConfigSnapshotError, "site_label_invalid"):
            project_capture(site_label=SITE, site_ref=SITE, client=_FakeClient())

    def test_snapshot_file_is_owner_only_and_never_overwritten(self) -> None:
        snapshot = _capture(_FakeClient())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            _write_snapshot(str(path), snapshot)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(_read_snapshot(str(path)), snapshot)
            with self.assertRaisesRegex(ConfigSnapshotError, "snapshot_write_failed"):
                _write_snapshot(str(path), snapshot)
            self.assertEqual(path.read_text(encoding="utf-8"),
                             json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, allow_nan=False) + "\n")
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaisesRegex(ConfigSnapshotError, "snapshot_file_invalid"):
                _read_snapshot(str(link))
            path.chmod(0o644)
            with self.assertRaisesRegex(ConfigSnapshotError, "snapshot_file_invalid"):
                _read_snapshot(str(path))


if __name__ == "__main__":
    unittest.main()
