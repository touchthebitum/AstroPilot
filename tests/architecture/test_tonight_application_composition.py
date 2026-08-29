import builtins

import astro_score
from decision.mission.mission_builder import NightMissionBuilder
from decision.opportunity.opportunity_engine import OpportunityEngine
from decision.recommendation.recommendation_engine import (
    RecommendationEngine,
)
from decision.services.tonight_application_service import (
    TonightApplicationService,
)


def test_factory_returns_tonight_application_service():
    service = astro_score.build_tonight_application_service()

    assert isinstance(service, TonightApplicationService)


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
