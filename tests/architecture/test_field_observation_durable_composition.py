from pathlib import Path

from astropilot.field_observation_store import FileFieldObservationStore
from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
from decision.services.durable_tonight_application_service import (
    DurableTonightApplicationService,
)


class ObservationStore:
    def __init__(self):
        self.calls = []

    def load(self, *, observation_id):
        self.calls.append(("load", observation_id))
        return "observation"

    def list_by_decision(self, *, decision_id):
        self.calls.append(("decision", decision_id))
        return ["decision-observation"]

    def list_by_execution(self, *, execution_id):
        self.calls.append(("execution", execution_id))
        return ["execution-observation"]


def test_durable_facade_exposes_only_observation_commands_and_reads():
    store = ObservationStore()
    service = DurableTonightApplicationService(
        application_service=object(),
        evidence_store=object(),
        decision_id_factory=lambda: "decision",
        field_observation_store=store,
    )
    assert service.load_field_observation("observation-1") == "observation"
    assert service.list_field_observations_by_decision("decision-1") == [
        "decision-observation"
    ]
    assert service.list_field_observations_by_execution("execution-1") == [
        "execution-observation"
    ]
    assert store.calls == [
        ("load", "observation-1"),
        ("decision", "decision-1"),
        ("execution", "execution-1"),
    ]


def test_production_composition_uses_canonical_user_data_directory(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    from astro_score import build_durable_tonight_application_service

    service = build_durable_tonight_application_service()
    assert type(service.field_observation_store) is FileFieldObservationStore
    assert service.field_observation_store._directory == (
        Path(tmp_path) / "field_observations"
    )
    assert type(service.outcome_evaluation_store) is FileOutcomeEvaluationStore
    assert service.outcome_evaluation_store._directory == (
        Path(tmp_path) / "outcome_evaluations"
    )
    assert not (tmp_path / "field_observations").exists()
    assert not (tmp_path / "outcome_evaluations").exists()
