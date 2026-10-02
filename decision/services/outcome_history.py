"""Read projection and population contract for Outcome History v1."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone

from decision.models.forecast_observation_comparison import ForecastObservationParameters
from decision.weather.cloud_mapping_policy import map_cloud_cover_to_condition
from decision.outcome_evaluation_persistence import serialize_outcome_evaluation
from decision.services.outcome_history_statistics import UNITS, statistics, OutcomeHistoryStatisticsUnavailable
from decision.services.forecast_observation_comparison import (
    _inspect_evidence, _source_digest, _validated_field_observation,
)


class OutcomeHistoryInvalidFilter(ValueError):
    pass


class OutcomeHistoryDatasetChanged(ValueError):
    pass


POLICY = {'version': 'outcome_history.v1', 'unit': 'individual_observation',
          'schema_version': 1, 'domain_version': 'outcome_evaluation.v1',
          'evaluation_algorithm_version': 'outcome_evaluation.v1',
          'comparison_algorithm_version': 'forecast_observation.v1',
          'forecast_scope': 'decision_attached_evidence',
          'temporal_policy': {'version': 'nearest_forecast_utc.v1', 'maximum_absolute_offset_us': 1800000000,
                              'timezone_name': 'UTC', 'selection_mode': 'nearest_per_variable',
                              'interpolation_enabled': False, 'averaging_enabled': False},
          'cloud_mapping_policy': {'version': 'cloud_mapping.v1', 'boundaries_percent': [10.0, 25.0, 50.0, 80.0]},
          'superseded_statistics': 'excluded', 'interpretation': 'descriptive_only'}


def filters(*, observed_from=None, observed_to=None, latitude=None, longitude=None,
            provider=None, variable=None, mode=None, status=None, include_superseded=False, limit=50):
    def utc(value):
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
            if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
                raise ValueError()
            return parsed.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, AttributeError):
            raise OutcomeHistoryInvalidFilter('invalid_outcome_history_filters') from None
    start, end = utc(observed_from), utc(observed_to)
    if start and end and datetime.fromisoformat(start) > datetime.fromisoformat(end):
        raise OutcomeHistoryInvalidFilter('invalid_outcome_history_filters')
    if (latitude is None) != (longitude is None):
        raise OutcomeHistoryInvalidFilter('invalid_outcome_history_filters')
    for value, bound in ((latitude, 90), (longitude, 180)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > bound):
            raise OutcomeHistoryInvalidFilter('invalid_outcome_history_filters')
    if (variable is not None and variable not in UNITS or
        mode is not None and mode not in ('decision_only', 'execution') or
        status is not None and status not in ('comparable', 'partial', 'not_comparable') or
        provider is not None and (not isinstance(provider, str) or not provider.strip()) or
        type(include_superseded) is not bool or type(limit) is not int or not 1 <= limit <= 100):
        raise OutcomeHistoryInvalidFilter('invalid_outcome_history_filters')
    return dict(observed_from=start, observed_to=end, latitude=latitude, longitude=longitude,
                provider=provider, variable=variable, mode=mode, status=status,
                include_superseded=include_superseded, limit=limit)


def lineage_states(observations):
    """Validate each connected component before determining its active tip."""
    children = defaultdict(list)
    neighbors = defaultdict(set)
    for identity, obs in observations.items():
        parent = obs.supersedes_observation_id
        if parent:
            children[parent].append(identity)
            neighbors[identity].add(parent)
            neighbors[parent].add(identity)
    states = {}
    for identity in observations:
        if identity in states:
            continue
        component, pending = set(), [identity]
        while pending:
            node = pending.pop()
            if node in component:
                continue
            component.add(node)
            pending.extend(neighbors[node] - component)
        reasons = set()
        checked = set()
        for node in component:
            obs = observations.get(node)
            if obs is None:
                reasons.add('lineage_parent_missing')
                continue
            if len(children[node]) > 1:
                reasons.add('lineage_fork')
            parent = observations.get(obs.supersedes_observation_id)
            if parent and parent.decision_id != obs.decision_id:
                reasons.add('lineage_decision_mismatch')
            if parent and parent.execution_id != obs.execution_id:
                reasons.add('lineage_execution_mismatch')
            visited = set()
            current = obs
            while current and current.observation_id not in checked:
                if current.observation_id in visited:
                    reasons.add('lineage_cycle')
                    break
                visited.add(current.observation_id)
                current = observations.get(current.supersedes_observation_id)
            checked.update(visited)
        for node in component & observations.keys():
            states[node] = ('indeterminate' if reasons else 'superseded' if children[node] else 'active', sorted(reasons))
    return states


def admissible(evaluation):
    c = evaluation.comparison
    return (evaluation.evaluation_algorithm_version == 'outcome_evaluation.v1' and
            c.algorithm_version == 'forecast_observation.v1' and c.forecast_scope == 'decision_attached_evidence' and
            c.parameters == ForecastObservationParameters() and
            all(r.unit == UNITS[r.variable.value] for r in c.results))


def result_source_mismatches(evaluation, observation, evidence):
    """Validate persisted facts only; never select forecasts or recompute comparisons."""
    failures = {}
    for result in evaluation.comparison.results:
        if result.status.value != 'comparable':
            continue
        variable = result.variable.value
        codes = []
        cloud = variable == 'cloud_cover_percent'
        expected = (observation.conditions.cloud_state if cloud else
                    getattr(observation.conditions, variable)) if observation else None
        actual = result.observed_condition if cloud else result.observed_value
        if expected is None or actual != expected:
            codes.append('outcome_history_observed_source_mismatch')
        if (cloud and evaluation.comparison.parameters.cloud_mapping_policy ==
                ForecastObservationParameters().cloud_mapping_policy):
            percent = result.forecast_coverage_percent
            if (type(percent) is not float or not math.isfinite(percent) or
                    not 0.0 <= percent <= 100.0):
                codes.append('outcome_history_cloud_coverage_out_of_range')
            elif map_cloud_cover_to_condition(percent) != result.predicted_condition:
                codes.append('outcome_history_cloud_category_source_mismatch')
        provenance = result.forecast_point
        if provenance is not None:
            offset = provenance.temporal_offset
            if (abs(offset) > evaluation.comparison.parameters.temporal_policy.maximum_absolute_offset or
                    observation is not None and
                    provenance.forecast_for_utc - observation.observed_at_utc != offset):
                codes.append('outcome_history_temporal_policy_mismatch')
        value = result.forecast_coverage_percent if cloud else result.forecast_value
        matches = evidence is not None and observation is not None and provenance is not None and any(
            point.provider_id == provenance.provider_id and point.model_id == provenance.model_id and
            point.retrieved_at_utc == provenance.retrieved_at_utc and
            point.forecast_for_utc == provenance.forecast_for_utc and
            point.forecast_for_utc - observation.observed_at_utc == provenance.temporal_offset and
            any(v.variable == result.variable and v.unit == result.unit and v.value == value for v in point.values)
            for point in evidence.forecast_points)
        if not matches:
            codes.append('outcome_history_forecast_source_mismatch')
        if codes:
            failures[variable] = codes
    return failures


class _EvidenceInspectionCache:
    """Valid inspections only, with source references and a bounded LRU."""

    def __init__(self):
        self._entries = OrderedDict()

    def inspect(self, decision_id, evidence):
        key = (decision_id, id(evidence))
        if key in self._entries:
            self._entries.move_to_end(key)
            return True, self._entries[key][1]
        valid, canonical = _inspect_evidence(evidence)
        if valid:
            self._entries[key] = (evidence, canonical)
            if len(self._entries) > 16:
                self._entries.popitem(last=False)
        return valid, canonical


def project(evaluation, snapshot, states):
    return _project(evaluation, snapshot, states)


def _project(evaluation, snapshot, states, inspection_cache=None):
    raw = json.loads(serialize_outcome_evaluation(evaluation))['outcome_evaluation']
    comparison = raw.pop('comparison')
    observation_id = comparison['observation_id']
    obs = snapshot.observations.get(observation_id)
    unknown = {}
    state, reasons = states.get(observation_id, ('indeterminate', ['observation_missing']))
    if obs is not None and (obs.decision_id != comparison['decision_id'] or obs.execution_id != comparison['execution_id']):
        state, reasons = 'indeterminate', reasons + ['evaluation_observation_lineage_mismatch']
    evidence = snapshot.evidence.get(comparison['decision_id'])
    sources_coherent = False
    if obs is not None and evidence is not None:
        valid_evidence, canonical_evidence = (
            _inspect_evidence(evidence) if inspection_cache is None else
            inspection_cache.inspect(comparison['decision_id'], evidence))
        try:
            sources_coherent = (valid_evidence and evaluation.comparison.identity_persistable and
                _source_digest(canonical_evidence, _validated_field_observation(obs), identity_persistable=True)
                == evaluation.comparison.source_digest)
        except (ValueError, TypeError, RecursionError):
            sources_coherent = False
    if not sources_coherent:
        reasons = reasons + ['comparison_sources_unknown_or_mismatched']
        unknown['observed_at_utc'] = 'comparison_sources_unknown_or_mismatched'
        unknown['site'] = 'comparison_sources_unknown_or_mismatched'
    persisted = evaluation.comparison.observation_provenance
    if obs is not None and (
            persisted.source_type != obs.provenance.source_type or
            persisted.source_id != obs.provenance.source_id or
            persisted.capture_method != obs.provenance.capture_method or
            persisted.confidence != obs.quality.confidence or
            persisted.quality_flags != obs.quality.flags):
        sources_coherent = False
        reasons = reasons + ['outcome_history_observation_provenance_mismatch']
        unknown['observed_at_utc'] = 'outcome_history_observation_provenance_mismatch'
        unknown['site'] = 'outcome_history_observation_provenance_mismatch'
    mismatches = result_source_mismatches(evaluation, obs, evidence)
    if mismatches:
        sources_coherent = False
        reasons = reasons + sorted({code for codes in mismatches.values() for code in codes})
        unknown['observed_at_utc'] = 'result_sources_mismatched'
        unknown['site'] = 'result_sources_mismatched'
    points = () if evidence is None else evidence.forecast_points
    locations = {(p.requested_location.latitude, p.requested_location.longitude) for p in points}
    site = None
    if sources_coherent and len(locations) == 1:
        lat, lon = next(iter(locations))
        site = {'latitude': lat, 'longitude': lon}
    elif sources_coherent:
        unknown['site'] = 'evidence_missing_or_empty' if not locations else 'incoherent_requested_coordinates'
    if site is None and sources_coherent:
        reasons = reasons + [unknown['site']]
    context = dict.fromkeys(('site_name', 'target', 'catalog_key', 'imaging_field_id', 'acquisition_intent_id', 'mission_id'))
    execution_id = comparison['execution_id']
    execution = snapshot.executions.get(execution_id)
    decision = snapshot.decisions.get(comparison['decision_id'])
    if execution and decision:
        mission = next((m for m in decision.missions if m.mission_id == execution.execution.mission_id), None)
        selection = next((s for s in decision.selections if mission and s.selection_id == mission.selection_id), None)
        if (mission and selection and mission.decision_id == comparison['decision_id'] and
                selection.decision_id == comparison['decision_id']):
            for key in ('site_name', 'target', 'imaging_field_id', 'acquisition_intent_id', 'mission_id'):
                context[key] = getattr(mission, key)
            context['catalog_key'] = selection.selected_catalog_key
        else:
            unknown['context'] = 'canonical_context_incoherent_or_missing'
    else:
        unknown['context'] = 'decision_only_context_unavailable' if not execution_id else 'canonical_context_missing'
    for key, value in context.items():
        if value is None:
            unknown[key] = unknown.get('context', 'canonical_dimension_missing')
    providers = set()
    for result in comparison['results']:
        point = result['forecast_point']
        provider = point['provider_id'] if result['status'] == 'comparable' and point else None
        result['compared_provider'] = provider
        result['unknown_dimensions'] = {}
        for code in mismatches.get(result['variable'], []):
            result['unknown_dimensions']['source'] = code
        if 'outcome_history_forecast_source_mismatch' in mismatches.get(result['variable'], []):
            provider = None
            result['compared_provider'] = None
            result['unknown_dimensions']['provider'] = 'outcome_history_forecast_source_mismatch'
        if provider:
            providers.add(provider)
        else:
            result['unknown_dimensions'].setdefault('provider', 'result_not_comparable')
        if not point or point['model_id'] is None:
            result['unknown_dimensions']['model'] = 'model_not_recorded'
    if not providers:
        unknown['compared_provider'] = 'no_comparable_result'
    if obs is None:
        unknown['observed_at_utc'] = 'observation_missing_or_corrupt'
    compatible = admissible(evaluation)
    return {**raw, **comparison, 'observed_at_utc': obs.observed_at_utc.isoformat() if obs and sources_coherent else None,
            'mode': 'execution' if execution_id else 'decision_only', 'site': site, 'context': context,
            'compared_providers': sorted(providers), 'evidence_providers': sorted({p.provider_id for p in points}),
            'supersession': state, 'lineage_reasons': reasons, 'unknown_dimensions': unknown,
            'admissible': compatible, 'sources_coherent': sources_coherent,
            'statistics_eligible': compatible and state == 'active' and sources_coherent and site is not None,
            'exclusion_reasons': ([] if compatible else ['incompatible_version_or_policy']) + reasons +
                                 (['superseded'] if state == 'superseded' else [])}


class OutcomeHistoryService:
    def __init__(self, reader):
        self.reader = reader

    def history(self, *, cursor=None, **kwargs):
        selected = filters(**kwargs)
        snapshot = self.reader.read()
        if not snapshot.stable:
            raise OutcomeHistoryDatasetChanged('outcome_history_dataset_changed')
        diagnostics = list(snapshot.diagnostics)
        states = lineage_states(snapshot.observations)
        # The snapshot reader reconstructs local evidence objects; projection does
        # not mutate them. Keep strong source references only for this call.
        inspection_cache = _EvidenceInspectionCache()
        rows = [_project(e, snapshot, states, inspection_cache) for e in snapshot.evaluations]
        counts = Counter(r['observation_id'] for r in rows if r['admissible'])
        missing_context = False
        for row in rows:
            if row['execution_id'] and 'context' in row['unknown_dimensions']:
                missing_context = True
                diagnostics.append({'code': row['unknown_dimensions']['context'],
                                    'observation_id': row['observation_id'], 'evaluation_id': row['evaluation_id']})
            if counts[row['observation_id']] > 1:
                row['statistics_eligible'] = False
                row['exclusion_reasons'].append('duplicate_admissible_evaluations')
            for code in row['exclusion_reasons']:
                diagnostics.append({'code': code, 'observation_id': row['observation_id'], 'evaluation_id': row['evaluation_id']})
            if row['observed_at_utc'] is None and (selected['observed_from'] or selected['observed_to']):
                diagnostics.append({'code': 'unknown_observed_date_excluded', 'observation_id': row['observation_id']})

        def matches(row):
            date = row['observed_at_utc']
            if selected['observed_from'] or selected['observed_to']:
                if date is None:
                    return False
                instant = datetime.fromisoformat(date)
                if selected['observed_from'] and instant < datetime.fromisoformat(selected['observed_from']):
                    return False
                if selected['observed_to'] and instant > datetime.fromisoformat(selected['observed_to']):
                    return False
            if not selected['include_superseded'] and row['supersession'] == 'superseded':
                return False
            if selected['latitude'] is not None and row['site'] != {'latitude': selected['latitude'], 'longitude': selected['longitude']}:
                return False
            for field in ('mode', 'status'):
                if selected[field] and row[field] != selected[field]:
                    return False
            results = [v for v in row['results'] if not selected['variable'] or v['variable'] == selected['variable']]
            if selected['variable'] and not results:
                return False
            if selected['provider'] and not any(v['compared_provider'] == selected['provider'] for v in results):
                return False
            return True

        filtered = [r for r in rows if matches(r)]
        # Unknown dates last; never substitute computed_at.
        filtered.sort(key=lambda r: (-(datetime.fromisoformat(r['observed_at_utc']).timestamp()) if r['observed_at_utc'] else math.inf,
                                     r['observation_id'], r['evaluation_id']))
        view = hashlib.sha256(json.dumps({'policy': POLICY, 'filters': selected, 'dataset': snapshot.fingerprint},
                            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        offset = 0
        if cursor:
            try:
                if len(cursor) > 2048:
                    raise ValueError()
                token = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
                if (set(token) != {'dataset', 'view', 'offset'} or type(token['offset']) is not int or token['offset'] < 0 or
                        any(type(token[key]) is not str or len(token[key]) != 64 or
                            any(c not in '0123456789abcdef' for c in token[key]) for key in ('dataset', 'view'))):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError):
                raise OutcomeHistoryInvalidFilter('invalid_outcome_history_cursor') from None
            if token['dataset'] != snapshot.fingerprint:
                raise OutcomeHistoryDatasetChanged('outcome_history_dataset_changed')
            if token['view'] != view or token['offset'] > len(filtered):
                raise OutcomeHistoryInvalidFilter('invalid_outcome_history_cursor')
            offset = token['offset']
        end = offset + selected['limit']
        next_cursor = None
        if snapshot.stable and end < len(filtered):
            next_cursor = base64.urlsafe_b64encode(json.dumps({'dataset': snapshot.fingerprint, 'view': view, 'offset': end},
                separators=(',', ':')).encode()).decode().rstrip('=')
        certified = snapshot.complete and not missing_context and not any(not r['sources_coherent'] or
            r['site'] is None or r['supersession'] == 'indeterminate' or
            'duplicate_admissible_evaluations' in r['exclusion_reasons'] for r in rows)
        computed_statistics = None
        if certified:
            try:
                computed_statistics = statistics([r for r in filtered if r['statistics_eligible']])
            except (OutcomeHistoryStatisticsUnavailable, OverflowError):
                certified = False
                diagnostics.append({'code': 'nonfinite_statistics'})
        projection_complete = snapshot.complete and not missing_context and all(
            r['sources_coherent'] and r['site'] is not None for r in rows)
        return {'rows': filtered[offset:end], 'next_cursor': next_cursor, 'dataset_fingerprint': snapshot.fingerprint,
                'view_token': view, 'statistics': computed_statistics,
                'diagnostics': diagnostics, 'completeness': 'complete' if projection_complete else 'degraded',
                'certification': 'certified' if certified else 'statistics_suspended',
                'readable_filtered_rows': len(filtered), 'policy': POLICY, 'filters': selected}
