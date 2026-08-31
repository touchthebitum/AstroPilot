from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from inspect import getsource
from uuid import UUID

import pytest

from astropilot.decision_forecast_evidence_store import (
    FileDecisionForecastEvidenceStore,
)
import decision.services.durable_tonight_application_service as durable_module
from decision.services.durable_tonight_application_service import (
    DurableTonightApplicationService,
    generate_decision_id,
)
from decision.services.tonight_application_service import (
    TonightResult,
    TonightStatus,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
)
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


FORECAST_AT = datetime(2026, 8, 31, 21, tzinfo=timezone.utc)
SITE = WeatherLocation(46.75, 6.55, altitude_m=1_245.0)
EVIDENCE = DecisionForecastEvidence(
    (
        WeatherForecastPoint(
            provider_id="open_meteo",
            model_id="best_match",
            retrieved_at_utc=FORECAST_AT.replace(hour=18),
            forecast_for_utc=FORECAST_AT,
            requested_location=SITE,
            grid_location=SITE,
            values=(
                WeatherValue(
                    WeatherVariable.TEMPERATURE_C,
                    8.25,
                    "°C",
                ),
            ),
        ),
    )
)


class FakeApplicationService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def evaluate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class FakeStore:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def save(self, *, decision_id, evidence):
        self.calls.append((decision_id, evidence))
        if self.error is not None:
            raise self.error


class IdFactory:
    def __init__(self, *identities, error=None):
        self.identities = iter(identities)
        self.error = error
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return next(self.identities)


def result(*, status=TonightStatus.AVAILABLE, evidence=EVIDENCE):
    return TonightResult(
        night={"date": "2026-08-31"},
        recommendation=object(),
        mission=object(),
        status=status,
        forecast_evidence=evidence,
    )


def wrapper(source_result, *, store=None, factory=None):
    application_service = FakeApplicationService(source_result)
    evidence_store = store or FakeStore()
    decision_id_factory = factory or IdFactory("decision-123")
    service = DurableTonightApplicationService(
        application_service=application_service,
        evidence_store=evidence_store,
        decision_id_factory=decision_id_factory,
    )
    return service, application_service, evidence_store, decision_id_factory


def test_available_result_is_persisted_once_and_structurally_enriched():
    original = result()
    service, application, store, factory = wrapper(original)
    arguments = {
        "profile": {"location": {"name": "Buttes"}},
        "weather": object(),
        "reference_time_utc": FORECAST_AT,
        "goal": "balanced",
    }

    durable = service.evaluate(**arguments)

    assert application.calls == [arguments]
    assert factory.calls == 1
    assert store.calls == [("decision-123", original.forecast_evidence)]
    assert store.calls[0][1] is original.forecast_evidence
    assert durable is not original
    assert durable.decision_id == "decision-123"
    assert durable.night is original.night
    assert durable.recommendation is original.recommendation
    assert durable.mission is original.mission
    assert durable.status is original.status
    assert durable.forecast_evidence is original.forecast_evidence
    assert original.decision_id is None


def test_result_without_evidence_returns_unchanged_without_id_or_save():
    original = result(
        status=TonightStatus.FORECAST_UNAVAILABLE,
        evidence=None,
    )
    service, application, store, factory = wrapper(original)

    returned = service.evaluate(profile={}, weather=None)

    assert returned is original
    assert returned.decision_id is None
    assert len(application.calls) == 1
    assert factory.calls == 0
    assert store.calls == []


@pytest.mark.parametrize(
    "status",
    [
        TonightStatus.NO_NIGHT,
        TonightStatus.NO_MISSION,
        TonightStatus.NO_PRODUCTIVE_WINDOW,
    ],
)
def test_partial_or_negative_result_with_evidence_is_persisted(status):
    original = result(status=status)
    service, _, store, factory = wrapper(original)

    durable = service.evaluate(profile={})

    assert durable.status is status
    assert durable.decision_id == "decision-123"
    assert factory.calls == 1
    assert store.calls == [("decision-123", EVIDENCE)]


def test_application_service_failure_prevents_id_and_save():
    application_error = RuntimeError("evaluation_failed")
    application = FakeApplicationService(error=application_error)
    store = FakeStore()
    factory = IdFactory("decision-123")
    service = DurableTonightApplicationService(
        application_service=application,
        evidence_store=store,
        decision_id_factory=factory,
    )

    with pytest.raises(RuntimeError, match="evaluation_failed"):
        service.evaluate(profile={})

    assert len(application.calls) == 1
    assert factory.calls == 0
    assert store.calls == []


def test_id_factory_failure_prevents_save():
    factory = IdFactory(error=RuntimeError("identity_failed"))
    service, _, store, _ = wrapper(result(), factory=factory)

    with pytest.raises(RuntimeError, match="identity_failed"):
        service.evaluate(profile={})

    assert factory.calls == 1
    assert store.calls == []


def test_store_failure_is_propagated_without_retry_or_durable_result():
    store = FakeStore(error=RuntimeError("save_failed"))
    service, application, _, factory = wrapper(result(), store=store)

    with pytest.raises(RuntimeError, match="save_failed"):
        service.evaluate(profile={})

    assert len(application.calls) == 1
    assert factory.calls == 1
    assert store.calls == [("decision-123", EVIDENCE)]


def test_same_evidence_in_two_evaluations_creates_two_events():
    original = result()
    store = FakeStore()
    factory = IdFactory("decision-1", "decision-2")
    service, application, _, _ = wrapper(
        original,
        store=store,
        factory=factory,
    )

    first = service.evaluate(profile={})
    second = service.evaluate(profile={})

    assert first.decision_id == "decision-1"
    assert second.decision_id == "decision-2"
    assert len(application.calls) == 2
    assert factory.calls == 2
    assert store.calls == [
        ("decision-1", EVIDENCE),
        ("decision-2", EVIDENCE),
    ]


def test_tonight_result_remains_immutable():
    original = result()

    with pytest.raises(FrozenInstanceError):
        original.decision_id = "changed"


def test_invalid_id_validation_is_delegated_to_store(tmp_path):
    real_store = FileDecisionForecastEvidenceStore(tmp_path)
    service, _, _, factory = wrapper(
        result(),
        store=real_store,
        factory=IdFactory("../invalid"),
    )

    with pytest.raises(
        DecisionForecastEvidencePersistenceError,
        match="invalid_decision_id",
    ):
        service.evaluate(profile={})

    assert factory.calls == 1
    assert list(tmp_path.iterdir()) == []


def test_production_id_factory_returns_distinct_canonical_uuid4_strings():
    first = generate_decision_id()
    second = generate_decision_id()

    assert isinstance(first, str)
    assert isinstance(second, str)
    assert first != second
    assert UUID(first).version == 4
    assert UUID(second).version == 4
    assert str(UUID(first)) == first
    assert str(UUID(second)) == second


def test_wrapper_has_no_clock_network_or_domain_specific_dependency():
    source = getsource(durable_module)

    assert "datetime" not in source
    assert "requests" not in source
    assert "meteoswiss" not in source.lower()
    assert "field_validation" not in source
    assert "provider_reliability" not in source
