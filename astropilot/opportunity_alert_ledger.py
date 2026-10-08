"""Dedicated durable suppression state. Claims commit before ALERT is returned."""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astropilot.file_lock import exclusive_file_lock
from astropilot.user_profile import get_user_data_dir
from decision.models.opportunity_alert import aware
from decision.validation.productive_window_evidence import valid_number


class OpportunityAlertLedgerError(RuntimeError):
    """Emission must stop; never recover by silently discarding suppression state."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def _time(value):
    if not isinstance(value, str):
        raise ValueError('invalid_timestamp')
    parsed = datetime.fromisoformat(value)
    if not aware(parsed):
        raise ValueError('naive_timestamp')
    return parsed.astimezone(timezone.utc)


def _identity(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('invalid_identity')


class FileOpportunityAlertLedger:
    """One data directory per user; local-filesystem locking, shared by all writers."""
    def __init__(self, directory=None):
        self.directory = (Path(directory) if directory is not None else get_user_data_dir()).expanduser().resolve()
        self.path = self.directory / 'opportunity_alert_ledger.json'
        self.lock_path = self.directory / '.opportunity_alert_ledger.lock'

    def _load(self):
        try:
            text = self.path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return {'schema_version': 1, 'latest_logical_time': None, 'entries': {}, 'families': {}}
        try:
            doc = json.loads(text, object_pairs_hook=_object)
            if not isinstance(doc, dict) or set(doc) != {'schema_version', 'latest_logical_time', 'entries', 'families'}:
                raise ValueError('invalid_document')
            if type(doc['schema_version']) is not int or doc['schema_version'] != 1:
                raise ValueError('unsupported_schema')
            entries, families = doc['entries'], doc['families']
            if not isinstance(entries, dict) or not isinstance(families, dict):
                raise ValueError('invalid_maps')
            latest = _time(doc['latest_logical_time']) if doc['latest_logical_time'] is not None else None
            expected = {}
            for key, record in entries.items():
                _identity(key)
                if not isinstance(record, dict) or set(record) != {'family_key', 'last_emitted', 'policy_version'}:
                    raise ValueError('invalid_record')
                _identity(record['family_key'])
                if type(record['policy_version']) is not int or record['policy_version'] != 1:
                    raise ValueError('unsupported_policy')
                emitted = _time(record['last_emitted'])
                if latest is None or emitted > latest:
                    raise ValueError('invalid_watermark')
                family = record['family_key']
                expected[family] = max(expected.get(family, emitted), emitted)
            if set(families) != set(expected) or any(_time(families[f]) != t for f, t in expected.items()):
                raise ValueError('inconsistent_families')
            return doc
        except (ValueError, TypeError, OverflowError) as error:
            raise OpportunityAlertLedgerError('opportunity_alert_ledger_corrupt') from error

    def _write(self, doc):
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                    prefix='.opportunity_alert_ledger.', suffix='.tmp', delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(doc, temporary, sort_keys=True, separators=(',', ':'), allow_nan=False)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            # POSIX: persist the directory entry as well as the file contents.
            if os.name != 'nt':
                descriptor = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def claim(self, *, key, family, logical_time, cooldown_minutes, policy_version=1):
        _identity(key)
        _identity(family)
        if not aware(logical_time) or not valid_number(cooldown_minutes, positive=True):
            raise ValueError('invalid_alert_claim')
        if type(policy_version) is not int or policy_version != 1:
            raise OpportunityAlertLedgerError('unsupported_alert_ledger_policy')
        logical_time = logical_time.astimezone(timezone.utc)
        try:
            with exclusive_file_lock(self.lock_path):
                doc = self._load()
                previous = doc['latest_logical_time']
                if previous is not None and logical_time < _time(previous):
                    return False
                last = doc['families'].get(family)
                permitted = key not in doc['entries'] and (last is None or
                    logical_time >= _time(last) + timedelta(minutes=cooldown_minutes))
                changed = previous != logical_time.isoformat()
                doc['latest_logical_time'] = logical_time.isoformat()
                if permitted:
                    doc['entries'][key] = {'family_key': family, 'last_emitted': logical_time.isoformat(),
                        'policy_version': policy_version}
                    doc['families'][family] = logical_time.isoformat()
                if permitted or changed:
                    self._write(doc)
                return permitted
        except (OSError, UnicodeError, OverflowError) as error:
            raise OpportunityAlertLedgerError('opportunity_alert_ledger_unavailable') from error
