import ast
import json
import os
import runpy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from astropilot.app import create_app
from astropilot.outcome_history_reader import FileOutcomeHistoryReader, OutcomeHistoryUnavailable
from decision.field_observation import CloudState, ObservedConditions
from decision.field_observation_persistence import serialize_field_observation
from decision.models.forecast_observation_comparison import ForecastObservationParameters, TemporalComparisonPolicy
from decision.models.outcome_evaluation import derive_outcome_evaluation_id
from decision.outcome_evaluation_persistence import serialize_outcome_evaluation
from decision.services.outcome_history import OutcomeHistoryService, OutcomeHistoryDatasetChanged, filters, lineage_states
from decision.services.outcome_history_statistics import statistics
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import serialize_decision_forecast_evidence
from decision.weather.provider_reliability import WeatherLocation, WeatherVariable

ROOT = Path(__file__).parents[2]
B = runpy.run_path(str(ROOT / 'tests/architecture/test_outcome_evaluation_orchestration_contract.py'))
URL = '/v1/outcome-evaluations/history'


def write(root, kind, identity, document):
    directory = root / kind
    directory.mkdir(exist_ok=True)
    (directory / (identity + '.json')).write_text(document)


def seed(root, identity='observation-1', *, source=None, evidence=None):
    source = source or B['observation'](observation_id=identity, execution_id=None)
    evidence = evidence or B['evidence'](WeatherVariable.TEMPERATURE_C)
    orchestration = B['service'](root / ('build-' + identity), source, B['MutableEvidenceStore'](evidence))
    evaluation = orchestration.evaluate(identity).evaluation
    write(root, 'outcome_evaluations', evaluation.evaluation_id, serialize_outcome_evaluation(evaluation))
    write(root, 'field_observations', identity, serialize_field_observation(source))
    write(root, 'decision_forecast_evidence', source.decision_id, serialize_decision_forecast_evidence(decision_id=source.decision_id, evidence=evidence))
    return evaluation


def client(root):
    service = OutcomeHistoryService(FileOutcomeHistoryReader(root))
    return TestClient(create_app(service_factory=lambda: SimpleNamespace(read_outcome_history=service.history)))


def test_statistics_signs_mae_n0_partial_units_reasons(tmp_path):
    source = B['observation'](execution_id=None, conditions=ObservedConditions(temperature_c=7.0, relative_humidity_percent=55.0))
    seed(tmp_path, source=source)
    result = client(tmp_path).get(URL).json()
    assert result['certification'] == 'certified'
    stats = result['statistics']
    assert stats['n_evaluations'] == stats['n_observations'] == stats['n_decisions'] == 1
    assert stats['n_executions'] == 0
    assert stats['coverage']['partial'] == 1
    assert stats['variables']['temperature_c']['mean_signed_error'] == 1
    assert stats['variables']['temperature_c']['mean_absolute_error'] == 1
    assert stats['variables']['relative_humidity_percent']['n_not_comparable'] == 1
    assert stats['variables']['wind_speed_kmh']['n_absent'] == 1
    assert stats['variables']['relative_humidity_percent']['error_unit'] == 'percentage_points'
    row = result['rows'][0]
    row['results'][0]['signed_error'] = -3.0
    row['results'][0]['absolute_error'] = 3.0
    row['reasons'] = [{'code': 'same'}, {'code': 'same'}]
    row['results'][1]['reasons'] = [{'code': 'same'}]
    values = statistics([row])
    assert values['reason_observation_counts'] == {'same': 1}
    assert values['variables']['temperature_c']['mean_signed_error'] == -3
    assert values['variables']['temperature_c']['mean_absolute_error'] == 3
    zero = statistics([])
    assert zero['n_evaluations'] == 0
    assert zero['variables']['temperature_c']['mean_signed_error'] is None


def test_cloud_matrix_and_humidity_wind(tmp_path):
    source = B['observation'](execution_id=None, conditions=ObservedConditions(cloud_state=CloudState.OVERCAST,
        relative_humidity_percent=55.0, wind_speed_kmh=12.0))
    seed(tmp_path, source=source, evidence=B['evidence'](WeatherVariable.CLOUD_COVER_PERCENT,
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT, WeatherVariable.WIND_SPEED_KMH))
    stats = client(tmp_path).get(URL).json()['statistics']
    assert stats['clouds'] == {'n': 1, 'forecast_x_observed': {'few': {'overcast': 1}}, 'match': 0, 'mismatch': 1}
    assert stats['variables']['relative_humidity_percent']['mean_signed_error'] == 5
    assert stats['variables']['wind_speed_kmh']['mean_signed_error'] == -2
    assert stats['variables']['wind_speed_kmh']['unit'] == 'km/h'


def test_provenance_exact_multi_provider_missing_model(tmp_path):
    evidence = B['evidence'](WeatherVariable.TEMPERATURE_C)
    evidence = DecisionForecastEvidence((replace(evidence.forecast_points[0], model_id=None),
        replace(evidence.forecast_points[0], provider_id='other', forecast_for_utc=B['OBSERVED_AT'] + timedelta(minutes=20))))
    seed(tmp_path, evidence=evidence)
    c = client(tmp_path)
    row = c.get(URL).json()['rows'][0]
    assert row['compared_providers'] == ['provider']
    assert row['evidence_providers'] == ['other', 'provider']
    assert row['results'][0]['unknown_dimensions']['model'] == 'model_not_recorded'
    assert row['context']['target'] is None
    assert row['unknown_dimensions']['context'] == 'decision_only_context_unavailable'
    assert c.get(URL, params={'latitude': 46.75, 'longitude': 6.55}).json()['readable_filtered_rows'] == 1
    assert c.get(URL, params={'latitude': 46.750001, 'longitude': 6.55}).json()['readable_filtered_rows'] == 0
    assert c.get(URL, params={'provider': 'other'}).json()['readable_filtered_rows'] == 0
    bad = DecisionForecastEvidence((evidence.forecast_points[0], replace(evidence.forecast_points[1], requested_location=WeatherLocation(46.751, 6.55))))
    write(tmp_path, 'decision_forecast_evidence', 'decision-1', serialize_decision_forecast_evidence(decision_id='decision-1', evidence=bad))
    row = c.get(URL).json()['rows'][0]
    assert row['site'] is None and row['unknown_dimensions']['site'] == 'comparison_sources_unknown_or_mismatched'


def test_noncomparable_provider_unknown(tmp_path):
    seed(tmp_path, evidence=B['evidence'](WeatherVariable.WIND_SPEED_KMH))
    row = client(tmp_path).get(URL).json()['rows'][0]
    assert row['compared_providers'] == [] and row['evidence_providers'] == ['provider']
    assert row['results'][0]['compared_provider'] is None


def test_superseded_child_outside_filter_without_outcome(tmp_path):
    seed(tmp_path)
    child = B['observation'](observation_id='child', execution_id=None, supersedes_observation_id='observation-1',
        observed_at_utc=B['OBSERVED_AT'] + timedelta(days=5), recorded_at_utc=B['OBSERVED_AT'] + timedelta(days=5, minutes=1))
    write(tmp_path, 'field_observations', 'child', serialize_field_observation(child))
    c = client(tmp_path)
    assert c.get(URL).json()['rows'] == []
    result = c.get(URL, params={'include_superseded': True, 'observed_to': B['OBSERVED_AT'].isoformat()}).json()
    assert result['rows'][0]['supersession'] == 'superseded'
    assert result['statistics']['n_evaluations'] == 0


@pytest.mark.parametrize('kind', ['chain', 'cycle', 'fork', 'missing_parent', 'decision', 'execution'])
def test_lineage_components(kind):
    a = B['observation'](observation_id='a', execution_id=None)
    b = B['observation'](observation_id='b', execution_id=None, supersedes_observation_id='a')
    items = {'a': a, 'b': b}
    if kind == 'chain':
        items['c'] = replace(b, observation_id='c', supersedes_observation_id='b')
    if kind == 'cycle': items['a'] = replace(a, supersedes_observation_id='b')
    if kind == 'fork': items['c'] = replace(b, observation_id='c')
    if kind == 'missing_parent': del items['a']
    if kind == 'decision': items['b'] = replace(b, decision_id='other')
    if kind == 'execution': items['b'] = replace(b, execution_id='exec')
    states = lineage_states(items)
    if kind == 'chain':
        assert states['a'][0] == states['b'][0] == 'superseded' and states['c'][0] == 'active'
    else:
        assert all(state[0] == 'indeterminate' for state in states.values())


@pytest.mark.parametrize('version', ['v2', 'policy', 'duplicate'])
def test_versions_and_duplicates(tmp_path, version):
    evaluation = seed(tmp_path)
    if version == 'v2':
        changed = replace(evaluation, evaluation_algorithm_version='outcome_evaluation.v2', evaluation_id=derive_outcome_evaluation_id(
            comparison_id=evaluation.comparison.comparison_id, evaluation_algorithm_version='outcome_evaluation.v2'))
    else:
        comparison = replace(evaluation.comparison, comparison_id='a' * 64,
            parameters=ForecastObservationParameters(temporal_policy=TemporalComparisonPolicy(maximum_absolute_offset=timedelta(minutes=20))) if version == 'policy' else evaluation.comparison.parameters)
        changed = replace(evaluation, comparison=comparison, evaluation_id=derive_outcome_evaluation_id(comparison_id=comparison.comparison_id))
    write(tmp_path, 'outcome_evaluations', changed.evaluation_id, serialize_outcome_evaluation(changed))
    result = client(tmp_path).get(URL).json()
    assert len(result['rows']) == 2
    if version == 'duplicate':
        assert result['statistics'] is None and any(d['code'] == 'duplicate_admissible_evaluations' for d in result['diagnostics'])
    else:
        assert result['statistics']['n_evaluations'] == 1
        assert any(d['code'] == 'incompatible_version_or_policy' for d in result['diagnostics'])


@pytest.mark.parametrize('kind', ['outcome_evaluations', 'field_observations', 'decision_forecast_evidence'])
def test_corruption_degraded_best_effort(tmp_path, kind):
    seed(tmp_path)
    identity = 'bad' if kind != 'decision_forecast_evidence' else 'decision-1'
    write(tmp_path, kind, identity, '{broken')
    result = client(tmp_path).get(URL)
    assert result.status_code == 200
    value = result.json()
    assert len(value['rows']) == 1 and value['statistics'] is None
    assert value['completeness'] == 'degraded'
    assert any(d['code'] == 'corrupt_document' for d in value['diagnostics'])


def test_missing_observation_unknown_date_never_computed_at(tmp_path):
    seed(tmp_path)
    (tmp_path / 'field_observations/observation-1.json').unlink()
    c = client(tmp_path)
    value = c.get(URL).json()
    assert value['rows'][0]['observed_at_utc'] is None and value['statistics'] is None
    value = c.get(URL, params={'observed_from': '2020-01-01T00:00:00Z'}).json()
    assert value['rows'] == [] and any(d['code'] == 'unknown_observed_date_excluded' for d in value['diagnostics'])


def test_missing_join_and_global_unavailable(tmp_path, monkeypatch):
    seed(tmp_path)
    (tmp_path / 'decision_forecast_evidence/decision-1.json').unlink()
    c = client(tmp_path)
    assert c.get(URL).json()['statistics'] is None
    original = FileOutcomeHistoryReader._directory_fd
    def blocked(self, path):
        if Path(path).name == 'outcome_evaluations': raise PermissionError()
        return original(self, path)
    monkeypatch.setattr(FileOutcomeHistoryReader, '_directory_fd', blocked)
    response = c.get(URL)
    assert response.status_code == 503 and response.json()['detail']['code'] == 'outcome_history_unavailable'


@pytest.mark.parametrize('params', [dict(limit=0), dict(limit=101), dict(latitude=46), dict(latitude='nan', longitude=0),
    dict(mode='night'), dict(variable='dew_point_c'), dict(status='sufficient'), dict(provider=' '),
    dict(observed_from='2026-01-01'), dict(observed_from='2026-01-01T00:00:00+01:00'),
    dict(observed_from='2026-01-02T00:00:00Z', observed_to='2026-01-01T00:00:00Z'), dict(cursor='bad'), dict(limit='x')])
def test_invalid_filters(tmp_path, params):
    assert client(tmp_path).get(URL, params=params).status_code == 422


def test_tie_sort_pages_stats_and_dataset_change(tmp_path):
    for identity in ['z', 'a', 'm']: seed(tmp_path, identity)
    c = client(tmp_path)
    page = c.get(URL, params={'limit': 1}).json()
    assert page['rows'][0]['observation_id'] == 'a'
    assert page['statistics']['n_evaluations'] == 3
    page2 = c.get(URL, params={'limit': 1, 'cursor': page['next_cursor']}).json()
    assert page2['rows'][0]['observation_id'] == 'm'
    assert c.get(URL, params={'limit': 2, 'cursor': page['next_cursor']}).status_code == 422
    assert c.get(URL, params={'limit': 1, 'mode': 'execution', 'cursor': page['next_cursor']}).status_code == 422
    path = tmp_path / 'field_observations/z.json'
    path.write_text(path.read_text() + ' ')
    response = c.get(URL, params={'limit': 1, 'cursor': page['next_cursor']})
    assert response.status_code == 409 and response.json()['detail']['code'] == 'outcome_history_dataset_changed'


def test_read_only_nonwritable_no_created_files(tmp_path, monkeypatch):
    seed(tmp_path)
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    for directory in ['outcome_evaluations', 'field_observations', 'decision_forecast_evidence']:
        (tmp_path / directory).chmod(0o555)
    # Any attempt to create or acquire a writer lock fails the test.
    import astropilot.file_lock as locks
    monkeypatch.setattr(locks, 'exclusive_file_lock', lambda *_: pytest.fail('writer lock'))
    try:
        assert client(tmp_path).get(URL).json()['certification'] == 'certified'
        after = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
        assert before == after
    finally:
        for directory in ['outcome_evaluations', 'field_observations', 'decision_forecast_evidence']:
            (tmp_path / directory).chmod(0o755)


def test_unstable_scan_suspends_statistics(tmp_path, monkeypatch):
    seed(tmp_path)
    reader = FileOutcomeHistoryReader(tmp_path)
    original = reader._inventory
    counts = {}
    def inventory(kind):
        counts[kind] = counts.get(kind, 0) + 1
        if kind == 'field_observations' and counts[kind] == 2:
            write(tmp_path, kind, 'child', serialize_field_observation(B['observation'](observation_id='child', execution_id=None, supersedes_observation_id='observation-1')))
        return original(kind)
    monkeypatch.setattr(reader, '_inventory', inventory)
    with pytest.raises(OutcomeHistoryDatasetChanged):
        OutcomeHistoryService(reader).history()


def test_architecture_no_commands_or_forbidden_dependencies():
    for name in ['astropilot/outcome_history_reader.py', 'decision/services/outcome_history.py', 'decision/services/outcome_history_statistics.py']:
        tree = ast.parse((ROOT / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(word in (node.module or '') for word in ('scoring', 'recommendation', 'learning', 'calibration', 'provider_selection', 'orchestration'))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ('save', 'evaluate', 'mkdir', 'write_text', 'write_bytes', 'unlink')


def seed_execution_joins(root):
    from decision.acceptance_lineage_persistence import DecisionAcceptanceAggregate, serialize_decision_acceptance_aggregate
    from decision.execution_lineage_persistence import ExecutionLineageAggregate, serialize_execution_lineage_aggregate
    acceptance = runpy.run_path(str(ROOT / 'tests/architecture/test_decision_acceptance_lineage_persistence.py'))
    execution = runpy.run_path(str(ROOT / 'tests/architecture/test_execution_lineage_persistence.py'))
    aggregate = DecisionAcceptanceAggregate(context=acceptance['context'](), selections=(acceptance['selection'](),), missions=(acceptance['mission'](),))
    write(root, 'decision_lineage', 'decision-1', serialize_decision_acceptance_aggregate(aggregate))
    write(root, 'execution_lineage', 'execution-1', serialize_execution_lineage_aggregate(ExecutionLineageAggregate(execution['execution']())))


def test_execution_canonical_context_and_join_fingerprint(tmp_path):
    seed(tmp_path, source=B['observation']())
    seed_execution_joins(tmp_path)
    c = client(tmp_path)
    result = c.get(URL).json()
    assert result['certification'] == 'certified'
    row = result['rows'][0]
    assert row['mode'] == 'execution' and row['assessment'] is not None
    assert row['context']['site_name'] == 'Mont Sujet'
    assert row['context']['target'] == 'Andromeda Galaxy'
    assert row['context']['catalog_key'] == 'M31'
    assert result['statistics']['n_executions'] == 1
    before = result['dataset_fingerprint']
    path = tmp_path / 'execution_lineage/execution-1.json'
    path.write_text(path.read_text() + ' ')
    assert c.get(URL).json()['dataset_fingerprint'] != before
    write(tmp_path, 'decision_lineage', 'unrelated', '{broken')
    # No global search over foreign mission/selection documents.
    assert c.get(URL).json()['certification'] == 'certified'
    path.write_text('{broken')
    result = c.get(URL).json()
    assert result['statistics'] is None and result['rows'][0]['context']['target'] is None


def test_facade_does_not_evaluate_or_save(tmp_path, monkeypatch):
    from decision.services.durable_tonight_application_service import DurableTonightApplicationService
    seed(tmp_path)
    reader_service = OutcomeHistoryService(FileOutcomeHistoryReader(tmp_path))
    forbidden = lambda *args, **kwargs: pytest.fail('write or evaluate')
    app = DurableTonightApplicationService(application_service=SimpleNamespace(evaluate=forbidden),
        evidence_store=SimpleNamespace(save=forbidden), decision_id_factory=forbidden,
        field_observation_store=SimpleNamespace(save=forbidden, load=forbidden),
        outcome_evaluation_store=SimpleNamespace(save=forbidden), outcome_history_service=reader_service)
    app.evaluate_outcome_observation = forbidden
    assert app.read_outcome_history()['statistics']['n_evaluations'] == 1


def test_root_v2_excluded_diagnostic_and_newest_never_selected(tmp_path):
    evaluation = seed(tmp_path)
    payload = json.loads(serialize_outcome_evaluation(evaluation))
    payload['schema_version'] = 2
    payload['domain_version'] = 'outcome_evaluation.v2'
    write(tmp_path, 'outcome_evaluations', 'future', json.dumps(payload))
    result = client(tmp_path).get(URL).json()
    assert len(result['rows']) == result['statistics']['n_evaluations'] == 1
    assert any(d['code'] == 'incompatible_version' for d in result['diagnostics'])


def test_observation_inconsistent_evaluation_link_suspends(tmp_path):
    seed(tmp_path)
    write(tmp_path, 'field_observations', 'observation-1', serialize_field_observation(B['observation'](execution_id='other')))
    result = client(tmp_path).get(URL).json()
    assert result['statistics'] is None
    assert result['rows'][0]['supersession'] == 'indeterminate'
    assert 'evaluation_observation_lineage_mismatch' in result['rows'][0]['lineage_reasons']


def test_execution_missing_canonical_mission_is_diagnostic(tmp_path):
    seed(tmp_path, source=B['observation']())
    seed_execution_joins(tmp_path)
    from decision.acceptance_lineage_persistence import deserialize_decision_acceptance_aggregate, serialize_decision_acceptance_aggregate
    path = tmp_path / 'decision_lineage/decision-1.json'
    aggregate = deserialize_decision_acceptance_aggregate(path.read_text())
    path.write_text(serialize_decision_acceptance_aggregate(replace(aggregate, missions=())))
    result = client(tmp_path).get(URL).json()
    assert result['statistics'] is None and result['completeness'] == 'degraded'
    assert any(d['code'] == 'canonical_context_incoherent_or_missing' for d in result['diagnostics'])


def test_cloud_match_and_numeric_n2(tmp_path):
    seed(tmp_path, source=B['observation'](execution_id=None, conditions=ObservedConditions(cloud_state=CloudState.FEW, temperature_c=7.0)),
        evidence=B['evidence'](WeatherVariable.CLOUD_COVER_PERCENT, WeatherVariable.TEMPERATURE_C))
    seed(tmp_path, 'second', source=B['observation'](observation_id='second', execution_id=None,
        conditions=ObservedConditions(cloud_state=CloudState.FEW, temperature_c=11.0)),
        evidence=B['evidence'](WeatherVariable.CLOUD_COVER_PERCENT, WeatherVariable.TEMPERATURE_C))
    values = client(tmp_path).get(URL).json()['statistics']
    assert values['clouds']['match'] == values['clouds']['n'] == 2
    assert values['variables']['temperature_c']['n_comparable'] == 2
    assert values['variables']['temperature_c']['mean_signed_error'] == -1.0
    assert values['variables']['temperature_c']['mean_absolute_error'] == 2.0


def test_invalid_schema_is_corruption_not_future_version(tmp_path):
    evaluation = seed(tmp_path)
    document = json.loads(serialize_outcome_evaluation(evaluation))
    document['schema_version'] = 'broken'
    write(tmp_path, 'outcome_evaluations', evaluation.evaluation_id, json.dumps(document))
    result = client(tmp_path).get(URL).json()
    assert result['statistics'] is None
    assert any(d['code'] == 'corrupt_document' for d in result['diagnostics'])


def test_default_fifty_and_maximum_hundred_pages(tmp_path):
    import hashlib
    evaluation = seed(tmp_path)
    snapshot = FileOutcomeHistoryReader(tmp_path).read()
    evaluations, observations = [], {}
    for number in range(105):
        identity = f'observation-{number:03}'
        comparison_id = hashlib.sha256(identity.encode()).hexdigest()
        from decision.services.forecast_observation_comparison import _canonical_evidence, _source_digest
        observation = B['observation'](observation_id=identity, execution_id=None)
        digest = _source_digest(_canonical_evidence(snapshot.evidence['decision-1']), observation, identity_persistable=True)
        comparison = replace(evaluation.comparison, comparison_id=comparison_id, observation_id=identity, source_digest=digest)
        evaluations.append(replace(evaluation, comparison=comparison,
            evaluation_id=derive_outcome_evaluation_id(comparison_id=comparison_id)))
        observations[identity] = B['observation'](observation_id=identity, execution_id=None)
    reader = SimpleNamespace(read=lambda: replace(snapshot, evaluations=tuple(evaluations), observations=observations))
    service = OutcomeHistoryService(reader)
    page = service.history()
    assert len(page['rows']) == 50 and page['statistics']['n_evaluations'] == 105
    second = service.history(cursor=page['next_cursor'])
    assert len(second['rows']) == 50
    last = service.history(cursor=second['next_cursor'])
    assert len(last['rows']) == 5 and last['next_cursor'] is None
    assert len(service.history(limit=100)['rows']) == 100


def test_referenced_observation_corrupt_preserves_outcome(tmp_path):
    seed(tmp_path)
    write(tmp_path, 'field_observations', 'observation-1', '{broken')
    value = client(tmp_path).get(URL).json()
    assert value['rows'][0]['observed_at_utc'] is None
    assert value['statistics'] is None and value['completeness'] == 'degraded'
    assert any(d['kind'] == 'field_observations' and d['code'] == 'corrupt_document' for d in value['diagnostics'])


@pytest.mark.parametrize('source_change', ['observation', 'evidence', 'empty_evidence'])
def test_certification_requires_exact_comparison_sources(tmp_path, source_change):
    seed(tmp_path)
    if source_change == 'observation':
        changed = B['observation'](execution_id=None, observed_at_utc=B['OBSERVED_AT'] + timedelta(days=100),
            recorded_at_utc=B['OBSERVED_AT'] + timedelta(days=100, minutes=1),
            conditions=ObservedConditions(temperature_c=99.0))
        write(tmp_path, 'field_observations', 'observation-1', serialize_field_observation(changed))
    else:
        original = B['evidence'](WeatherVariable.TEMPERATURE_C)
        changed = DecisionForecastEvidence(tuple(replace(p, requested_location=WeatherLocation(0, 0))
            for p in original.forecast_points) if source_change == 'evidence' else ())
        write(tmp_path, 'decision_forecast_evidence', 'decision-1',
            serialize_decision_forecast_evidence(decision_id='decision-1', evidence=changed))
    c = client(tmp_path)
    value = c.get(URL).json()
    assert value['statistics'] is None and value['certification'] == 'statistics_suspended'
    assert value['completeness'] == 'degraded'
    row = value['rows'][0]
    assert row['site'] is None and row['observed_at_utc'] is None
    assert row['results'][0]['observed_value'] == 7.0
    assert row['results'][0]['compared_provider'] == ('provider' if source_change == 'evidence' else None)
    assert not row['statistics_eligible'] and not row['sources_coherent']
    assert any(d['code'] == 'comparison_sources_unknown_or_mismatched' for d in value['diagnostics'])
    assert c.get(URL, params={'latitude': 0, 'longitude': 0}).json()['rows'] == []
    assert c.get(URL, params={'observed_from': '2026-12-01T00:00:00Z'}).json()['rows'] == []


def test_unstable_scan_rejects_existing_cursor_and_emits_no_continuation(tmp_path, monkeypatch):
    seed(tmp_path, 'a'); seed(tmp_path, 'b')
    c = client(tmp_path)
    page = c.get(URL, params={'limit': 1}).json()
    original = FileOutcomeHistoryReader._read_bytes
    target = tmp_path / 'field_observations/b.json'
    reads = 0
    def unstable(self, kind, name):
        path = self.directory / kind / name
        nonlocal reads
        if path == target:
            reads += 1
            if reads % 2 == 0:
                return original(self, kind, name) + b' '
        return original(self, kind, name)
    monkeypatch.setattr(FileOutcomeHistoryReader, '_read_bytes', unstable)
    response = c.get(URL, params={'limit': 1, 'cursor': page['next_cursor']})
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'outcome_history_dataset_changed'
    response = c.get(URL, params={'limit': 1})
    assert response.status_code == 409
    assert set(response.json()) == {'detail'}


@pytest.mark.parametrize('field', ['decision_id', 'execution_id'])
@pytest.mark.parametrize('identity', ['invalid\x00id', '../escape', '/absolute', 'sub/path', 'sub\\path'])
def test_join_ids_validated_before_any_path_read(tmp_path, monkeypatch, field, identity):
    evaluation = seed(tmp_path, source=B['observation']()) if field == 'execution_id' else seed(tmp_path)
    comparison = replace(evaluation.comparison, **{field: identity})
    if field == 'execution_id':
        from decision.models.outcome_evaluation import derive_forecast_comparison_outcome_evidence_id
        evidence_id = derive_forecast_comparison_outcome_evidence_id(evaluation_id=evaluation.evaluation_id,
            comparison_id=comparison.comparison_id, decision_id=comparison.decision_id,
            observation_id=comparison.observation_id, execution_id=identity)
        evaluation = replace(evaluation, comparison=comparison,
            outcome_evidence=replace(evaluation.outcome_evidence, execution_id=identity, evidence_id=evidence_id),
            assessment=replace(evaluation.assessment, execution_id=identity, evidence_ids=(evidence_id,),
                findings=tuple(replace(f, evidence_ids=(evidence_id,)) for f in evaluation.assessment.findings)))
    else:
        evaluation = replace(evaluation, comparison=comparison)
    payload = json.loads(serialize_outcome_evaluation(evaluation))
    write(tmp_path, 'outcome_evaluations', evaluation.evaluation_id, json.dumps(payload))
    original = FileOutcomeHistoryReader._read_bytes
    paths = []
    def record(self, kind, name):
        path = self.directory / kind / name
        paths.append(path)
        assert '\x00' not in str(path)
        assert path.is_relative_to(tmp_path)
        assert path.parent.name in ('outcome_evaluations', 'field_observations', 'decision_forecast_evidence',
                                    'execution_lineage', 'decision_lineage')
        assert identity + '.json' != path.name
        return original(self, kind, name)
    monkeypatch.setattr(FileOutcomeHistoryReader, '_read_bytes', record)
    response = client(tmp_path).get(URL)
    assert response.status_code == 200
    value = response.json()
    assert value['completeness'] == 'degraded' and value['statistics'] is None
    assert any(d['code'] == 'invalid_document_identity' for d in value['diagnostics'])
    assert paths


@pytest.mark.parametrize('kind', ['outcome_evaluations', 'field_observations', 'decision_forecast_evidence'])
def test_deeply_nested_corruption_is_isolated(tmp_path, kind):
    seed(tmp_path)
    identity = 'decision-1' if kind == 'decision_forecast_evidence' else 'bad'
    write(tmp_path, kind, identity, '[' * 100000 + ']' * 100000)
    response = client(tmp_path).get(URL)
    assert response.status_code == 200
    value = response.json()
    assert len(value['rows']) == 1 and value['statistics'] is None
    assert value['completeness'] == 'degraded'
    assert any(d['code'] == 'corrupt_document' and d['kind'] == kind for d in value['diagnostics'])


def test_finite_extreme_errors_do_not_overflow_http_means(tmp_path):
    for identity in ('a', 'b'):
        seed(tmp_path, identity, source=B['observation'](observation_id=identity, execution_id=None,
            conditions=ObservedConditions(temperature_c=-1e308)))
    response = client(tmp_path).get(URL)
    assert response.status_code == 200
    value = response.json()
    assert value['certification'] == 'certified' and len(value['rows']) == 2
    stats = value['statistics']['variables']['temperature_c']
    assert stats['n_comparable'] == 2
    assert stats['mean_signed_error'] == stats['mean_absolute_error'] == 1e308
    from decision.services.outcome_history_statistics import finite_mean
    assert finite_mean([1e308, -1e308]) == 0
    assert finite_mean([1e-308, 1e-308]) == 1e-308


def test_lineage_long_chain_has_linear_ancestor_lookups():
    class Counted(dict):
        lookups = 0
        def get(self, key, *args):
            self.lookups += 1
            return super().get(key, *args)
    items = Counted({str(i): B['observation'](observation_id=str(i), execution_id=None,
        supersedes_observation_id=str(i - 1) if i else None) for i in range(6000)})
    states = lineage_states(items)
    assert states['5999'][0] == 'active'
    assert all(states[str(i)][0] == 'superseded' for i in range(5999))
    assert items.lookups < 4 * len(items)
    items['0'] = replace(items['0'], supersedes_observation_id='5999')
    assert all(state[0] == 'indeterminate' for state in lineage_states(items).values())


def test_canonical_source_digest_ignores_evidence_order_and_duplicates(tmp_path):
    evidence = B['evidence'](WeatherVariable.TEMPERATURE_C, WeatherVariable.WIND_SPEED_KMH)
    seed(tmp_path, evidence=evidence)
    changed = DecisionForecastEvidence(tuple(reversed(evidence.forecast_points)) + evidence.forecast_points)
    write(tmp_path, 'decision_forecast_evidence', 'decision-1',
        serialize_decision_forecast_evidence(decision_id='decision-1', evidence=changed))
    value = client(tmp_path).get(URL).json()
    assert value['certification'] == 'certified' and value['rows'][0]['sources_coherent']


def test_coherent_evidence_with_unknown_site_suspends_certification(tmp_path):
    evidence = B['evidence'](WeatherVariable.TEMPERATURE_C, WeatherVariable.WIND_SPEED_KMH)
    changed = DecisionForecastEvidence((evidence.forecast_points[0],
        replace(evidence.forecast_points[0], requested_location=WeatherLocation(0, 0))))
    seed(tmp_path, evidence=changed)
    value = client(tmp_path).get(URL).json()
    assert value['rows'][0]['sources_coherent'] and value['rows'][0]['site'] is None
    assert value['statistics'] is None and value['completeness'] == 'degraded'
    assert any(d['code'] == 'incoherent_requested_coordinates' for d in value['diagnostics'])


@pytest.mark.parametrize('kind,identity', [('field_observations', 'outside-filter'),
    ('decision_forecast_evidence', 'decision-1'), ('outcome_evaluations', 'foreign-corrupt')])
def test_fingerprint_covers_outside_filter_observations_joins_and_corrupt_files(tmp_path, kind, identity):
    seed(tmp_path, 'a'); seed(tmp_path, 'b')
    c = client(tmp_path)
    page = c.get(URL, params={'limit': 1}).json()
    if kind == 'field_observations':
        write(tmp_path, kind, identity, serialize_field_observation(B['observation'](observation_id=identity,
            execution_id=None, supersedes_observation_id='a', observed_at_utc=B['OBSERVED_AT'] + timedelta(days=5),
            recorded_at_utc=B['OBSERVED_AT'] + timedelta(days=5, minutes=1))))
    elif kind == 'decision_forecast_evidence':
        path = tmp_path / kind / (identity + '.json')
        path.write_text(path.read_text() + ' ')
    else:
        write(tmp_path, kind, identity, '{broken')
    response = c.get(URL, params={'limit': 1, 'cursor': page['next_cursor']})
    assert response.status_code == 409
    if kind == 'outcome_evaluations':
        page = c.get(URL, params={'limit': 1}).json()
        (tmp_path / kind / (identity + '.json')).unlink()
        assert c.get(URL, params={'limit': 1, 'cursor': page['next_cursor']}).status_code == 409


def test_statistics_failure_preserves_consultation_with_diagnostic(tmp_path, monkeypatch):
    import decision.services.outcome_history as module
    from decision.services.outcome_history_statistics import OutcomeHistoryStatisticsUnavailable
    seed(tmp_path)
    def unavailable(rows):
        raise OutcomeHistoryStatisticsUnavailable('nonfinite_statistics')
    monkeypatch.setattr(module, 'statistics', unavailable)
    value = client(tmp_path).get(URL).json()
    assert len(value['rows']) == 1 and value['statistics'] is None
    assert value['certification'] == 'statistics_suspended'
    assert any(d['code'] == 'nonfinite_statistics' for d in value['diagnostics'])


@pytest.mark.parametrize('change', ['observed', 'provider', 'forecast', 'model', 'retrieved', 'offset'])
def test_persisted_result_must_match_canonical_sources(tmp_path, change):
    evidence = B['evidence'](WeatherVariable.TEMPERATURE_C, WeatherVariable.WIND_SPEED_KMH)
    evaluation = seed(tmp_path, evidence=evidence,
        source=B['observation'](execution_id=None, conditions=ObservedConditions(temperature_c=7, wind_speed_kmh=3)))
    results = list(evaluation.comparison.results)
    index = next(i for i, r in enumerate(results) if r.variable == WeatherVariable.TEMPERATURE_C)
    result = results[index]
    if change == 'observed':
        result = replace(result, observed_value=99.0, signed_error=-91.0, absolute_error=91.0)
    elif change == 'forecast':
        result = replace(result, forecast_value=9.0, signed_error=2.0, absolute_error=2.0)
    else:
        changes = {'provider': {'provider_id': 'foreign'}, 'model': {'model_id': 'foreign'},
            'retrieved': {'retrieved_at_utc': result.forecast_point.retrieved_at_utc - timedelta(seconds=1)},
            'offset': {'temporal_offset': timedelta(seconds=1)}}
        result = replace(result, forecast_point=replace(result.forecast_point, **changes[change]))
    results[index] = result
    altered = replace(evaluation, comparison=replace(evaluation.comparison, results=tuple(results)))
    write(tmp_path, 'outcome_evaluations', evaluation.evaluation_id, serialize_outcome_evaluation(altered))
    c = client(tmp_path)
    response = c.get(URL)
    assert response.status_code == 200
    value = response.json()
    assert len(value['rows']) == 1 and len(value['rows'][0]['results']) == 2
    assert value['statistics'] is None and value['completeness'] == 'degraded'
    code = 'outcome_history_observed_source_mismatch' if change == 'observed' else 'outcome_history_forecast_source_mismatch'
    assert any(d['code'] == code for d in value['diagnostics'])
    assert c.get(URL, params={'provider': 'foreign'}).json()['certification'] != 'certified'


@pytest.mark.parametrize('mutation', ['child', 'content', 'delete', 'foreign_add', 'foreign_delete'])
@pytest.mark.parametrize('with_cursor', [False, True])
def test_mutation_during_second_evidence_read_is_rejected(tmp_path, monkeypatch, mutation, with_cursor):
    seed(tmp_path, 'a'); seed(tmp_path, 'b')
    foreign = tmp_path / 'field_observations/foreign.json'
    if mutation == 'foreign_delete':
        foreign.write_text('{broken')
    c = client(tmp_path)
    page = c.get(URL, params={'limit': 1}).json()
    original = FileOutcomeHistoryReader._read_bytes
    reads = 0
    def mutate(self, kind, name):
        nonlocal reads
        raw = original(self, kind, name)
        if kind == 'decision_forecast_evidence':
            reads += 1
            if reads == 2:
                path = tmp_path / 'field_observations/a.json'
                if mutation == 'child':
                    write(tmp_path, 'field_observations', 'child', serialize_field_observation(
                        B['observation'](observation_id='child', execution_id=None, supersedes_observation_id='a')))
                elif mutation == 'content':
                    path.write_text(path.read_text() + ' ')
                elif mutation == 'delete':
                    path.unlink()
                elif mutation == 'foreign_add':
                    foreign.write_text('{broken')
                else:
                    foreign.unlink()
        return raw
    monkeypatch.setattr(FileOutcomeHistoryReader, '_read_bytes', mutate)
    params = {'limit': 1}
    if with_cursor:
        params['cursor'] = page['next_cursor']
    response = c.get(URL, params=params)
    assert response.status_code == 409
    assert response.json() == {'detail': {'code': 'outcome_history_dataset_changed'}}


@pytest.mark.parametrize('kind', ['field_observations', 'outcome_evaluations', 'decision_forecast_evidence',
    'execution_lineage', 'decision_lineage'])
@pytest.mark.parametrize('object_type', ['symlink', 'directory', 'fifo'])
def test_unsafe_documents_never_opened(tmp_path, monkeypatch, kind, object_type):
    evaluation = seed(tmp_path, source=B['observation']())
    seed_execution_joins(tmp_path)
    names = {'field_observations': 'observation-1', 'outcome_evaluations': evaluation.evaluation_id,
        'decision_forecast_evidence': 'decision-1', 'execution_lineage': 'execution-1', 'decision_lineage': 'decision-1'}
    path = tmp_path / kind / (names[kind] + '.json')
    external = tmp_path / 'external.json'
    external.write_bytes(path.read_bytes())
    path.unlink()
    if object_type == 'symlink':
        path.symlink_to(external)
    elif object_type == 'directory':
        path.mkdir()
    else:
        os.mkfifo(path)
    original = os.open
    def guarded(name, flags, *args, **kwargs):
        assert str(name) != str(external)
        if 'dir_fd' in kwargs:
            parent = os.fstat(kwargs['dir_fd'])
            target_parent = path.parent.stat()
            if (parent.st_dev, parent.st_ino) == (target_parent.st_dev, target_parent.st_ino):
                assert str(name) != path.name  # rejection must precede document open
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', guarded)
    response = client(tmp_path).get(URL)
    assert response.status_code == 200
    value = response.json()
    assert value['certification'] == 'statistics_suspended' and value['statistics'] is None
    assert any(d['code'] == 'unreadable_document' and d['kind'] == kind for d in value['diagnostics'])


def test_cursor_offset_tampering_cannot_bypass_filters(tmp_path):
    import base64
    seed(tmp_path, 'a'); seed(tmp_path, 'b')
    c = client(tmp_path)
    page = c.get(URL, params={'limit': 1, 'provider': 'provider'}).json()
    token = json.loads(base64.urlsafe_b64decode(page['next_cursor'] + '=='))
    token['offset'] = 0
    cursor = base64.urlsafe_b64encode(json.dumps(token).encode()).decode()
    assert c.get(URL, params={'limit': 1, 'provider': 'foreign', 'cursor': cursor}).status_code == 422
    assert c.get(URL, params={'limit': 1, 'provider': 'provider', 'cursor': cursor}).json()['rows'][0]['observation_id'] == 'a'


def test_change_to_already_rehashed_observation_detected_at_final_membership(tmp_path, monkeypatch):
    seed(tmp_path)
    original = FileOutcomeHistoryReader._read_bytes
    reads = 0
    def mutate(self, kind, name):
        nonlocal reads
        raw = original(self, kind, name)
        if kind == 'decision_forecast_evidence':
            reads += 1
            if reads == 3:  # initial manifest, decode, final hash (observations already hashed)
                path = tmp_path / 'field_observations/observation-1.json'
                path.write_text(path.read_text() + ' ')
        return raw
    monkeypatch.setattr(FileOutcomeHistoryReader, '_read_bytes', mutate)
    assert client(tmp_path).get(URL).status_code == 409


def test_document_replaced_with_symlink_between_stat_and_open(tmp_path, monkeypatch):
    seed(tmp_path)
    target = tmp_path / 'field_observations/observation-1.json'
    external = tmp_path / 'outside.json'
    external.write_bytes(target.read_bytes())
    original = os.open
    swapped = False
    def swap(name, flags, *args, **kwargs):
        nonlocal swapped
        if str(name) == target.name and not swapped:
            swapped = True
            target.unlink()
            target.symlink_to(external)
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', swap)
    response = client(tmp_path).get(URL)
    assert swapped and response.status_code == 409
    # Stable subsequent scan isolates the unsafe document and never loads the observation.
    snapshot = FileOutcomeHistoryReader(tmp_path).read()
    assert not snapshot.observations and not snapshot.complete and snapshot.stable


def test_cloud_observed_category_must_match_source(tmp_path):
    from decision.models.forecast_observation_comparison import CloudComparisonOutcome
    evaluation = seed(tmp_path, evidence=B['evidence'](WeatherVariable.CLOUD_COVER_PERCENT),
        source=B['observation'](execution_id=None, conditions=ObservedConditions(cloud_state=CloudState.FEW)))
    result = evaluation.comparison.results[0]
    changed = replace(result, observed_condition=CloudState.OVERCAST,
        confusion_cell=(result.predicted_condition, CloudState.OVERCAST), outcome=CloudComparisonOutcome.MISMATCH)
    altered = replace(evaluation, comparison=replace(evaluation.comparison, results=(changed,)))
    write(tmp_path, 'outcome_evaluations', evaluation.evaluation_id, serialize_outcome_evaluation(altered))
    value = client(tmp_path).get(URL).json()
    assert value['statistics'] is None
    assert any(d['code'] == 'outcome_history_observed_source_mismatch' for d in value['diagnostics'])


def persist_altered(root, evaluation, comparison):
    write(root, 'outcome_evaluations', evaluation.evaluation_id,
          serialize_outcome_evaluation(replace(evaluation, comparison=comparison)))


def assert_suspended(root, code):
    response = client(root).get(URL)
    assert response.status_code == 200
    value = response.json()
    assert len(value['rows']) == 1 and value['statistics'] is None
    assert value['certification'] == 'statistics_suspended' and value['completeness'] == 'degraded'
    assert any(d['code'] == code for d in value['diagnostics'])


def test_cloud_predicted_category_source_mismatch(tmp_path):
    from decision.models.forecast_observation_comparison import CloudComparisonOutcome
    evaluation = seed(tmp_path, evidence=B['evidence'](WeatherVariable.CLOUD_COVER_PERCENT),
        source=B['observation'](execution_id=None, conditions=ObservedConditions(cloud_state=CloudState.FEW)))
    changed = replace(evaluation.comparison.results[0], predicted_condition=CloudState.OVERCAST,
        confusion_cell=(CloudState.OVERCAST, CloudState.FEW), outcome=CloudComparisonOutcome.MISMATCH)
    persist_altered(tmp_path, evaluation, replace(evaluation.comparison, results=(changed,)))
    assert_suspended(tmp_path, 'outcome_history_cloud_category_source_mismatch')


@pytest.mark.parametrize('percent', [101.0, -0.1])
@pytest.mark.parametrize('mixed', [False, True])
@pytest.mark.parametrize('transport', ['service', 'api'])
def test_cloud_out_of_range_degrades_without_losing_rows(tmp_path, monkeypatch, percent, mixed, transport):
    evaluation = seed(tmp_path, evidence=B['evidence'](WeatherVariable.CLOUD_COVER_PERCENT),
        source=B['observation'](execution_id=None, conditions=ObservedConditions(cloud_state=CloudState.FEW)))
    changed = replace(evaluation.comparison.results[0], forecast_coverage_percent=percent)
    persist_altered(tmp_path, evaluation, replace(evaluation.comparison, results=(changed,)))
    valid = seed(tmp_path, identity='valid') if mixed else None
    monkeypatch.setattr('decision.services.outcome_history.map_cloud_cover_to_condition',
                        lambda *_: pytest.fail('mapper called before domain validation'))
    if transport == 'api':
        response = client(tmp_path).get(URL)
        assert response.status_code == 200
        value = response.json()
    else:
        value = OutcomeHistoryService(FileOutcomeHistoryReader(tmp_path)).history()
    assert value['completeness'] == 'degraded'
    assert value['certification'] == 'statistics_suspended'
    assert value['statistics'] is None
    assert len(value['rows']) == (2 if mixed else 1)
    assert any(d['code'] == 'outcome_history_cloud_coverage_out_of_range' for d in value['diagnostics'])
    corrupt = next(r for r in value['rows'] if r['evaluation_id'] == evaluation.evaluation_id)
    assert not corrupt['sources_coherent']
    assert corrupt['results'][0]['forecast_coverage_percent'] == percent
    if valid:
        assert next(r for r in value['rows'] if r['evaluation_id'] == valid.evaluation_id)['sources_coherent']


@pytest.mark.parametrize('percent,category', [(0.0, 'clear'), (100.0, 'overcast')] + [(b + d, c) for b, low, high in
    [(10, 'clear', 'few'), (25, 'few', 'partly_cloudy'),
     (50, 'partly_cloudy', 'mostly_cloudy'), (80, 'mostly_cloudy', 'overcast')]
    for d, c in [(-0.000001, low), (0, high), (0.000001, high)]])
def test_cloud_thresholds_certified(tmp_path, percent, category):
    evidence = B['evidence'](WeatherVariable.CLOUD_COVER_PERCENT)
    point = evidence.forecast_points[0]
    evidence = DecisionForecastEvidence((replace(point, values=(replace(point.values[0], value=percent),)),))
    seed(tmp_path, evidence=evidence,
         source=B['observation'](execution_id=None, conditions=ObservedConditions(cloud_state=CloudState.FEW)))
    value = client(tmp_path).get(URL).json()
    assert value['certification'] == 'certified'
    assert value['rows'][0]['results'][0]['predicted_condition'] == category


def test_noncomparable_cloud_without_percent(tmp_path):
    seed(tmp_path, evidence=B['evidence'](WeatherVariable.TEMPERATURE_C),
         source=B['observation'](execution_id=None, conditions=ObservedConditions(cloud_state=CloudState.FEW)))
    value = client(tmp_path).get(URL).json()
    assert value['certification'] == 'certified'
    result = value['rows'][0]['results'][0]
    assert result['forecast_coverage_percent'] is None and result['status'] == 'not_comparable'


@pytest.mark.parametrize('field', ['source_id', 'confidence', 'quality_flags', 'flags_order', 'capture_method', 'source_type', 'exact'])
def test_observation_provenance_source_match(tmp_path, field):
    from decision.field_observation import QualityFlag, Confidence, CaptureMethod, ObservationSourceType
    source = B['observation'](execution_id=None)
    source = replace(source, quality=replace(source.quality, flags=(QualityFlag.ESTIMATED, QualityFlag.PARTIAL)))
    evaluation = seed(tmp_path, source=source)
    changes = {'source_id': {'source_id': 'foreign-sensor'}, 'confidence': {'confidence': Confidence.LOW},
        'quality_flags': {'quality_flags': (QualityFlag.IMPORTED,)},
        'flags_order': {'quality_flags': tuple(reversed(source.quality.flags))},
        'capture_method': {'capture_method': CaptureMethod.MANUAL},
        'source_type': {'source_type': ObservationSourceType.USER}, 'exact': {}}
    provenance = replace(evaluation.comparison.observation_provenance, **changes[field])
    persist_altered(tmp_path, evaluation, replace(evaluation.comparison, observation_provenance=provenance))
    if field == 'exact':
        assert client(tmp_path).get(URL).json()['certification'] == 'certified'
    else:
        assert_suspended(tmp_path, 'outcome_history_observation_provenance_mismatch')


@pytest.mark.parametrize('offset_us,stored_delta,certified', [
    (3600000000, 0, False), (1800000000, 0, True), (-1800000000, 0, True),
    (1800000001, 0, False), (0, 1, False)])
def test_temporal_policy_source_match(tmp_path, offset_us, stored_delta, certified):
    evidence = B['evidence'](WeatherVariable.TEMPERATURE_C)
    point = evidence.forecast_points[0]
    evidence = DecisionForecastEvidence((replace(point, forecast_for_utc=B['OBSERVED_AT'] + timedelta(microseconds=offset_us)),))
    # Build a comparable result inside the window, then persist the canonical out-of-window point.
    evaluation = seed(tmp_path)
    write(tmp_path, 'decision_forecast_evidence', 'decision-1',
          serialize_decision_forecast_evidence(decision_id='decision-1', evidence=evidence))
    from decision.services.forecast_observation_comparison import _inspect_evidence, _source_digest, _validated_field_observation
    _, canonical = _inspect_evidence(evidence)
    source = B['observation'](execution_id=None)
    digest = _source_digest(canonical, _validated_field_observation(source), identity_persistable=True)
    result = evaluation.comparison.results[0]
    result = replace(result, forecast_point=replace(result.forecast_point,
        forecast_for_utc=evidence.forecast_points[0].forecast_for_utc,
        temporal_offset=timedelta(microseconds=offset_us + stored_delta)))
    persist_altered(tmp_path, evaluation, replace(evaluation.comparison, source_digest=digest, results=(result,)))
    if certified:
        assert client(tmp_path).get(URL).json()['certification'] == 'certified'
    else:
        assert_suspended(tmp_path, 'outcome_history_temporal_policy_mismatch')


@pytest.mark.parametrize('kind', ['missing', 'file', 'denied', 'valid'])
def test_storage_root_availability(tmp_path, monkeypatch, kind):
    root = tmp_path / 'storage'
    if kind == 'file': root.write_text('not a directory')
    if kind in ('denied', 'valid'): root.mkdir()
    if kind == 'denied':
        original = os.open
        def denied(path, *args, **kwargs):
            if Path(path) == root: raise PermissionError('denied')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(os, 'open', denied)
    before = sorted(tmp_path.rglob('*'))
    response = client(root).get(URL)
    if kind == 'valid':
        assert response.status_code == 200 and response.json()['certification'] == 'certified'
        assert response.json()['rows'] == []
    else:
        assert response.status_code == 503
        assert response.json()['detail']['code'] == 'outcome_history_storage_unavailable'
    assert sorted(tmp_path.rglob('*')) == before
