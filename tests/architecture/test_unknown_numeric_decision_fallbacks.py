from conftest import modern_ranking_project
"""Reachability of unknown diagnostics through production decision boundaries."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import astro_score
from decision.portfolio.historical_night_capacity_estimator import NightCapacityEstimate, NightCapacitySource
from decision.engines.future_opportunity_engine import FutureOpportunityEngine
from decision.models.future_opportunity import FutureOpportunity
from decision.portfolio.portfolio_forecast_engine import PortfolioForecastEngine
from decision.portfolio.project_scoring import simulated_portfolio_score
from decision.risk.postponement_impact import risk_label_to_score, compute_postponement_impact
from decision.risk.project_risk_context_builder import ProjectRiskContextBuilder
from decision.risk.risk_engine import RiskEngine
from decision.advisor.night_advisor import NightAdvisor


@pytest.mark.parametrize('label', [None, 'INCONNU', '', 'unexpected'])
def test_unknown_risk_is_not_a_midpoint_measurement(label):
    assert risk_label_to_score(label) is None


@pytest.mark.parametrize('astro', [20, 69, 70, 100])
@pytest.mark.parametrize('priority', [0, 50, 100])
@pytest.mark.parametrize('confidence', ['HAUTE', 'MOYENNE', 'BASSE'])
def test_unknown_risk_bound_cannot_improve_known_adverse_impact(astro, priority, confidence):
    unknown = compute_postponement_impact(None, confidence, priority, astro)
    assert unknown['urgency_bonus'] == 0
    for risk in range(101):
        known = compute_postponement_impact(risk, confidence, priority, astro)
        assert unknown['postponement_net_impact'] <= known['postponement_net_impact']


@pytest.mark.parametrize('label', ['FAIBLE', 'MOYEN', 'ÉLEVÉ', 'CRITIQUE'])
@pytest.mark.parametrize('astro', [20, 60, 80, 100])
@pytest.mark.parametrize('mode', ['balanced', 'roi', 'completion', 'diversification', 'risk'])
def test_real_candidate_boundary_withdrawing_risk_never_improves_scores(monkeypatch, label, astro, mode):
    risk = [label]
    monkeypatch.setattr(astro_score.future_engine, 'estimate', lambda *a, **k:
        FutureOpportunity(10, risk[0], 1.0, 2, 5.0))
    profile = {'projects': {'M31': modern_ranking_project({'hours': 2, 'target_hours': 10, 'importance': 5})},
               'preferences': {'decision_mode': mode}}
    def candidate():
        return astro_score.recommend_project_for_night(
            [{'name': 'M31', 'catalog_key': 'M31', 'global_score': astro}],
            available_hours=2, profile=profile)[0]
    known = candidate()
    risk[0] = 'INCONNU'
    unknown = candidate()
    assert unknown.final_score <= known.final_score
    assert unknown.decision_score <= known.decision_score
    assert all(unknown.strategy_scores[k] <= known.strategy_scores[k] for k in known.strategy_scores)
    assert unknown.closure_bonus == known.closure_bonus


@pytest.mark.parametrize('remaining,priority', [(None, None), (0, 0), (10, None), (None, 80)])
def test_risk_builder_preserves_unknown_and_zero_without_capacity_gain(monkeypatch, remaining, priority):
    monkeypatch.setattr('decision.risk.project_risk_context_builder.SeasonResolver.resolve',
        lambda _: {'remaining_days': 10, 'remaining_good_nights': 2})
    portfolio = SimpleNamespace(total_remaining_hours=remaining, highest_priority=priority,
        average_progress=None, productive_hours_per_night=4, night_capacity_source='profile', historical_nights=0)
    context = SimpleNamespace(portfolio=portfolio, site=SimpleNamespace(latitude=46.7, longitude=6.5),
        session=SimpleNamespace(start_time=datetime(2026, 10, 6, tzinfo=timezone.utc)))
    result = ProjectRiskContextBuilder.build('M31', context)
    assert result.remaining_hours is remaining
    assert result.priority is priority
    assert result.completion is None
    if remaining is None:
        assert result.required_nights is None
        assert result.pressure is None
    else:
        assert result.required_nights == (0 if remaining == 0 else 3)
    if remaining is None or priority is None:
        report = RiskEngine.evaluate(result)
        assert report.score is None
        assert report.level == 'UNKNOWN'
        mission = SimpleNamespace(productivity=SimpleNamespace(productive_hours=3),
            season_analysis=None, risk_report=report)
        assert not any(a.category == 'risk' for a in NightAdvisor.build(mission))


def weather():
    return {'hourly': {'time': ['2026-10-06T23:00'], 'cloud_cover': [0],
        'relative_humidity_2m': [50], 'wind_speed_10m': [5], 'precipitation': [0]}}


@pytest.mark.parametrize('missing', ['weather', 'remaining', 'night_hours'])
def test_future_engine_unknown_evidence_does_not_invent_numeric_opportunity(monkeypatch, missing):
    monkeypatch.setattr('decision.engines.future_opportunity_engine.SeasonResolver.resolve',
        lambda _: {'remaining_days': 30, 'remaining_good_nights': 10, 'source': 'dynamic'})
    data = weather()
    if missing == 'night_hours':
        data['hourly']['time'] = ['2026-10-06T12:00']
    engine = FutureOpportunityEngine({'M31': {'name': 'M31'}},
        lambda *a: None if missing == 'weather' else data)
    result = engine.estimate('M31', remaining_hours=None if missing == 'remaining' else 6,
        latitude=46.7, longitude=6.5,
        night_capacity=NightCapacityEstimate(3, NightCapacitySource.SCENARIO, None))
    assert result.risk == 'INCONNU'


def test_real_roadmap_boundary_unknown_ratio_does_not_add_scarcity_bonus():
    class UnknownFuture:
        def estimate(self, *a, **k):
            return FutureOpportunity(0, 'INCONNU', 0.0, 0, 0.0)
    project = modern_ranking_project({'hours': 0, 'target_hours': 10, 'importance': 0})
    roadmap = PortfolioForecastEngine(UnknownFuture(), simulated_portfolio_score).simulate_dynamic_portfolio_roadmap(
        night_capacities=[{'hours': 2}], profile={'projects': {'M31': project}})
    assert roadmap[0]['score'] == simulated_portfolio_score(project, available_hours=2)
    assert roadmap[0]['hours'] == 2


def test_real_roadmap_priority_unknown_cannot_outrank_explicit_low_priority():
    class UnknownFuture:
        def estimate(self, *a, **k):
            return FutureOpportunity(0, 'INCONNU', 0.0, 0, 0.0)
    projects = {'unknown': modern_ranking_project({'hours': 0, 'target_hours': 10}),
                'known': modern_ranking_project({'hours': 0, 'target_hours': 10, 'importance': 1})}
    roadmap = PortfolioForecastEngine(UnknownFuture(), simulated_portfolio_score).simulate_dynamic_portfolio_roadmap(
        night_capacities=[{'hours': 2}], profile={'projects': projects})
    assert roadmap[0]['project'] == 'known'

@pytest.mark.parametrize('score,level', [(63, 'MEDIUM'), (None, 'UNKNOWN')])
def test_legacy_and_unknown_risk_roundtrip_and_api_are_explicit(score, level):
    from decision.risk.risk_report import RiskReport
    from decision.risk.project_risk_context import ProjectRiskContext
    from decision.mission.night_mission import NightMission
    from decision.acceptance_lineage_persistence import serialize_night_mission, deserialize_night_mission
    from decision.services.tonight_response import TonightResponse
    from decision.services.tonight_application_service import TonightResult
    from astropilot.app import TonightPostponementRiskModel
    context = ProjectRiskContext(priority=None if score is None else 50,
        remaining_hours=None if score is None else 5.5, completion=0,
        season_remaining_days=21, favorable_nights=2)
    mission = NightMission(target='M31', confidence=None, risk_report=RiskReport(level, score, context=context))
    document = serialize_night_mission(mission)
    restored = deserialize_night_mission(document)
    assert serialize_night_mission(restored) == document
    assert restored.risk_report.score == score
    response = TonightResponse.from_result(TonightResult(night=None, recommendation=None, mission=restored)).to_dict()['postponement_risk']
    assert response['score'] == score
    assert response['estimated'] is True
    assert response['decision_eligible'] is False
    assert TonightPostponementRiskModel(**response).score == score


@pytest.mark.parametrize('priority', [0, 50, 100])
@pytest.mark.parametrize('astro', [20, 80])
def test_withdrawing_priority_and_confidence_cannot_improve_known_risk_impact(priority, astro):
    for confidence in ['HAUTE', 'MOYENNE', 'BASSE']:
        known = compute_postponement_impact(80, confidence, priority, astro)
        unknown = compute_postponement_impact(80, None, None, astro)
        assert unknown['postponement_net_impact'] <= known['postponement_net_impact']


@pytest.mark.parametrize('capacities', [None, [], [{}], [{'hours': None}], [{'hours': 0}]])
def test_roadmap_unknown_capacity_never_becomes_five_hours_gain(capacities):
    engine = PortfolioForecastEngine(SimpleNamespace(estimate=lambda *a, **k:
        FutureOpportunity(0, 'INCONNU', 0, 0, 0)), simulated_portfolio_score)
    result = engine.simulate_dynamic_portfolio_roadmap(night_capacities=capacities,
        profile={'projects': {'M31': modern_ranking_project({'hours': 0, 'target_hours': 10})}})
    assert result == []


def test_roadmap_explicit_scenario_capacity_is_a_user_default():
    engine = PortfolioForecastEngine(SimpleNamespace(estimate=lambda *a, **k:
        FutureOpportunity(0, 'INCONNU', 0, 0, 0)), simulated_portfolio_score)
    result = engine.simulate_dynamic_portfolio_roadmap(avg_night_hours=5,
        profile={'projects': {'M31': modern_ranking_project({'hours': 0, 'target_hours': 10})}})
    assert sum(row['hours'] for row in result) == 10
    assert all(row['capacity'] == 5 for row in result)


pytestmark = pytest.mark.usefixtures("selected_modern_ranking_intent")
