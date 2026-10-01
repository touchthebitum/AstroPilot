"""Read projection and population contract for Outcome History v1."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from decision.models.forecast_observation_comparison import ForecastObservationParameters
from decision.outcome_evaluation_persistence import serialize_outcome_evaluation
from decision.services.outcome_history_statistics import UNITS, statistics


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
            while current:
                if current.observation_id in visited:
                    reasons.add('lineage_cycle')
                    break
                visited.add(current.observation_id)
                current = observations.get(current.supersedes_observation_id)
        for node in component & observations.keys():
            states[node] = ('indeterminate' if reasons else 'superseded' if children[node] else 'active', sorted(reasons))
    return states


def admissible(evaluation):
    c = evaluation.comparison
    return (evaluation.evaluation_algorithm_version == 'outcome_evaluation.v1' and
            c.algorithm_version == 'forecast_observation.v1' and c.forecast_scope == 'decision_attached_evidence' and
            c.parameters == ForecastObservationParameters() and
            all(r.unit == UNITS[r.variable.value] for r in c.results))


def project(evaluation, snapshot, states):
    raw = json.loads(serialize_outcome_evaluation(evaluation))['outcome_evaluation']
    comparison = raw.pop('comparison')
    observation_id = comparison['observation_id']
    obs = snapshot.observations.get(observation_id)
    unknown = {}
    state, reasons = states.get(observation_id, ('indeterminate', ['observation_missing']))
    if obs is not None and (obs.decision_id != comparison['decision_id'] or obs.execution_id != comparison['execution_id']):
        state, reasons = 'indeterminate', reasons + ['evaluation_observation_lineage_mismatch']
    evidence = snapshot.evidence.get(comparison['decision_id'])
    points = () if evidence is None else evidence.forecast_points
    locations = {(p.requested_location.latitude, p.requested_location.longitude) for p in points}
    site = None
    if len(locations) == 1:
        lat, lon = next(iter(locations))
        site = {'latitude': lat, 'longitude': lon}
    else:
        unknown['site'] = 'evidence_missing_or_empty' if not locations else 'incoherent_requested_coordinates'
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
        if provider:
            providers.add(provider)
        else:
            result['unknown_dimensions']['provider'] = 'result_not_comparable'
        if not point or point['model_id'] is None:
            result['unknown_dimensions']['model'] = 'model_not_recorded'
    if not providers:
        unknown['compared_provider'] = 'no_comparable_result'
    if obs is None:
        unknown['observed_at_utc'] = 'observation_missing_or_corrupt'
    compatible = admissible(evaluation)
    return {**raw, **comparison, 'observed_at_utc': obs.observed_at_utc.isoformat() if obs else None,
            'mode': 'execution' if execution_id else 'decision_only', 'site': site, 'context': context,
            'compared_providers': sorted(providers), 'evidence_providers': sorted({p.provider_id for p in points}),
            'supersession': state, 'lineage_reasons': reasons, 'unknown_dimensions': unknown,
            'admissible': compatible, 'statistics_eligible': compatible and state == 'active',
            'exclusion_reasons': ([] if compatible else ['incompatible_version_or_policy']) + reasons +
                                 (['superseded'] if state == 'superseded' else [])}


class OutcomeHistoryService:
    def __init__(self, reader):
        self.reader = reader

    def history(self, *, cursor=None, **kwargs):
        selected = filters(**kwargs)
        snapshot = self.reader.read()
        diagnostics = list(snapshot.diagnostics)
        states = lineage_states(snapshot.observations)
        rows = [project(e, snapshot, states) for e in snapshot.evaluations]
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
        if end < len(filtered):
            next_cursor = base64.urlsafe_b64encode(json.dumps({'dataset': snapshot.fingerprint, 'view': view, 'offset': end},
                separators=(',', ':')).encode()).decode().rstrip('=')
        certified = snapshot.complete and not missing_context and not any(r['supersession'] == 'indeterminate' or
            'duplicate_admissible_evaluations' in r['exclusion_reasons'] for r in rows)
        return {'rows': filtered[offset:end], 'next_cursor': next_cursor, 'dataset_fingerprint': snapshot.fingerprint,
                'view_token': view, 'statistics': statistics([r for r in filtered if r['statistics_eligible']]) if certified else None,
                'diagnostics': diagnostics, 'completeness': 'complete' if snapshot.complete and not missing_context else 'degraded',
                'certification': 'certified' if certified else 'statistics_suspended',
                'readable_filtered_rows': len(filtered), 'policy': POLICY, 'filters': selected}
