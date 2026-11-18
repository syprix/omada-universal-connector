import unittest
from app.changes import RadioChangePlans, ChangeError

class ChangesTests(unittest.TestCase):
    def setUp(self):
        self.state = {'radioSetting2g': {'txPowerLevel': 1}}
        self.calls = []
        def read(*args): return {k: dict(v) for k,v in self.state.items()}
        def write(*args):
            self.calls.append(args)
            self.state.update(args[-1])
        self.engine = RadioChangePlans(read, write, writes_enabled=True)
    def preview(self):
        return self.engine.preview('site', 'ap', {'radioSetting2g': {'txPowerLevel': 0}})['plan_id']
    def test_preview_identifies_only_its_opaque_target_refs(self):
        site_ref, device_ref = 'a' * 24, 'b' * 24
        preview = self.engine.preview(site_ref, device_ref,
                                      {'radioSetting2g': {'txPowerLevel': 0}})
        self.assertEqual(preview['site_ref'], site_ref)
        self.assertEqual(preview['device_ref'], device_ref)
        self.assertRegex(preview['site_ref'], r'^[0-9a-f]{24}$')
        self.assertRegex(preview['device_ref'], r'^[0-9a-f]{24}$')
        self.assertNotIn('raw-site-id', str(preview))
        self.assertNotIn('raw-device-id', str(preview))
    def test_apply_readback_and_replay(self):
        plan=self.preview()
        self.assertEqual(self.engine.apply(plan)['status'],'verified')
        self.assertEqual(len(self.calls),1)
        with self.assertRaisesRegex(ChangeError,'consumed'): self.engine.apply(plan)
    def test_default_disabled_and_preview_has_no_write(self):
        self.engine.writes_enabled=False
        plan=self.preview()
        with self.assertRaisesRegex(ChangeError,'disabled'): self.engine.apply(plan)
        self.assertFalse(self.calls)
    def test_stale_and_expired_never_write(self):
        plan=self.preview(); self.state['radioSetting2g']['txPowerLevel']=2
        with self.assertRaisesRegex(ChangeError,'state_changed'): self.engine.apply(plan)
        plan=self.preview(); self.engine.clock=lambda: float('inf')
        with self.assertRaisesRegex(ChangeError,'expired'): self.engine.apply(plan)
        self.assertFalse(self.calls)
    def test_uncertain_write_is_consumed(self):
        plan=self.preview()
        self.engine.write=lambda *args: (_ for _ in ()).throw(TimeoutError())
        with self.assertRaisesRegex(ChangeError,'in_doubt'): self.engine.apply(plan)
        with self.assertRaisesRegex(ChangeError,'consumed'): self.engine.apply(plan)
    def test_custom_and_unknown_fields_rejected(self):
        for patch in ({'radioSetting2g':{'txPowerLevel':3}}, {'radioSetting2g':{'channel':'6'}},
                      {'radioSetting2g':{'txPowerLevel':True}}):
            with self.assertRaises(ChangeError): self.engine.preview('s','a',patch)

    def test_readback_mismatch_blocks_replay(self):
        plan=self.preview()
        self.engine.write=lambda *args: None
        with self.assertRaisesRegex(ChangeError,'change_in_doubt'): self.engine.apply(plan)
        with self.assertRaisesRegex(ChangeError,'consumed'): self.engine.apply(plan)
    def test_missing_previous_level_has_no_plan(self):
        self.state={'radioSetting2g': {'txPowerLevel':3}}
        with self.assertRaisesRegex(ChangeError,'rollback_state_unavailable'): self.preview()
        self.assertFalse(self.engine.plans)

    def test_expired_completed_plan_releases_capacity_without_replay(self):
        now = [10.0]
        self.engine.clock = lambda: now[0]
        self.engine.limit = 1
        first = self.preview()
        self.engine.apply(first)
        now[0] = 311.0
        self.preview()
        with self.assertRaisesRegex(ChangeError, 'plan_unknown'):
            self.engine.apply(first)

    def test_slow_state_read_expiring_plan_aborts_before_write(self):
        now = [0.0]
        reads = [0]
        writes = []
        self.engine = RadioChangePlans(
            lambda *_: {'radioSetting2g': dict(self.state['radioSetting2g'])},
            lambda *args: writes.append(args), writes_enabled=True,
            ttl=10, clock=lambda: now[0])
        plan = self.preview()

        def slow_read(*_args):
            reads[0] += 1
            if reads[0] == 1:  # Apply-time read; preview used the original reader.
                now[0] = 10.0
            return {'radioSetting2g': dict(self.state['radioSetting2g'])}

        self.engine.read = slow_read
        now[0] = 1.0
        with self.assertRaisesRegex(ChangeError, 'plan_expired'):
            self.engine.apply(plan)
        self.assertEqual(writes, [])
        self.assertEqual(self.engine.plans[plan]['state'], 'expired')

    def test_slow_channel_catalog_expiring_plan_aborts_before_write(self):
        now = [0.0]
        catalog_calls = [0]
        writes = []
        state = {'radioSetting2g': {'channel': '1', 'freq': 2412,
                                    'channelWidth': 'RADIO_20'}}

        def catalog(*_args):
            catalog_calls[0] += 1
            if catalog_calls[0] == 2:  # Apply-time catalogue read.
                now[0] = 10.0
            return {'radioSetting2g': [
                {'index': 1, 'freq': 2412, 'available_widths_mhz': [20]},
                {'index': 2, 'freq': 2437, 'available_widths_mhz': [20]},
            ]}

        engine = RadioChangePlans(lambda *_: {'radioSetting2g': dict(state['radioSetting2g'])},
            lambda *args: writes.append(args), catalog=catalog, writes_enabled=True,
            ttl=10, clock=lambda: now[0])
        plan = engine.preview('site', 'ap', {'radioSetting2g': {'channel': 2}})['plan_id']
        now[0] = 1.0
        with self.assertRaisesRegex(ChangeError, 'plan_expired'):
            engine.apply(plan)
        self.assertEqual(writes, [])
        self.assertEqual(engine.plans[plan]['state'], 'expired')
