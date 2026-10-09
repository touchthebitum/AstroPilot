"""Explicit local caller attestations; no discovery, inference or hardware control."""
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from decision.models.guardian import GuardianSessionState
from decision.models.guardian_live_session import GuardianLiveSessionEvidence
from decision.services.guardian_live_contracts import live_session

PROVIDER_ID = 'local_session_attestation_v1'
_MAX_BYTES = 16384
_FIELDS = {'schema_version', 'version', 'source', 'provenance', 'state',
           'observed_at', 'session_id'}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('nonfinite_number')


def _decode(doc):
    if (type(doc) is not dict or set(doc) != _FIELDS
            or type(doc['schema_version']) is not int or doc['schema_version'] != 1
            or doc['version'] != 'guardian-live-session-v1'
            or doc['source'] != 'caller_session_heartbeat_v1'
            or doc['provenance'] != 'CALLER_ASSERTED'
            or not isinstance(doc['observed_at'], str)
            or not isinstance(doc['state'], str)
            or (doc['session_id'] is not None and
                (not isinstance(doc['session_id'], str) or not doc['session_id'].strip()))):
        raise ValueError('session_attestation_invalid')
    timestamp = datetime.fromisoformat(doc['observed_at'])
    if timestamp.utcoffset() is None:
        raise ValueError('session_attestation_invalid')
    return GuardianLiveSessionEvidence(GuardianSessionState(doc['state']), timestamp,
        doc['source'], doc['provenance'], doc['session_id'], doc['version'])


class GuardianSessionStore:
    """One authoritative file. Writers must explicitly renew ACTIVE and INACTIVE."""

    def __init__(self, path):
        self.path = Path(path)

    def write(self, evidence: GuardianLiveSessionEvidence):
        """Atomically replace an attestation; never synthesize a heartbeat time."""
        if not isinstance(evidence, GuardianLiveSessionEvidence):
            raise ValueError('session_attestation_invalid')
        if (not isinstance(evidence.state, GuardianSessionState)
                or not isinstance(evidence.observed_at, datetime)):
            raise ValueError('session_attestation_invalid')
        doc = dict(schema_version=1, version=evidence.version, source=evidence.source,
                   provenance=evidence.provenance, state=evidence.state.value,
                   observed_at=evidence.observed_at.isoformat(), session_id=evidence.session_id)
        _decode(doc)
        payload = json.dumps(doc, allow_nan=False).encode('utf-8')
        if len(payload) > _MAX_BYTES:
            raise ValueError('session_attestation_invalid')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.guardian-session-',
                                             delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def read(self, logical_time: datetime):
        """Unknown on missing, unreadable, corrupt, future or expired evidence."""
        try:
            with self.path.open('rb') as handle:
                payload = handle.read(_MAX_BYTES + 1)
            if len(payload) > _MAX_BYTES:
                return None
            doc = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique,
                             parse_constant=_constant)
            evidence = _decode(doc)
            state, _, _ = live_session(evidence, logical_time)
            return None if state is GuardianSessionState.UNKNOWN else evidence
        except (OSError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
            return None

    def __call__(self, logical_time: datetime):
        evidence = self.read(logical_time)
        if evidence is None:
            # Opt-in host must not retain decision eligibility on context loss.
            # The existing periodic runner maps this to UNKNOWN + EMERGENCY_STOP.
            raise RuntimeError('session_context_unavailable')
        return evidence
