from pathlib import Path
import runpy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from astropilot.app import create_app
from decision.field_observation import CloudState
from decision.services.durable_tonight_application_service import DurableTonightApplicationService
from decision.services.outcome_evaluation_orchestration import OutcomeEvaluationOrchestrationError
from decision.outcome_evaluation_persistence import OutcomeEvaluationPersistenceError
from decision.services.field_observation_context import FieldObservationContextError
from decision.weather.decision_forecast_evidence_persistence import DecisionForecastEvidencePersistenceError

builders = runpy.run_path(str(Path(__file__).parents[1] / "architecture/test_outcome_evaluation_orchestration_contract.py"))


def setup(tmp_path, execution=None):
    source = builders["observation"](execution_id=execution)
    orchestration = builders["service"](tmp_path, source,
        builders["MutableEvidenceStore"](builders["evidence"](builders["WeatherVariable"].TEMPERATURE_C)))
    app = DurableTonightApplicationService(application_service=None,
        evidence_store=orchestration.forecast_evidence_store, decision_id_factory=lambda: pytest.fail("allocated"),
        field_observation_store=orchestration.observation_store, outcome_evaluation_store=orchestration.outcome_evaluation_store)
    app._outcome_evaluation_service = orchestration
    app.outcome_evaluation_clock = lambda: pytest.fail("unused")
    client = TestClient(create_app(service_factory=lambda: app))
    return app, orchestration, client

URL = "/v1/field-observations/observation-1/outcome-evaluation"


@pytest.mark.parametrize("execution", [None, "execution-1"])
def test_post_replay_get_and_projection(tmp_path, execution):
    app, orchestration, client = setup(tmp_path, execution)
    first = client.post(URL)
    assert first.status_code == 201
    value = first.json()
    assert value["created"] is True
    assert value["version"] == "outcome_evaluation.v1"
    assert value["execution_id"] == execution
    assert (value["assessment"] is None) == (execution is None)
    assert value["results"][0]["signed_error"] == 1.0
    assert "source_digest" not in value and "comparison" not in value
    replay = client.post(URL)
    assert replay.status_code == 200 and replay.json() == {**value, "created": False}
    orchestration.clock = lambda: pytest.fail("GET clock")
    orchestration.context_resolver.resolve = lambda *_: pytest.fail("GET lineage")
    assert client.get(URL).json() == {k: v for k, v in value.items() if k != "created"}


def test_absent_and_not_found(tmp_path):
    _, _, client = setup(tmp_path)
    assert client.get(URL).json() == {"detail": {"code": "outcome_evaluation_not_found"}}
    for method in (client.get, client.post):
        response = method(URL.replace("observation-1", "absent"))
        assert response.status_code == 404
        assert response.json() == {"detail": {"code": "field_observation_not_found"}}
        assert method(URL.replace("observation-1", "..bad")).status_code == 422


def test_superseded_history_and_concurrent_posts(tmp_path):
    app, orchestration, client = setup(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(URL), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert len({r.json()["evaluation_id"] for r in responses}) == 1
    orchestration.observation_store.save(observation=builders["observation"](
        observation_id="observation-2", execution_id=None, supersedes_observation_id="observation-1"))
    assert client.get(URL).status_code == 200
    assert client.post(URL).json() == {"detail": {"code": "field_observation_superseded"}}
    assert client.post(URL).status_code == 409


@pytest.mark.parametrize("error,status,code", [
    (OutcomeEvaluationOrchestrationError("outcome_evaluation_conflict"),409,"outcome_evaluation_conflict"),
    (FieldObservationContextError("decision_not_found"),409,"decision_not_found"),
    (OutcomeEvaluationPersistenceError("outcome_evaluation_corrupt"),500,"outcome_evaluation_internal_error"),
    (DecisionForecastEvidencePersistenceError("invalid_json_document"),500,"outcome_evaluation_internal_error"),
    (OutcomeEvaluationOrchestrationError("comparison_identity_not_persistable"),500,"outcome_evaluation_internal_error"),
    (RuntimeError("outcome_evaluation_persistence_unavailable"),503,"outcome_evaluation_unavailable"),
    (PermissionError("/secret/document"),503,"outcome_evaluation_unavailable"),
    (ValueError("/secret/document contents"),500,"outcome_evaluation_internal_error"),
])
def test_safe_errors(tmp_path,error,status,code):
    app, _, client = setup(tmp_path)
    def fail(*_): raise error
    app.evaluate_outcome_observation = fail
    response = client.post(URL)
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}


def test_corrupt_document_and_wrapped_unavailability(tmp_path):
    app, orchestration, client = setup(tmp_path)
    client.post(URL)
    path = next((tmp_path / "outcomes").glob("*.json"))
    path.write_text("secret malformed document")
    assert client.get(URL).status_code == 500
    error = OutcomeEvaluationPersistenceError("outcome_evaluation_corrupt")
    error.__cause__ = PermissionError("secret path")
    def fail(*_): raise error
    app.load_outcome_evaluation_by_observation = fail
    assert client.get(URL).status_code == 503


def test_multiple_aggregates_and_not_comparable(tmp_path):
    app, orchestration, client = setup(tmp_path)
    orchestration.forecast_evidence_store.value = builders["evidence"]()
    response = client.post(URL)
    assert response.status_code == 201 and response.json()["status"] == "not_comparable"
    evaluation = app.load_outcome_evaluation_by_observation("observation-1")
    app.outcome_evaluation_store = SimpleNamespace(list_by_observation=lambda **_: [evaluation, evaluation])
    assert client.get(URL).status_code == 409


def test_missing_forecast_and_source_divergence(tmp_path):
    app, orchestration, client = setup(tmp_path)
    client.post(URL)
    orchestration.forecast_evidence_store.value = builders["evidence"]()
    assert client.post(URL).status_code == 409
    orchestration.forecast_evidence_store.value = None
    assert client.post(URL).status_code == 409


def test_invalid_request_has_stable_error(tmp_path):
    _, _, client = setup(tmp_path)
    response = client.post(URL, json={"unexpected": "private"})
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_outcome_evaluation_request"}}


def test_cloud_categories_and_units(tmp_path):
    source = builders['observation'](execution_id=None,
        conditions=builders['ObservedConditions'](cloud_state=CloudState.OVERCAST))
    app, orchestration, client = setup(tmp_path)
    # Keep the canonical observation immutable; use its replacement fixture in a new store.
    from astropilot.field_observation_store import FileFieldObservationStore
    store = FileFieldObservationStore(tmp_path / 'cloud-observations')
    store.save(observation=source)
    app.field_observation_store = store
    orchestration.observation_store = store
    orchestration.forecast_evidence_store.value = builders['evidence'](builders['WeatherVariable'].CLOUD_COVER_PERCENT)
    response = client.post(URL)
    assert response.status_code == 201
    cloud = response.json()['results'][0]
    assert cloud.pop('forecast_point')['temporal_offset_minutes'] == 0.0
    assert cloud == {'variable': 'cloud_cover_percent', 'status': 'comparable', 'unit': '%',
                     'forecast': 'few', 'observed': 'overcast', 'outcome': 'mismatch', 'reasons': []}


def test_humidity_weather_traceability_roundtrip_and_ui(tmp_path):
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    import json
    import subprocess
    from astropilot.field_observation_store import FileFieldObservationStore

    observed = datetime(2026, 10, 3, 0, 10, tzinfo=ZoneInfo("Europe/Zurich")).astimezone(timezone.utc)
    assert observed.isoformat() == "2026-10-02T22:10:00+00:00"
    app, orchestration, client = setup(tmp_path)
    source = builders['observation'](execution_id=None, observed_at_utc=observed,
        recorded_at_utc=observed + timedelta(minutes=1),
        conditions=builders['ObservedConditions'](relative_humidity_percent=73.0))
    store = FileFieldObservationStore(tmp_path / 'humidity-observations')
    store.save(observation=source)
    app.field_observation_store = orchestration.observation_store = store
    variable = builders['WeatherVariable'].RELATIVE_HUMIDITY_PERCENT
    point = builders['evidence'](variable).forecast_points[0]
    point = replace(point, provider_id="Open-Meteo", model_id=None,
        retrieved_at_utc=observed - timedelta(hours=4),
        forecast_for_utc=observed - timedelta(minutes=10),
        grid_location=builders['WeatherLocation'](46.76, 6.56, altitude_m=1200.0),
        values=(builders['WeatherValue'](variable=variable, value=91.0, unit="%"),))
    orchestration.forecast_evidence_store.value = builders['DecisionForecastEvidence']((point,))
    result = client.post(URL)
    assert result.status_code == 201
    payload = result.json()
    humidity = next(r for r in payload['results'] if r['variable'] == variable.value)
    assert (humidity['forecast'], humidity['observed'], humidity['signed_error']) == (91, 73, 18)
    assert humidity['forecast_point'] == {
        'selected_forecast_for_utc': '2026-10-02T22:00:00+00:00', 'temporal_offset_minutes': -10.0}
    trace = payload['weather_traceability']
    assert trace['provider_id'] == 'Open-Meteo' and trace['model_id'] is None
    assert trace['retrieved_at_utc'] == point.retrieved_at_utc.isoformat()
    assert trace['requested_location']['latitude'] == 46.75
    assert trace['grid_location'] == {'latitude': 46.76, 'longitude': 6.56, 'altitude_m': 1200.0}
    # Existing serialized evaluations are untouched; GET reads persisted comparison provenance.
    orchestration.clock = lambda: pytest.fail('read must not evaluate')
    readback = client.get(URL).json()
    assert readback == {k: v for k, v in payload.items() if k != 'created'}
    js = (Path(__file__).parents[2] / 'astropilot/web/app.js').read_text()
    render = js[js.index('function renderOutcomeEvaluation('):js.index('function validateOutcomeProjection(')]
    program = "const state={fieldObservationDraftContext:{timezone:'Europe/Zurich'}}; const output={}; const document={querySelector:()=>output}; const OUTCOME_REASON_TEXT={};\n" + render
    program += "\nrenderOutcomeEvaluation(" + json.dumps(readback) + "); console.log(output.textContent);"
    node = runpy.run_path(str(Path(__file__).with_name('test_field_observation_ui.py')))['javascript_engine']()
    if node is None or Path(node).name != 'node':
        pytest.skip('Node required for UI rendering')
    text = subprocess.check_output([node, '-e', program], text=True)
    assert '00:00' in text and '2026-10-02T22:00:00.000Z' in text
    assert '-10 min' in text and 'Open-Meteo' in text and '1200 m' in text
    assert 'prévision 91 %, observation 73 %' in text and '18 %' in text
    ambiguous = replace(point, grid_location=builders['WeatherLocation'](46.77, 6.57))
    orchestration.forecast_evidence_store.value = builders['DecisionForecastEvidence']((point, ambiguous))
    assert client.get(URL).json()['weather_traceability']['grid_location'] is None
    orchestration.forecast_evidence_store.value = None
    missing = client.get(URL).json()
    assert missing['weather_traceability']['grid_location'] is None
    assert missing['results'] == readback['results']
