"""Bounded in-memory AP radio change plans; controller writes stay opt-in."""
from __future__ import annotations

import copy
import hashlib
import json
import secrets
import threading
import time
import re
from typing import Callable

try:
    from .change_journal import ALLOWED_JOURNAL_OPERATIONS
except ImportError:  # pragma: no cover - direct app-module execution
    from change_journal import ALLOWED_JOURNAL_OPERATIONS


class ChangeError(RuntimeError):
    pass


BANDS = frozenset(('radioSetting2g', 'radioSetting5g', 'radioSetting5g1',
                   'radioSetting5g2', 'radioSetting6g'))
CHANNEL_CHANGE_BANDS = frozenset(('radioSetting2g', 'radioSetting6g'))
CHANNEL_WIDTHS = {
    'RADIO_20': {20}, 'RADIO_40': {40}, 'RADIO_40_20': {20, 40},
    'RADIO_80': {80}, 'RADIO_80_40_20': {20, 40, 80},
    'RADIO_160': {160}, 'RADIO_160_80_40_20': {20, 40, 80, 160},
    'RADIO_240': {240}, 'RADIO_320': {320},
}
_OPAQUE_REF = re.compile(r"[0-9a-f]{24}\Z")
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")


def _journal_radio_snapshot(before: object, target: object) -> bool:
    if not isinstance(before, dict) or not before or not isinstance(target, dict) or not target:
        return False
    if set(before) != set(target) or not set(before).issubset(BANDS):
        return False
    for band in before:
        old, new = before[band], target[band]
        if not isinstance(old, dict) or not isinstance(new, dict):
            return False
        if set(old) == {"txPowerLevel"}:
            if (set(new) != {"txPowerLevel"} or type(old["txPowerLevel"]) is not int or
                    old["txPowerLevel"] not in (0, 1, 2, 4) or
                    type(new["txPowerLevel"]) is not int or new["txPowerLevel"] not in (0, 1, 2, 4)):
                return False
        elif set(old) == {"channel"}:
            channel = old["channel"]
            if type(channel) is not int or not 0 <= channel <= 1024:
                return False
            if set(new) == {"channel"}:
                if new["channel"] != "0":
                    return False
            elif set(new) == {"channel", "freq"}:
                target_channel, freq = new["channel"], new["freq"]
                if (not isinstance(target_channel, str) or not target_channel.isascii() or
                        len(target_channel) > 4 or not target_channel.isdecimal() or
                        str(int(target_channel)) != target_channel or
                        not 1 <= int(target_channel) <= 1024 or type(freq) is not int or
                        not 2000 <= freq <= 8000):
                    return False
            else:
                return False
        else:
            return False
    return True


def validate_changes(value: object) -> dict:
    if not isinstance(value, dict) or not value or len(value) > len(BANDS):
        raise ChangeError('changes_invalid')
    clean = {}
    for band, settings in value.items():
        if band not in BANDS or not isinstance(settings, dict):
            raise ChangeError('changes_invalid')
        if set(settings) == {'txPowerLevel'}:
            level = settings['txPowerLevel']
            # Custom requires a separately validated txPower; do not accept it here.
            if type(level) is not int or level not in (0, 1, 2, 4):
                raise ChangeError('changes_invalid')
            clean[band] = {'txPowerLevel': level}
        elif set(settings) == {'channel'}:
            channel = settings['channel']
            if type(channel) is not int or not 0 <= channel <= 1024:
                raise ChangeError('changes_invalid')
            if band not in CHANNEL_CHANGE_BANDS:
                raise ChangeError('channel_band_unsupported')
            clean[band] = {'channel': channel}
        else:
            raise ChangeError('changes_invalid')
    return clean


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


class RadioChangePlans:
    def __init__(self, read: Callable, write: Callable, *, catalog: Callable | None = None,
                 writes_enabled=False,
                 ttl=300, clock=time.monotonic, limit=100, journal=None,
                 require_journal: bool = False):
        self.read, self.write, self.catalog = read, write, catalog
        self.writes_enabled = writes_enabled
        self.ttl, self.clock, self.limit = ttl, clock, limit
        self.journal, self.require_journal = journal, require_journal
        self.plans = {}
        self.lock = threading.RLock()
        if journal is not None:
            try:
                for item in journal.in_doubt_plans():
                    operation = item.get('operation') if isinstance(item, dict) else None
                    if operation not in ALLOWED_JOURNAL_OPERATIONS:
                        raise ChangeError('journal_unavailable')
                    if operation != 'radio':
                        continue
                    refs = item.get('target_refs')
                    if (not isinstance(item, dict) or set(item) != {
                            'plan_id', 'operation', 'target_refs', 'before', 'target', 'state'} or
                            not isinstance(item.get('plan_id'), str) or
                            not _PLAN_ID.fullmatch(item['plan_id']) or item.get('state') != 'in_doubt' or
                            not isinstance(refs, dict) or set(refs) != {'site_ref', 'device_ref'} or
                            any(not isinstance(refs[key], str) or not _OPAQUE_REF.fullmatch(refs[key])
                                for key in ('site_ref', 'device_ref')) or
                            not _journal_radio_snapshot(item.get('before'), item.get('target'))):
                        raise ChangeError('journal_unavailable')
                    self.plans[item['plan_id']] = {
                        'target': (refs['site_ref'], refs['device_ref']),
                        'changes': copy.deepcopy(item['target']),
                        'previous': copy.deepcopy(item['before']),
                        'state': 'in_doubt', 'journalled': True,
                        'expires': float('inf'),
                    }
            except Exception:
                raise ChangeError('journal_unavailable') from None

    @staticmethod
    def _operator_refs(plan: dict) -> dict[str, str | None]:
        target = plan.get('target')
        if not isinstance(target, tuple) or len(target) != 2:
            return {'site_ref': None, 'device_ref': None}
        return {key: value if isinstance(value, str) and len(value) == 24 and
                all(char in '0123456789abcdef' for char in value) else None
                for key, value in zip(('site_ref', 'device_ref'), target)}

    def list_in_doubt(self) -> list[dict]:
        """List unresolved plans using only opaque references; performs no I/O."""
        with self.lock:
            return [{'plan_id': ident, 'state': 'in_doubt', 'scope': 'ap_radio_changes',
                     'target_refs': self._operator_refs(plan)}
                    for ident, plan in self.plans.items() if plan.get('state') == 'in_doubt']

    def inspect_in_doubt(self, plan_id: str) -> dict:
        """Inspect one unresolved plan and make at most one redacted read observation.

        A matching current value is only an observation; the original write outcome
        remains unknown because a later external change could produce that value.
        """
        with self.lock:
            plan = self._require_in_doubt(plan_id)
            changes = plan.get('changes')
            observation = {'status': 'unavailable'}
            try:
                current = self.read(*plan['target'])
                if not isinstance(current, dict):
                    raise ValueError('invalid_read')
                projected = {}
                if isinstance(changes, dict):
                    for band, fields in changes.items():
                        row = current.get(band)
                        if not isinstance(fields, dict) or not isinstance(row, dict):
                            continue
                        selected = {}
                        for field in fields:
                            value = row.get(field)
                            if (isinstance(value, (str, int, bool)) or value is None) and not isinstance(value, float):
                                if not isinstance(value, str) or len(value) <= 64:
                                    selected[field] = value
                        if selected:
                            projected[band] = selected
                observation = {'status': 'observed', 'data': projected}
            except Exception:
                pass
            return {'plan_id': plan_id, 'state': 'in_doubt', 'outcome': 'unknown',
                    'scope': 'ap_radio_changes', 'target_refs': self._operator_refs(plan),
                    'before': copy.deepcopy(plan.get('previous', {})),
                    'target': copy.deepcopy(changes) if isinstance(changes, dict) else {},
                    'current_observation': observation,
                    'observation_note': 'current_state_does_not_prove_original_write_outcome'}

    def close_in_doubt(self, plan_id: str, confirmation: object) -> dict:
        """Close an unresolved plan without retry; its outcome remains unknown."""
        with self.lock:
            if confirmation != 'outcome_unknown_no_retry':
                raise ChangeError('operator_confirmation_required')
            plan = self._require_in_doubt(plan_id)
            refs = self._operator_refs(plan)
            if plan.get('journalled'):
                try:
                    self.journal.close_unknown(plan_id, confirmation)
                except Exception:
                    raise ChangeError('journal_unavailable') from None
            del self.plans[plan_id]
            return {'plan_id': plan_id, 'state': 'closed_outcome_unknown',
                    'scope': 'ap_radio_changes', 'target_refs': refs}

    def _require_in_doubt(self, plan_id: str) -> dict:
        plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if plan is None:
            raise ChangeError('plan_unknown')
        if plan.get('state') != 'in_doubt':
            raise ChangeError('plan_not_in_doubt')
        return plan

    def preview(self, site_ref: str, device_ref: str, changes: object) -> dict:
        patch = validate_changes(changes)
        with self.lock:
            now = self.clock()
            # Expired/resolved plans cannot execute. Keep uncertain outcomes
            # until restart; never silently discard an uncertain outcome.
            self.plans = {k: v for k, v in self.plans.items()
                          if v['state'] == 'in_doubt' or now < v['expires']}
            if len(self.plans) >= self.limit:
                raise ChangeError('plan_capacity_reached')
            before = self.read(site_ref, device_ref)
            if not isinstance(before, dict):
                raise ChangeError('readback_invalid')
            catalog_snapshot = None
            canonical_patch = copy.deepcopy(patch)
            if any('channel' in fields for fields in patch.values()):
                if self.catalog is None:
                    raise ChangeError('channel_catalog_unavailable')
                catalog_snapshot = self.catalog(site_ref, device_ref)
                if not isinstance(catalog_snapshot, dict):
                    raise ChangeError('channel_catalog_invalid')
                canonical_patch = {}
                for band, fields in patch.items():
                    if 'channel' not in fields:
                        canonical_patch[band] = fields
                        continue
                    channel = fields['channel']
                    if channel == 0:
                        canonical_patch[band] = {'channel': '0'}
                        continue
                    entries = catalog_snapshot.get(band)
                    match = next((entry for entry in entries if entry.get('index') == channel), None) if isinstance(entries, list) else None
                    if not isinstance(match, dict) or type(match.get('freq')) is not int:
                        raise ChangeError('channel_not_supported')
                    current = before.get(band)
                    width = current.get('channelWidth') if isinstance(current, dict) else None
                    required_widths = CHANNEL_WIDTHS.get(width) if isinstance(width, str) else None
                    offered_widths = match.get('available_widths_mhz')
                    if (required_widths is None or not isinstance(offered_widths, list) or
                            not required_widths.issubset(set(offered_widths))):
                        raise ChangeError('channel_width_incompatible')
                    canonical_patch[band] = {'channel': str(channel), 'freq': match['freq']}
            previous = {}
            for band in canonical_patch:
                current = before.get(band)
                if 'txPowerLevel' in canonical_patch[band]:
                    if (not isinstance(current, dict) or type(current.get('txPowerLevel')) is not int
                            or current['txPowerLevel'] not in (0, 1, 2, 4)):
                        raise ChangeError('rollback_state_unavailable')
                    previous[band] = {'txPowerLevel': current['txPowerLevel']}
                else:
                    old_channel = current.get('channel') if isinstance(current, dict) else None
                    if not isinstance(old_channel, str) or not old_channel.isdecimal():
                        raise ChangeError('rollback_state_unavailable')
                    previous[band] = {'channel': int(old_channel)}
            ident = secrets.token_hex(24)
            self.plans[ident] = {'target': (site_ref, device_ref), 'changes': canonical_patch,
                'before_hash': digest({'state': before, 'catalog': catalog_snapshot}) if catalog_snapshot is not None else digest(before),
                'has_catalog': catalog_snapshot is not None, 'previous': previous,
                'expires': now + self.ttl, 'state': 'pending'}
            return {'plan_id': ident, 'expires_in_seconds': self.ttl,
                    'site_ref': site_ref, 'device_ref': device_ref,
                    'changes': copy.deepcopy(canonical_patch), 'previous': copy.deepcopy(previous),
                    'writes_enabled': self.writes_enabled,
                    'warning': 'radio_changes_may_interrupt_clients'}

    def apply(self, plan_id: str) -> dict:
        with self.lock:
            if not self.writes_enabled:
                raise ChangeError('writes_disabled')
            plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
            if plan is None:
                raise ChangeError('plan_unknown')
            if plan['state'] != 'pending':
                raise ChangeError('plan_already_consumed')
            if self.clock() >= plan['expires']:
                plan['state'] = 'expired'
                raise ChangeError('plan_expired')
            if self.require_journal and self.journal is None:
                raise ChangeError('journal_required')
            current = self.read(*plan['target'])
            catalog_snapshot = self.catalog(*plan['target']) if plan.get('has_catalog') and self.catalog else None
            current_hash = digest({'state': current, 'catalog': catalog_snapshot}) if plan.get('has_catalog') else digest(current)
            if current_hash != plan['before_hash']:
                plan['state'] = 'stale'
                raise ChangeError('state_changed')
            # The reads above may take long enough to cross the plan deadline.
            # Recheck immediately before dispatch so an expired plan never writes.
            if self.clock() >= plan['expires']:
                plan['state'] = 'expired'
                raise ChangeError('plan_expired')
            if self.journal is not None:
                refs = self._operator_refs(plan)
                if any(value is None for value in refs.values()):
                    plan['state'] = 'in_doubt'
                    plan['journalled'] = True
                    raise ChangeError('journal_unavailable')
                try:
                    self.journal.record_dispatch_intent(
                        operation='radio', plan_id=plan_id, target_refs=refs,
                        before=copy.deepcopy(plan['previous']),
                        target=copy.deepcopy(plan['changes']))
                except Exception:
                    plan['state'] = 'in_doubt'
                    plan['journalled'] = True
                    raise ChangeError('journal_unavailable') from None
                plan['journalled'] = True
                if self.clock() >= plan['expires']:
                    try:
                        self.journal.record_outcome(plan_id, 'unknown')
                    except Exception:
                        pass
                    plan['state'] = 'in_doubt'
                    raise ChangeError('plan_expired')
                # Repeat the complete before-state check after the durable
                # intent, including the channel catalog and its constraints.
                try:
                    dispatch_state = self.read(*plan['target'])
                    dispatch_catalog = (self.catalog(*plan['target'])
                                        if plan.get('has_catalog') and self.catalog else None)
                    dispatch_hash = (digest({'state': dispatch_state, 'catalog': dispatch_catalog})
                                     if plan.get('has_catalog') else digest(dispatch_state))
                    if dispatch_hash != plan['before_hash']:
                        raise ChangeError('state_changed')
                except Exception:
                    try:
                        self.journal.record_outcome(plan_id, 'unknown')
                    except Exception:
                        pass
                    plan['state'] = 'in_doubt'
                    raise ChangeError('change_in_doubt') from None
                if self.clock() >= plan['expires']:
                    try:
                        self.journal.record_outcome(plan_id, 'unknown')
                    except Exception:
                        pass
                    plan['state'] = 'in_doubt'
                    raise ChangeError('plan_expired')
            # Consume before dispatch. Timeout/transport failure must never repeat.
            plan['state'] = 'in_doubt'
            try:
                self.write(*plan['target'], copy.deepcopy(plan['changes']))
                after = self.read(*plan['target'])
                if not all(isinstance(after.get(b), dict) and
                           all(after[b].get(k) == v for k, v in fields.items())
                           for b, fields in plan['changes'].items()):
                    raise ChangeError('readback_mismatch')
            except Exception:
                if plan.get('journalled'):
                    try:
                        self.journal.record_outcome(plan_id, 'unknown')
                    except Exception:
                        pass
                raise ChangeError('change_in_doubt') from None
            if plan.get('journalled'):
                try:
                    self.journal.record_outcome(plan_id, 'verified_readback')
                except Exception:
                    try:
                        self.journal.record_outcome(plan_id, 'unknown')
                    except Exception:
                        pass
                    raise ChangeError('change_in_doubt') from None
            plan['state'] = 'applied'
            return {'status': 'verified', 'plan_id': plan_id,
                    'rollback_changes': copy.deepcopy(plan['previous'])}
