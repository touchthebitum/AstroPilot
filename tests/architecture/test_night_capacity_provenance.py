from conftest import modern_ranking_project
"""Capacity evidence reaches risk/API, but never supplies Tonight availability."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
import astro_score
from decision.portfolio.historical_night_capacity_estimator import (
    HistoricalNightCapacityEstimator as Estimator, NightCapacitySource as Source,
    NightCapacityEstimate,
)
from decision.risk.project_risk_context_builder import ProjectRiskContextBuilder
from decision.risk.risk_engine import RiskEngine
from decision.advisor.night_advisor import NightAdvisor
from decision.acceptance_lineage_persistence import serialize_night_mission, deserialize_night_mission
from decision.mission.night_mission import NightMission
from decision.services.tonight_response import TonightResponse
from decision.services.tonight_application_service import TonightResult
from astropilot.app import TonightPostponementRiskModel


def context(estimate):
    return SimpleNamespace(portfolio=SimpleNamespace(total_remaining_hours=15,
        highest_priority=80, average_progress=0,
        productive_hours_per_night=estimate.productive_hours_per_night,
        night_capacity_source=str(estimate.source), historical_nights=estimate.historical_nights),
        site=SimpleNamespace(latitude=46.7, longitude=6.5),
        session=SimpleNamespace(start_time=datetime(2026, 10, 6, tzinfo=timezone.utc)))


@pytest.mark.parametrize('sessions,count', [(None, None), ([], 0)])
@pytest.mark.parametrize('fallback,source', [(None, Source.UNKNOWN), (4, Source.PROFILE)])
def test_absent_and_empty_history_are_distinct(sessions, count, fallback, source):
    estimate = Estimator.estimate(sessions, fallback)
    assert estimate.historical_nights is count
    assert estimate.source == source
    assert not estimate.observed and estimate.estimated
    assert not estimate.decision_eligible


def test_explicit_scenario_is_preserved_and_cannot_claim_history():
    estimate = Estimator.estimate([], 6, fallback_source=Source.SCENARIO)
    assert estimate.source == Source.SCENARIO
    assert estimate.productive_hours_per_night == 6
    assert estimate.scenario_eligible and not estimate.observed
    with pytest.raises(ValueError):
        Estimator.estimate([], 6, fallback_source=Source.HISTORY)


@pytest.mark.parametrize('fallback', [None, 1, 4, 100])
def test_withdrawing_history_cannot_produce_confident_low_risk(monkeypatch, fallback):
    monkeypatch.setattr('decision.risk.project_risk_context_builder.SeasonResolver.resolve',
                       lambda _: {'remaining_days': 10, 'remaining_good_nights': 2})
    sessions = [{'date': str(i), 'hours': 1} for i in range(3)]
    observed = Estimator.estimate(sessions, fallback)
    removed = Estimator.estimate([], fallback)
    known = RiskEngine.evaluate(ProjectRiskContextBuilder.build('M31', context(observed)))
    unknown = RiskEngine.evaluate(ProjectRiskContextBuilder.build('M31', context(removed)))
    assert known.level == 'HIGH'
    assert unknown.level == 'UNKNOWN' and unknown.score is None
    assert not removed.decision_eligible and removed.confidence != 'medium'
    mission = NightMission(target='M31', confidence=None, risk_report=unknown)
    assert not any(a.category == 'risk' for a in NightAdvisor.build(SimpleNamespace(productivity=SimpleNamespace(productive_hours=3),
        season_analysis=None, risk_report=unknown)))
    document = serialize_night_mission(mission)
    restored = deserialize_night_mission(document)
    assert serialize_night_mission(restored) == document
    response = TonightResponse.from_result(TonightResult(night=None, recommendation=None,
        mission=restored)).to_dict()['postponement_risk']
    model = TonightPostponementRiskModel(**response)
    assert model.capacity_source == str(removed.source)
    assert model.capacity_estimated and not model.capacity_observed
    assert not model.capacity_decision_eligible and not model.decision_eligible
    assert model.historical_nights == 0


@pytest.mark.parametrize('source,count', [('unknown', None), ('history', 0), ('history', None), ('profile', 30)])
def test_bare_value_or_label_is_not_empirical_evidence(source, count):
    estimate = NightCapacityEstimate(4, source, count)
    assert not estimate.observed and not estimate.decision_eligible


@pytest.mark.parametrize('fallback', [1, 4, 100])
def test_history_withdrawal_and_profile_changes_do_not_increase_candidate_or_mission_gain(fallback):
    projects = {'M31': modern_ranking_project({'hours': 2, 'target_hours': 10, 'importance': 5})}
    profiles = [dict(projects=projects, preferences={'productive_hours_per_night': fallback},
                     sessions=[{'date': str(i), 'hours': 1} for i in range(3)]),
                dict(projects=projects, preferences={'productive_hours_per_night': fallback}, sessions=[])]
    candidates = [astro_score.recommend_project_for_night(
        [{'name': 'M31', 'catalog_key': 'M31', 'global_score': 80}],
        available_hours=2, profile=profile)[0] for profile in profiles]
    assert candidates[0].final_score == candidates[1].final_score
    assert candidates[0].decision_score == candidates[1].decision_score
    assert candidates[0].strategy_scores == candidates[1].strategy_scores
    assert candidates[0].closure_bonus == candidates[1].closure_bonus
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    evaluation = {'selected_acquisition_intent_id': 'sh2-129_ha', 'name': 'M31', 'catalog_key': 'M31', 'window': {'start': start,
        'end': start + timedelta(hours=2), 'clouds': 10, 'humidity': 50, 'wind': 2, 'seeing': 1.5}}
    missions = [astro_score.build_mission_input(evaluation, profile=p) for p in profiles]
    assert missions[0].recommended_hours == missions[1].recommended_hours == 2
    assert missions[0].expected_gain == missions[1].expected_gain


def test_explicit_scenario_computes_diagnostic_nights_without_empirical_pressure(monkeypatch):
    monkeypatch.setattr('decision.risk.project_risk_context_builder.SeasonResolver.resolve',
                       lambda _: {'remaining_days': 100, 'remaining_good_nights': 100})
    estimate = Estimator.estimate(None, 5, fallback_source=Source.SCENARIO)
    result = ProjectRiskContextBuilder.build('M31', context(estimate))
    assert result.required_nights == 3
    assert result.night_capacity_source == 'scenario'
    assert result.historical_nights is None
    assert result.pressure is None


pytestmark = pytest.mark.usefixtures("selected_modern_ranking_intent")
