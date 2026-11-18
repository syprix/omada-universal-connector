import copy
import unittest

from app.port_status_changes import SwitchPortStatusPlans, PortStatusChangeError
from app.port_name_changes import SwitchPortNamePlans, PortNameChangeError
from app.band_steering_changes import BandSteeringChangePlans, BandSteeringChangeError
from app.rrm_mode_changes import RrmModePlans, RrmModeChangeError
from app.site_led_changes import SiteLedPlans, SiteLedChangeError


class Clock:
    def __init__(self): self.value = 10.0
    def __call__(self): return self.value


class Journal:
    def __init__(self, hook=None):
        self.hook = hook
        self.events = []
    def in_doubt_plans(self): return []
    def record_dispatch_intent(self, **event):
        self.events.append(("intent", copy.deepcopy(event)))
        if self.hook: self.hook()
    def record_outcome(self, plan_id, outcome):
        self.events.append(("outcome", plan_id, outcome))
    def close_unknown(self, *args): pass


def fixture(kind, *, hook=None, clock=None, fail_read_number=None):
    site, switch = "a" * 24, "b" * 24
    initial = {
        "port_status": {"status": 0},
        "port_name": {"name": "Old port"},
        "band": {"mode": 0},
        "rrm": {"mode": 0, "timeRangeEnable": False, "resource": 0,
                "timeRangeId": "", "timeRangeAction": 0},
        "led": {"enable": False},
    }[kind]
    state = copy.deepcopy(initial)
    reads, writes = [], []
    def read(*args):
        reads.append(1)
        if fail_read_number == len(reads): raise OSError("private controller text")
        return copy.deepcopy(state)
    def write(*args):
        body = args[-1]
        writes.append(copy.deepcopy(body))
        state.clear(); state.update(copy.deepcopy(body))
    clock = clock or Clock()
    journal = Journal(hook)
    options = {"writes_enabled": True, "journal": journal, "require_journal": True,
               "clock": clock, "ttl_seconds": 300}
    if kind == "port_status":
        mgr = SwitchPortStatusPlans(read, write, **options)
        preview = mgr.preview(site, switch, 7, {"status": 1}, disruption_confirmed=True)
        exc = PortStatusChangeError
    elif kind == "port_name":
        mgr = SwitchPortNamePlans(read, write, **options)
        preview = mgr.preview(site, switch, 7, {"name": "New port"})
        exc = PortNameChangeError
    elif kind == "band":
        mgr = BandSteeringChangePlans(read, write, **options)
        preview = mgr.preview(site, {"mode": 1}, disruption_confirmed=True)
        exc = BandSteeringChangeError
    elif kind == "rrm":
        mgr = RrmModePlans(read, write, **options)
        preview = mgr.preview(site, {"mode": 1}, disruption_confirmed=True)
        exc = RrmModeChangeError
    else:
        mgr = SiteLedPlans(read, write, **options)
        preview = mgr.preview(site, {"enable": True})
        exc = SiteLedChangeError
    return mgr, preview["plan_id"], state, reads, writes, journal, clock, exc


class PresendJournalRecheckTests(unittest.TestCase):
    kinds = ("port_status", "port_name", "band", "rrm", "led")

    def test_mutation_during_intent_fsync_blocks_write_unknown_and_replay(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                holder = {}
                def mutate():
                    state = holder["state"]
                    key = next(iter(state))
                    if type(state[key]) is bool: state[key] = not state[key]
                    elif type(state[key]) is int: state[key] = 1
                    else: state[key] = "Changed"
                # Hook runs after the fixture exposes its state via a holder.
                mgr, pid, state, reads, writes, journal, _clock, exc = fixture(kind, hook=lambda: None)
                # Replace with a hook-bearing journal and bind the already-created fixture state.
                holder["state"] = state
                journal.hook = mutate
                with self.assertRaises(exc) as raised:
                    mgr.apply(pid)
                self.assertIn(str(raised.exception), ("state_changed", "change_in_doubt"))
                self.assertEqual(writes, [])
                self.assertEqual(journal.events[-1][0:1], ("outcome",))
                self.assertEqual(journal.events[-1][-1], "unknown")
                with self.assertRaisesRegex(exc, "plan_already_consumed"):
                    mgr.apply(pid)

    def test_post_intent_read_error_is_unknown_and_never_writes(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                mgr, pid, _state, _reads, writes, journal, _clock, exc = fixture(
                    kind, fail_read_number=3)
                with self.assertRaisesRegex(exc, "change_in_doubt"):
                    mgr.apply(pid)
                self.assertEqual(writes, [])
                self.assertEqual(journal.events[-1][-1], "unknown")
                with self.assertRaisesRegex(exc, "plan_already_consumed"):
                    mgr.apply(pid)

    def test_expiry_after_post_intent_read_is_unknown_and_never_writes(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                holder = {}
                def expire_on_post_intent_read():
                    holder["reads"] += 1
                    if holder["reads"] == 2: holder["clock"].value = 310.0
                clock = Clock(); holder.update(reads=0, clock=clock)
                # Use a read wrapper that advances time on the post-intent GET.
                mgr, pid, _state, _reads, writes, journal, _clock, exc = fixture(kind, clock=clock)
                original_read = mgr.read
                def timed_read(*args):
                    result = original_read(*args)
                    expire_on_post_intent_read()
                    return result
                mgr.read = timed_read
                with self.assertRaisesRegex(exc, "plan_expired"):
                    mgr.apply(pid)
                self.assertEqual(writes, [])
                self.assertEqual(journal.events[-1][-1], "unknown")
                with self.assertRaisesRegex(exc, "plan_already_consumed"):
                    mgr.apply(pid)

    def test_unchanged_post_intent_state_allows_exactly_one_write(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                mgr, pid, _state, reads, writes, journal, _clock, _exc = fixture(kind)
                result = mgr.apply(pid)
                self.assertEqual(result["status"], "verified")
                self.assertEqual(len(writes), 1)
                self.assertGreaterEqual(len(reads), 4)
                self.assertEqual(journal.events[-1][-1], "verified_readback")
                with self.assertRaises(Exception): mgr.apply(pid)

    def test_port_name_journal_never_contains_names(self):
        mgr, pid, _state, _reads, _writes, journal, _clock, _exc = fixture("port_name")
        mgr.apply(pid)
        encoded = repr(journal.events)
        self.assertNotIn("Old port", encoded)
        self.assertNotIn("New port", encoded)


if __name__ == "__main__": unittest.main()
