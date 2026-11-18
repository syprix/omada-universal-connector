from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from tools.wifi_measurement_session import MeasurementSessionError, run_session


SITE_REF = "a" * 24
CLIENT_REF = "b" * 24
AP_REF = "c" * 24


class FakeClock:
    def __init__(self) -> None:
        self.value = 10.0

    def __call__(self) -> float:
        return self.value


class FakeStopEvent:
    def __init__(self, clock: FakeClock, stop_after_waits: int | None = None) -> None:
        self.clock = clock
        self.waits = 0
        self.stop_after_waits = stop_after_waits

    def is_set(self) -> bool:
        return self.stop_after_waits is not None and self.waits >= self.stop_after_waits

    def wait(self, seconds: float) -> bool:
        self.clock.value += seconds
        self.waits += 1
        return self.is_set()


class WifiMeasurementSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output = os.path.join(self.temp_dir.name, "walk.jsonl")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run(self, fetch, *, max_samples=3, stop_event=None):
        clock = FakeClock()
        event = stop_event or FakeStopEvent(clock)
        return run_session(
            site_ref=SITE_REF, client_ref=CLIENT_REF, output_path=self.output,
            duration_seconds=20, interval_seconds=2, max_samples=max_samples,
            fetch=fetch, stop_event=event, monotonic=clock,
            now_ms=lambda: 1_800_000_000_000 + int((clock.value - 10) * 1000))

    def test_records_bounded_redacted_samples_with_private_file_permissions(self) -> None:
        paths = []

        def fetch(path):
            paths.append(path)
            if path.endswith("/devices"):
                return {"status": "ok", "resource": "devices", "items": []}
            return {"status": "ok", "resource": "client_detail", "client_ref": CLIENT_REF,
                    "wireless": True, "rssi": -57, "snr": 32, "channel": 44,
                    "radio_id": 1, "signal_level": 87, "rx_rate_kbps": 866,
                    "tx_rate_kbps": 720, "access_point_ref": AP_REF,
                    "ap_mac": "00:11:22:33:44:66"}

        result = self._run(fetch)
        text = Path(self.output).read_text(encoding="utf-8")
        records = [json.loads(line) for line in text.splitlines()]
        self.assertEqual(paths, [f"/v1/sites/{SITE_REF}/devices"] +
                         [f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF}"] * 3)
        self.assertEqual(result["sample_count"], 3)
        self.assertEqual(records[0]["record_type"], "session")
        self.assertEqual([x["record_type"] for x in records[1:-1]], ["sample"] * 3)
        self.assertEqual(records[1]["metrics"]["rssi"], -57)
        self.assertEqual(records[1]["access_point_ref"], AP_REF)
        self.assertTrue(records[1]["partial"] is False)
        self.assertEqual(records[-1]["stop_reason"], "sample_limit")
        self.assertNotIn(SITE_REF, text)
        self.assertNotIn(CLIENT_REF, text)
        self.assertNotIn("00:11:22:33:44:66", text)
        self.assertEqual(stat.S_IMODE(os.stat(self.output).st_mode), 0o600)

    def test_missing_ap_binding_is_marked_partial(self) -> None:
        def fetch(path):
            if path.endswith("/devices"):
                return {"status": "ok", "resource": "devices", "items": []}
            return {"status": "ok", "resource": "client_detail", "client_ref": CLIENT_REF,
                    "wireless": True, "rssi": -64, "snr": 28, "channel": 149}

        self._run(fetch, max_samples=1)
        sample = json.loads(Path(self.output).read_text(encoding="utf-8").splitlines()[1])
        self.assertIsNone(sample["access_point_ref"])
        self.assertEqual(sample["ap_assignment_status"], "unavailable")
        self.assertTrue(sample["partial"])

    def test_user_stop_writes_a_complete_footer(self) -> None:
        clock = FakeClock()
        stop = FakeStopEvent(clock, stop_after_waits=1)

        def fetch(path):
            if path.endswith("/devices"):
                return {"status": "ok", "resource": "devices", "items": []}
            return {"status": "ok", "resource": "client_detail", "client_ref": CLIENT_REF,
                    "wireless": True, "rssi": -57}

        self._run(fetch, max_samples=10, stop_event=stop)
        records = [json.loads(line) for line in Path(self.output).read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(records[-1]["sample_count"], 1)
        self.assertEqual(records[-1]["stop_reason"], "user_stopped")

    def test_not_wireless_state_is_recorded_without_claiming_an_outage(self) -> None:
        def fetch(path):
            if path.endswith("/devices"):
                return {"status": "ok", "resource": "devices", "items": []}
            return {"status": "ok", "resource": "client_detail", "client_ref": CLIENT_REF,
                    "wireless": False, "active": False}

        self._run(fetch, max_samples=1)
        sample = json.loads(Path(self.output).read_text(encoding="utf-8").splitlines()[1])
        self.assertEqual(sample["sample_status"], "not_wireless")
        self.assertTrue(sample["partial"])
        self.assertNotIn("outage", sample)

    def test_read_failure_is_saved_as_one_unavailable_sample_and_stops(self) -> None:
        calls = []

        def fetch(path):
            calls.append(path)
            if path.endswith("/devices"):
                return {"status": "ok", "resource": "devices", "items": []}
            raise RuntimeError("must not be serialized")

        result = self._run(fetch, max_samples=10)
        records = [json.loads(line) for line in Path(self.output).read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(result["status"], "partial")
        self.assertEqual(records[-2]["sample_status"], "read_unavailable")
        self.assertEqual(records[-1]["stop_reason"], "source_error")
        self.assertNotIn("must not be serialized", Path(self.output).read_text(encoding="utf-8"))
        self.assertEqual(calls.count(f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF}"), 1)

    def test_invalid_limits_and_existing_output_fail_closed(self) -> None:
        def fetch(_path):
            return {"status": "ok", "resource": "devices", "items": []}

        with self.assertRaisesRegex(MeasurementSessionError, "limits_invalid"):
            run_session(site_ref=SITE_REF, client_ref=CLIENT_REF, output_path=self.output,
                        duration_seconds=601, interval_seconds=1, max_samples=1, fetch=fetch)
        self.assertFalse(os.path.exists(self.output))
        with open(self.output, "x", encoding="utf-8"):
            pass
        with self.assertRaisesRegex(MeasurementSessionError, "output_unavailable"):
            self._run(fetch, max_samples=1)

    def test_duration_limit_bounds_the_last_wait(self) -> None:
        clock = FakeClock()
        stop = FakeStopEvent(clock)
        output = os.path.join(self.temp_dir.name, "short.jsonl")
        calls = []

        def fetch(path):
            calls.append(path)
            if path.endswith("/devices"):
                return {"status": "ok", "resource": "devices", "items": []}
            return {"status": "ok", "resource": "client_detail", "client_ref": CLIENT_REF,
                    "wireless": True, "rssi": -57}

        run_session(site_ref=SITE_REF, client_ref=CLIENT_REF, output_path=output,
                    duration_seconds=1, interval_seconds=2, max_samples=10,
                    fetch=fetch, stop_event=stop, monotonic=clock,
                    now_ms=lambda: 1_800_000_000_000 + int((clock.value - 10) * 1000))
        records = [json.loads(line) for line in Path(output).read_text(
            encoding="utf-8").splitlines()]
        self.assertEqual(calls.count(f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF}"), 1)
        self.assertEqual(records[-1]["stop_reason"], "duration_limit")
        self.assertEqual(clock.value, 11.0)


if __name__ == "__main__":
    unittest.main()
