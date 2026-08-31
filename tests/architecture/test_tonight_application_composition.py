import builtins

import astro_score
import astropilot.app as app_module
from astropilot.decision_forecast_evidence_store import (
    FileDecisionForecastEvidenceStore,
)
from decision.services.durable_tonight_application_service import (
    DurableTonightApplicationService,
    generate_decision_id,
)
from decision.mission.mission_builder import NightMissionBuilder
from decision.opportunity.opportunity_engine import OpportunityEngine
from decision.recommendation.recommendation_engine import (
    RecommendationEngine,
)
from decision.services.tonight_application_service import (
    TonightApplicationService,
    TonightResult,
    TonightStatus,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


def test_factory_returns_tonight_application_service():
    service = astro_score.build_tonight_application_service()

    assert isinstance(service, TonightApplicationService)


def test_durable_factory_wraps_pure_service_with_canonical_store(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    service = astro_score.build_durable_tonight_application_service()

    assert isinstance(service, DurableTonightApplicationService)
    assert isinstance(service.application_service, TonightApplicationService)
    assert isinstance(
        service.evidence_store,
        FileDecisionForecastEvidenceStore,
    )
    assert service.evidence_store._directory == (
        tmp_path / "decision_forecast_evidence"
    )
    assert service.decision_id_factory is generate_decision_id


def test_durable_factory_persists_and_reloads_evaluation_evidence(
    monkeypatch,
    tmp_path,
):
    source = DecisionForecastEvidence(())

    class ControlledService:
        def evaluate(self, **kwargs):
            return TonightResult(
                None,
                None,
                None,
                status=TonightStatus.NO_NIGHT,
                forecast_evidence=source,
            )

    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        astro_score,
        "build_tonight_application_service",
        lambda: ControlledService(),
    )
    monkeypatch.setattr(
        astro_score,
        "generate_decision_id",
        lambda: "decision-123",
    )

    result = astro_score.build_durable_tonight_application_service().evaluate()
    store = FileDecisionForecastEvidenceStore(
        tmp_path / "decision_forecast_evidence"
    )

    assert result.decision_id == "decision-123"
    assert store.load(decision_id=result.decision_id) == result.forecast_evidence


def test_api_production_factory_uses_common_durable_factory(monkeypatch):
    marker = object()
    monkeypatch.setattr(
        astro_score,
        "build_durable_tonight_application_service",
        lambda: marker,
    )

    assert app_module._production_service_factory() is marker


def test_factory_wires_exact_production_dependencies():
    service = astro_score.build_tonight_application_service()

    assert service.forecast_nights is astro_score.forecast_astro
    assert service.build_candidates is astro_score.recommend_project_for_night
    assert (
        service.opportunity_recommendation_service
        is astro_score.opportunity_recommendation_service
    )
    assert (
        service.tonight_mission_service
        is astro_score.tonight_mission_service
    )
    assert service.build_mission_input is astro_score.build_mission_input


def test_factory_call_causes_no_application_side_effects(monkeypatch):
    calls = []

    def record(name):
        return lambda *args, **kwargs: calls.append(name)

    monkeypatch.setattr(astro_score, "load_user_profile", record("profile"))
    monkeypatch.setattr(astro_score, "fetch_weather", record("weather"))
    monkeypatch.setattr(astro_score, "save_user_profile", record("persistence"))
    monkeypatch.setattr(
        astro_score.report_runner,
        "run_tonight",
        record("report"),
    )
    monkeypatch.setattr(
        astro_score.MissionPresenter,
        "present",
        record("presenter"),
    )
    monkeypatch.setattr(builtins, "print", record("print"))

    astro_score.build_tonight_application_service()

    assert calls == []


def test_factory_preserves_real_recommendation_engines():
    service = astro_score.build_tonight_application_service()
    recommendation_service = service.opportunity_recommendation_service

    assert isinstance(
        recommendation_service.opportunity_engine,
        OpportunityEngine,
    )
    assert isinstance(
        recommendation_service.recommendation_engine,
        RecommendationEngine,
    )
    assert (
        recommendation_service.opportunity_engine
        is astro_score.opportunity_engine
    )
    assert (
        recommendation_service.recommendation_engine
        is astro_score.recommendation_engine
    )


def test_factory_preserves_real_mission_builder():
    service = astro_score.build_tonight_application_service()

    assert (
        service.tonight_mission_service.build_mission
        is NightMissionBuilder.build
    )
