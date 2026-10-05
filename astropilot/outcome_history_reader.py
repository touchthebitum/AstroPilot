"""Best-effort historical snapshot. Never invokes a store or writer lock."""
from __future__ import annotations

from astropilot.field_lab_paths import require_user_directory
from decision.storage_namespace import is_field_lab_document

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from decision.outcome_evaluation_persistence import deserialize_outcome_evaluation
from decision.field_observation import validate_observation_identity
from decision.execution_lineage_persistence import validate_lineage_identity
from decision.weather.decision_forecast_evidence_persistence import validate_decision_id
from decision.field_observation_persistence import deserialize_field_observation
from decision.weather.decision_forecast_evidence_persistence import deserialize_decision_forecast_evidence
from decision.execution_lineage_persistence import deserialize_execution_lineage_aggregate
from decision.acceptance_lineage_persistence import deserialize_decision_acceptance_aggregate


# Per-document input budget; this does not bound total snapshot memory.
_MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024


class OutcomeHistoryDocumentTooLarge(RuntimeError):
    def __init__(self, info):
        self.marker = 'too_large:' + json.dumps(
            [_MAX_DOCUMENT_BYTES, info.st_dev, info.st_ino, info.st_mode,
             info.st_size, info.st_mtime_ns, info.st_ctime_ns], separators=(',', ':'))
        super().__init__('outcome_history_document_too_large')


class OutcomeHistoryUnavailable(RuntimeError):
    pass


# Keep stdlib identities for capability membership even when callers instrument
# the operations (for example, to exercise directory/document swap races).
_DIR_FD_OPERATIONS = (os.open, os.stat)
_SCANDIR_OPERATION = os.scandir


def _require_secure_fs_capabilities():
    """Reject unsupported readers without probing or touching document storage."""
    supports_dir_fd = getattr(os, 'supports_dir_fd', None)
    supports_fd = getattr(os, 'supports_fd', None)
    # stdlib declares these capabilities as sets. Reject malformed declarations
    # explicitly, without catching exceptions from operations or membership.
    if (os.name != 'posix' or
            type(supports_dir_fd) not in (set, frozenset) or
            type(supports_fd) not in (set, frozenset) or
            not all(hasattr(os, flag) for flag in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK')) or
            not all(operation in supports_dir_fd for operation in _DIR_FD_OPERATIONS) or
            _SCANDIR_OPERATION not in supports_fd):
        raise OutcomeHistoryUnavailable('outcome_history_unavailable')


@dataclass(frozen=True)
class OutcomeHistorySnapshot:
    evaluations: tuple
    observations: dict
    evidence: dict
    executions: dict
    decisions: dict
    fingerprint: str
    diagnostics: tuple
    complete: bool
    stable: bool = True


class FileOutcomeHistoryReader:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _directory_fd(self, kind):
        _require_secure_fs_capabilities()
        require_user_directory(self.directory)
        require_user_directory(self.directory / kind)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            root = os.open(self.directory, flags)
        except OSError as error:
            raise OutcomeHistoryUnavailable('outcome_history_storage_unavailable') from error
        try:
            return os.open(kind, flags, dir_fd=root)
        finally:
            os.close(root)

    def _inventory(self, kind):
        try:
            fd = self._directory_fd(kind)
            try:
                with os.scandir(fd) as entries:
                    return sorted(entry.name for entry in entries if entry.name.endswith('.json'))
            finally:
                os.close(fd)
        except FileNotFoundError:
            return []
        except OSError as error:
            raise OutcomeHistoryUnavailable('outcome_history_unavailable') from error

    def _read_bytes(self, kind, name, *, remaining_total_budget=None):
        read_limit = (_MAX_DOCUMENT_BYTES if remaining_total_budget is None
                      else min(_MAX_DOCUMENT_BYTES, remaining_total_budget))
        if read_limit < 0:
            raise ValueError("negative_read_budget")
        # Fingerprint reads obey the same identity rules as decoded documents.
        identity = name[:-5]
        if kind == 'decision_forecast_evidence':
            validate_decision_id(identity)
        elif kind in ('execution_lineage', 'decision_lineage'):
            validate_lineage_identity(identity, field='document_id')
        else:
            validate_observation_identity(identity, field='document_id')
        directory = self._directory_fd(kind)
        try:
            expected = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(expected.st_mode):
                raise OSError('unsafe_document')
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
                    raise OSError('unsafe_document')
                if opened.st_size > _MAX_DOCUMENT_BYTES:
                    raise OutcomeHistoryDocumentTooLarge(opened)
                with os.fdopen(fd, 'rb', buffering=0, closefd=False) as stream:
                    raw = bytearray()
                    while len(raw) <= read_limit:
                        budget = read_limit + 1 - len(raw)
                        try:
                            chunk = stream.read(min(_READ_CHUNK_BYTES, budget))
                        except InterruptedError:
                            continue
                        if not chunk:
                            return bytes(raw)
                        raw.extend(chunk)
                    # Use current descriptor metadata when growth crossed the budget.
                    raise OutcomeHistoryDocumentTooLarge(os.fstat(fd))
            finally:
                os.close(fd)
        finally:
            os.close(directory)

    def _digest(self, kind, name):
        try:
            return hashlib.sha256(self._read_bytes(kind, name)).hexdigest()
        except OutcomeHistoryDocumentTooLarge as error:
            return error.marker
        except FileNotFoundError:
            return 'missing'
        except ValueError:
            return 'invalid_identity'
        except OSError:
            return 'unreadable'

    def _metadata(self, inventories):
        result = {}
        for kind, names in inventories.items():
            if not names:
                continue
            try:
                fd = self._directory_fd(kind)
                try:
                    for name in names:
                        try:
                            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                            result[kind + '/' + name] = (info.st_dev, info.st_ino, info.st_mode,
                                info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                        except OSError:
                            result[kind + '/' + name] = None
                finally:
                    os.close(fd)
            except OSError:
                result[kind] = None
        return result

    def read(self):
        _require_secure_fs_capabilities()
        manifest = {}
        diagnostics = []
        content_changed = False
        values = {key: {} for key in ('outcome_evaluations', 'field_observations',
                  'decision_forecast_evidence', 'execution_lineage', 'decision_lineage')}
        inventories = {kind: self._inventory(kind) for kind in values}
        initial_metadata = self._metadata(inventories)
        for kind, names in inventories.items():
            for name in names:
                manifest[kind + '/' + name] = self._digest(kind, name)

        def load(kind, identity, decoder, keyword):
            nonlocal content_changed
            # Domain decoders do not all enforce filesystem-safe join identities.
            try:
                if kind == 'decision_forecast_evidence':
                    validate_decision_id(identity)
                elif kind in ('execution_lineage', 'decision_lineage'):
                    validate_lineage_identity(identity, field=keyword)
                else:
                    validate_observation_identity(identity, field=keyword)
            except ValueError:
                diagnostics.append({'code': 'invalid_document_identity', 'kind': kind})
                return
            name = identity + '.json'
            key = kind + '/' + name
            try:
                raw = self._read_bytes(kind, name)
            except OutcomeHistoryDocumentTooLarge as error:
                content_changed = content_changed or (key in manifest and manifest[key] != error.marker)
                manifest.setdefault(key, error.marker)
                diagnostics.append({'code': 'document_too_large', 'kind': kind, 'id': identity})
                return
            except FileNotFoundError:
                manifest[key] = 'missing'
                diagnostics.append({'code': 'missing_join', 'kind': kind, 'id': identity})
                return
            except OSError:
                manifest[key] = 'unreadable'
                diagnostics.append({'code': 'unreadable_document', 'kind': kind, 'id': identity})
                return
            digest = hashlib.sha256(raw).hexdigest()
            content_changed = content_changed or (key in manifest and manifest[key] != digest)
            manifest.setdefault(key, digest)
            try:
                text = raw.decode('utf-8')
                root = json.loads(text)
                if is_field_lab_document(root):
                    diagnostics.append({'code': 'field_lab_document_excluded', 'kind': kind, 'id': identity})
                    # Evaluation filenames are persisted SHA-256 identities. An
                    # excluded document occupying one is ambiguous unless it is
                    # the lab artifact's own content-addressed filename.
                    if (kind == 'outcome_evaluations' and
                            re.fullmatch(r'[0-9a-f]{64}', identity) and
                            identity != hashlib.sha256(str(root.get('idempotency_key', '')).encode()).hexdigest()):
                        diagnostics.append({'code': 'expected_user_document_excluded', 'kind': kind, 'id': identity})
                    return
                if kind == 'outcome_evaluations':
                    if isinstance(root, dict) and (
                            type(root.get('schema_version')) is int and root['schema_version'] > 1 or
                            isinstance(root.get('domain_version'), str) and
                            root['domain_version'].startswith('outcome_evaluation.v') and
                            root['domain_version'] != 'outcome_evaluation.v1'):
                        diagnostics.append({'code': 'incompatible_version', 'kind': kind, 'id': identity})
                        return
                values[kind][identity] = decoder(text, **{keyword: identity})
            except (ValueError, TypeError, UnicodeError, RecursionError):
                diagnostics.append({'code': 'corrupt_document', 'kind': kind, 'id': identity})

        for kind, decoder, keyword in (
            ('outcome_evaluations', deserialize_outcome_evaluation, 'evaluation_id'),
            ('field_observations', deserialize_field_observation, 'observation_id'),
        ):
            for name in inventories[kind]:
                load(kind, name[:-5], decoder, keyword)
        evaluations = tuple(values['outcome_evaluations'].values())
        for identity in sorted({e.comparison.observation_id for e in evaluations}):
            if identity not in values['field_observations']:
                diagnostics.append({'code': 'missing_user_observation', 'kind': 'field_observations', 'id': identity})
        decision_ids = {e.comparison.decision_id for e in evaluations if e.comparison.decision_id}
        execution_ids = {e.comparison.execution_id for e in evaluations if e.comparison.execution_id}
        for kind, identities, decoder, keyword in (
            ('decision_forecast_evidence', decision_ids, deserialize_decision_forecast_evidence, 'decision_id'),
            ('execution_lineage', execution_ids, deserialize_execution_lineage_aggregate, 'execution_id'),
            ('decision_lineage', {e.comparison.decision_id for e in evaluations if e.comparison.execution_id and e.comparison.decision_id}, deserialize_decision_acceptance_aggregate, 'decision_id'),
        ):
            # Enumeration also distinguishes inaccessible directories from missing joins.
            self._inventory(kind)
            for identity in sorted(identities):
                load(kind, identity, decoder, keyword)
                if identity not in values[kind] and any(
                        d['code'] == 'field_lab_document_excluded' and d['kind'] == kind and d['id'] == identity
                        for d in diagnostics):
                    diagnostics.append({'code': 'expected_user_document_excluded', 'kind': kind, 'id': identity})
        # Content validation follows all decoding/join reads. Membership and metadata
        # are checked last, including files hashed early in this final pass.
        stable = not content_changed
        for key, digest in list(manifest.items()):
            kind, name = key.split('/')
            stable = self._digest(kind, name) == digest and stable
        final_inventories = {kind: self._inventory(kind) for kind in values}
        stable = (stable and final_inventories == inventories and
                  self._metadata(final_inventories) == initial_metadata)
        if not stable:
            diagnostics.append({'code': 'dataset_changed_during_read'})
        fingerprint = hashlib.sha256(json.dumps({'files': manifest, 'inventory': inventories},
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        complete = stable and not any(d['code'] not in ('incompatible_version', 'field_lab_document_excluded') for d in diagnostics)
        return OutcomeHistorySnapshot(evaluations, values['field_observations'],
            values['decision_forecast_evidence'], values['execution_lineage'],
            values['decision_lineage'], fingerprint, tuple(diagnostics), complete, stable)
