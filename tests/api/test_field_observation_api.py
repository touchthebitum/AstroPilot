from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from astropilot.app import create_app
from decision.field_observation_persistence import (
    FieldObservationPersistenceError,
)
from decision.models.execution import ExecutionStatus
from decision.services.field_observation_context import (
    ResolvedFieldObservationContext,
)
from decision.services.field_observation_recording_service import (
    FieldObservationRecordingError,
    FieldObservationRecordingResult,
)


NOW = datetime(2026, 9, 29, 21, 10, tzinfo=timezone.utc)


class FieldObservationService:
    def __init__(self):
        self.observations = {}

    @staticmethod
    def context(observation):
        return ResolvedFieldObservationContext(
            decision_id=observation.decision_id,
            site_name="Buttes",
            latitude=46.9,
            longitude=6.5,
            target="Sh2-129",
            catalog_key="Sh2-129",
            imaging_field_id="sh2-129",
            acquisition_intent_id="sh2-129_ha",
            mission_id=("mission-1" if observation.execution_id else None),
            execution_id=observation.execution_id,
            execution_status=(
                ExecutionStatus.COMPLETED if observation.execution_id else None
            ),
            forecast_evidence_available=True,
        )

    def record_field_observation(self, observation):
        if observation.decision_id == "missing-decision":
            raise FieldObservationRecordingError("decision_not_found")
        existing = self.observations.get(observation.observation_id)
        if existing is not None and existing != observation:
            raise FieldObservationPersistenceError(
                "field_observation_conflict"
            )
        created = existing is None
        self.observations.setdefault(observation.observation_id, observation)
        return FieldObservationRecordingResult(
            observation=self.observations[observation.observation_id],
            resolved_context=self.context(observation),
            created=created,
        )

    def load_field_observation(self, observation_id):
        return self.observations.get(observation_id)

    def list_field_observations_by_decision(self, decision_id):
        return [
            item for item in self.observations.values()
            if item.decision_id == decision_id
        ]

    def list_field_observations_by_execution(self, execution_id):
        return [
            item for item in self.observations.values()
            if item.execution_id == execution_id
        ]


def payload(**overrides):
    value = {
        "observation_id": "observation-1",
        "decision_id": "decision-1",
        "execution_id": "execution-1",
        "observed_at_utc": "2026-09-29T21:05:00Z",
        "recorded_at_utc": "2026-09-29T21:10:00Z",
        "supersedes_observation_id": None,
        "conditions": {
            "temperature_c": 15.2,
            "relative_humidity_percent": 60,
            "cloud_state": "overcast",
            "transparency": "poor",
            "seeing": None,
            "wind_speed_kmh": 0,
            "surface_condition": "damp",
            "moon_halo": False,
        },
        "acquisition": {
            "attempted_frames": None,
            "usable_frames": None,
            "stop_reason": "clouds",
        },
        "technical": {
            "hfr": None,
            "hfr_unit": None,
            "sky_background": None,
            "sky_background_unit": None,
            "guiding_rms_arcsec": None,
        },
        "confidence": "medium",
        "quality_flags": ["estimated", "partial"],
    }
    value.update(overrides)
    return value


def client_and_service():
    service = FieldObservationService()
    client = TestClient(
        create_app(service_factory=lambda: service, clock=lambda: NOW)
    )
    return client, service


def test_field_observation_create_replay_read_and_list_contract():
    client, service = client_and_service()

    created = client.post("/v1/field-observations", json=payload())
    replay = client.post("/v1/field-observations", json=payload())
    loaded = client.get("/v1/field-observations/observation-1")
    by_decision = client.get(
        "/v1/decisions/decision-1/field-observations"
    )
    by_execution = client.get(
        "/v1/executions/execution-1/field-observations"
    )

    assert created.status_code == 201
    assert created.json()["created"] is True
    assert created.json()["context"] == {
        "decision_id": "decision-1",
        "site_name": "Buttes",
        "latitude": 46.9,
        "longitude": 6.5,
        "target": "Sh2-129",
        "catalog_key": "Sh2-129",
        "imaging_field_id": "sh2-129",
        "acquisition_intent_id": "sh2-129_ha",
        "mission_id": "mission-1",
        "execution_id": "execution-1",
        "execution_status": "completed",
        "forecast_evidence_available": True,
    }
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert loaded.status_code == 200
    assert loaded.json()["conditions"]["cloud_state"] == "overcast"
    assert loaded.json()["recorded_at_utc"] == NOW.isoformat()
    assert by_decision.json() == [loaded.json()]
    assert by_execution.json() == [loaded.json()]
    assert len(service.observations) == 1


def test_field_observation_conflict_and_missing_decision_are_explicit():
    client, _service = client_and_service()
    assert client.post("/v1/field-observations", json=payload()).status_code == 201

    changed = payload()
    changed["conditions"]["temperature_c"] = 16.0
    conflict = client.post("/v1/field-observations", json=changed)
    missing = client.post(
        "/v1/field-observations",
        json=payload(
            observation_id="observation-2",
            decision_id="missing-decision",
        ),
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "field_observation_conflict"
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "decision_not_found"


def test_field_observation_api_rejects_empty_invalid_and_unknown_fields():
    client, service = client_and_service()
    empty = payload(
        conditions={}, acquisition={}, technical={}
    )
    invalid_humidity = payload()
    invalid_humidity["conditions"]["relative_humidity_percent"] = 101
    unknown = payload(unexpected=True)

    for candidate in (empty, invalid_humidity, unknown):
        assert client.post(
            "/v1/field-observations", json=candidate
        ).status_code == 422
    assert service.observations == {}


def test_field_observation_quick_capture_ui_is_categorical_and_progressive():
    root = Path(__file__).resolve().parents[2] / "astropilot" / "web"
    html = (root / "index.html").read_text(encoding="utf-8")
    script = (root / "app.js").read_text(encoding="utf-8")

    assert html.count('data-observation-choice="') == 2
    assert 'type="range"' not in html
    assert 'value="partly_cloudy"' in html
    assert 'value="excellent"' in html
    assert 'id="observation-wind" type="number"' in html
    assert "Ajouter des détails" in html
    assert 'name="observation-surface"' in html
    assert "OBSERVATION_CHOICES" in script
    assert 'quality_flags: ["estimated", "partial"]' in script
    assert "pendingFieldObservation" in script
