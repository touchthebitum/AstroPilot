"""Best-effort historical snapshot. Never invokes a store or writer lock."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from decision.outcome_evaluation_persistence import deserialize_outcome_evaluation
from decision.field_observation_persistence import deserialize_field_observation
from decision.weather.decision_forecast_evidence_persistence import deserialize_decision_forecast_evidence
from decision.execution_lineage_persistence import deserialize_execution_lineage_aggregate
from decision.acceptance_lineage_persistence import deserialize_decision_acceptance_aggregate


class OutcomeHistoryUnavailable(RuntimeError):
    pass


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


class FileOutcomeHistoryReader:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _inventory(self, kind):
        try:
            with os.scandir(self.directory / kind) as entries:
                return sorted(entry.name for entry in entries if entry.name.endswith('.json'))
        except FileNotFoundError:
            return []
        except OSError as error:
            raise OutcomeHistoryUnavailable('outcome_history_unavailable') from error

    def read(self):
        manifest = {}
        diagnostics = []
        values = {key: {} for key in ('outcome_evaluations', 'field_observations',
                  'decision_forecast_evidence', 'execution_lineage', 'decision_lineage')}
        inventories = {}

        def load(kind, identity, decoder, keyword):
            # Identifiers from validated canonical documents only; no user path input.
            name = identity + '.json'
            path = self.directory / kind / name
            key = kind + '/' + name
            try:
                raw = path.read_bytes()
            except FileNotFoundError:
                manifest[key] = 'missing'
                diagnostics.append({'code': 'missing_join', 'kind': kind, 'id': identity})
                return
            except OSError:
                manifest[key] = 'unreadable'
                diagnostics.append({'code': 'unreadable_document', 'kind': kind, 'id': identity})
                return
            manifest[key] = hashlib.sha256(raw).hexdigest()
            try:
                text = raw.decode('utf-8')
                if kind == 'outcome_evaluations':
                    root = json.loads(text)
                    if isinstance(root, dict) and (
                            type(root.get('schema_version')) is int and root['schema_version'] > 1 or
                            isinstance(root.get('domain_version'), str) and
                            root['domain_version'].startswith('outcome_evaluation.v') and
                            root['domain_version'] != 'outcome_evaluation.v1'):
                        diagnostics.append({'code': 'incompatible_version', 'kind': kind, 'id': identity})
                        return
                values[kind][identity] = decoder(text, **{keyword: identity})
            except (ValueError, TypeError, UnicodeError):
                diagnostics.append({'code': 'corrupt_document', 'kind': kind, 'id': identity})

        for kind, decoder, keyword in (
            ('outcome_evaluations', deserialize_outcome_evaluation, 'evaluation_id'),
            ('field_observations', deserialize_field_observation, 'observation_id'),
        ):
            inventories[kind] = self._inventory(kind)
            for name in inventories[kind]:
                load(kind, name[:-5], decoder, keyword)
        evaluations = tuple(values['outcome_evaluations'].values())
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
        # Verify content and membership again: no durable snapshot or lock required.
        stable = all(self._inventory(kind) == names for kind, names in inventories.items())
        for key, digest in list(manifest.items()):
            try:
                current = hashlib.sha256((self.directory / key).read_bytes()).hexdigest()
            except FileNotFoundError:
                current = 'missing'
            except OSError:
                current = 'unreadable'
            stable = stable and current == digest
        if not stable:
            diagnostics.append({'code': 'dataset_changed_during_read'})
        fingerprint = hashlib.sha256(json.dumps({'files': manifest, 'inventory': inventories},
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        complete = stable and not any(d['code'] != 'incompatible_version' for d in diagnostics)
        return OutcomeHistorySnapshot(evaluations, values['field_observations'],
            values['decision_forecast_evidence'], values['execution_lineage'],
            values['decision_lineage'], fingerprint, tuple(diagnostics), complete)
