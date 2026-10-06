"""No implicit 3h evidence at the real future/roadmap/gain boundaries."""
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
import json

import pytest
import astro_score
from decision.engines.future_opportunity_engine import FutureOpportunityEngine
from decision.models.future_opportunity import FutureOpportunity
from decision.portfolio.historical_night_capacity_estimator import NightCapacityEstimate, NightCapacitySource as Source
from decision.portfolio.portfolio_forecast_engine import PortfolioForecastEngine
from decision.portfolio.project_gain import portfolio_gain_if_shot, session_portfolio_gain, session_roi
from decision.portfolio.project_scoring import closure_bonus, closure_bonus_for_remaining, simulated_portfolio_score


def profile(hours=None, *, history=None):
    value = {'location': {'latitude': 46.7, 'longitude': 6.5}, 'preferences': {},
             'projects': {'M31': {'hours': 0, 'target_hours': 15, 'importance': 5}}}
    if hours is not None:
        value['preferences']['productive_hours_per_night'] = hours
    if history is not None:
        value['sessions'] = history
    return value


def observed(hours):
    return [{'date': f'2026-10-{i:02}', 'hours': hours} for i in (1, 2, 3)]


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr('decision.engines.future_opportunity_engine.SeasonResolver.resolve',
        lambda _: {'remaining_days': 100, 'remaining_good_nights': 30, 'source': 'dynamic'})
    return FutureOpportunityEngine({'M31': {'name': 'M31'}, 'M51': {'name': 'M51'}},
        lambda *_: {'hourly': {'time': ['2026-10-06T23:00'], 'cloud_cover': [0],
        'relative_humidity_2m': [50], 'wind_speed_10m': [5], 'precipitation': [0]}})


@pytest.mark.parametrize('hours', [None, 1, 3, 100])
@pytest.mark.parametrize('history', [None, [], [{'date': '2026-10-01', 'hours': 1}]])
def test_absent_or_insufficient_history_is_not_three_hours(engine, hours, history):
    result = engine.estimate('M31', remaining_hours=15, profile=profile(hours, history=history))
    assert result.risk == 'INCONNU'
    assert result.needed_nights == 0 and result.opportunity_ratio == 0
    assert result.night_capacity.source == ('unknown' if hours is None else 'profile')
    assert not result.night_capacity.observed
    assert result.night_capacity.historical_nights == (None if history is None else len(history))


@pytest.mark.parametrize('hours,needed', [(1, 15), (3, 5), (5, 3)])
def test_empirical_capacity_controls_needed_nights_and_has_provenance(engine, hours, needed):
    result = engine.estimate('M31', remaining_hours=15, profile=profile(100, history=observed(hours)))
    assert result.needed_nights == needed
    assert result.night_capacity.source == Source.HISTORY
    assert result.night_capacity.observed and not result.night_capacity.estimated
    assert json.loads(json.dumps(asdict(result)))['night_capacity']['source'] == 'history'


@pytest.mark.parametrize('hours,needed', [(1, 15), (3, 5), (5, 3)])
def test_explicit_scenario_is_allowed_without_becoming_observed(engine, hours, needed):
    capacity = NightCapacityEstimate(hours, Source.SCENARIO, None)
    result = engine.estimate('M31', remaining_hours=15, profile=profile(), night_capacity=capacity)
    assert result.needed_nights == needed
    assert result.night_capacity is capacity
    assert capacity.estimated and not capacity.decision_eligible
    assert capacity.confidence == 'low'


@pytest.mark.parametrize('capacity', [
    NightCapacityEstimate(100, Source.PROFILE, 0),
    NightCapacityEstimate(3, Source.HISTORY, 0),
    NightCapacityEstimate(3, Source.HISTORY, None),
    NightCapacityEstimate(None, Source.UNKNOWN, None),
    NightCapacityEstimate(float('nan'), Source.SCENARIO, None),
    NightCapacityEstimate(0, Source.SCENARIO, None),
    NightCapacityEstimate(1e-310, Source.SCENARIO, None),
])
def test_unapproved_capacity_does_not_produce_future_risk(engine, capacity):
    assert engine.estimate('M31', remaining_hours=15, profile=profile(),
        night_capacity=capacity).risk == 'INCONNU'


@pytest.mark.parametrize('mode', ['balanced', 'roi', 'completion', 'diversification', 'risk'])
@pytest.mark.parametrize('hours', [1, 3, 5])
def test_withdrawing_history_cannot_raise_real_candidate_scores_or_gain(engine, monkeypatch, mode, hours):
    monkeypatch.setattr(astro_score, 'future_engine', engine)
    known_profile = profile(100, history=observed(hours))
    unknown_profile = profile(100, history=[])
    known_profile['preferences']['decision_mode'] = mode
    unknown_profile['preferences']['decision_mode'] = mode
    def candidate(p):
        return astro_score.recommend_project_for_night(
            [{'name': 'M31', 'catalog_key': 'M31', 'global_score': 80}],
            available_hours=2, profile=p)[0]
    known, removed = candidate(known_profile), candidate(unknown_profile)
    assert removed.final_score <= known.final_score
    assert removed.decision_score <= known.decision_score
    assert all(removed.strategy_scores[k] <= known.strategy_scores[k] for k in known.strategy_scores)
    assert removed.closure_bonus == known.closure_bonus
    assert removed.acquisition_intent_assessments == known.acquisition_intent_assessments
    start = datetime(2026, 10, 6, tzinfo=timezone.utc)
    evaluation = {'name': 'M31', 'catalog_key': 'M31', 'window': {'start': start,
        'end': start + timedelta(hours=2), 'clouds': 10, 'humidity': 50, 'wind': 2, 'seeing': 1.5}}
    inputs = [astro_score.build_mission_input(evaluation, profile=p) for p in (known_profile, unknown_profile)]
    assert inputs[0].recommended_hours == inputs[1].recommended_hours == 2
    assert inputs[0].expected_gain == inputs[1].expected_gain


def test_explicit_future_capacity_changes_simulated_ranking_but_not_night_allocation(engine):
    # 3 h is now a deliberate, inspectable scenario rather than a hidden divisor.
    p = profile()
    p['projects'] = {'M31': {'hours': 0, 'target_hours': 90, 'importance': 5},
                     'M51': {'hours': 0, 'target_hours': 12, 'importance': 8.5}}
    forecast = PortfolioForecastEngine(engine, simulated_portfolio_score)
    results = [forecast.simulate_dynamic_portfolio_roadmap(
        [{'hours': 1}], profile=p,
        future_night_capacity=NightCapacityEstimate(h, Source.SCENARIO, None)) for h in (3, 1)]
    assert [r[0]['project'] for r in results] == ['M31', 'M51']
    for result, hours in zip(results, (3, 1)):
        assert sum(step['hours'] for step in result) == 1
        assert result[0]['future_capacity']['hours'] == hours
        assert result[0]['future_capacity']['source'] == 'scenario'
        assert not result[0]['future_capacity']['observed']


def test_roadmap_does_not_extrapolate_current_night_to_all_future_nights(engine):
    p = profile(100, history=[])
    result = PortfolioForecastEngine(engine, simulated_portfolio_score).simulate_dynamic_portfolio_roadmap(
        [{'hours': 1}], profile=p)
    assert result[0]['score'] == simulated_portfolio_score(p['projects']['M31'], available_hours=1)
    assert result[0]['future_capacity']['source'] == 'profile'
    assert not result[0]['future_capacity']['empirical_eligible']


@pytest.mark.parametrize('duration', [None, 0, -1, float('nan'), float('inf'), True])
def test_missing_session_capacity_creates_no_gain_roi_or_closure(duration):
    projects = {'M31': {'hours': 0, 'target_hours': 2, 'importance': 5}}
    assert portfolio_gain_if_shot('M31', duration, projects=projects) == 0
    assert session_portfolio_gain('M31', duration, projects=projects) == 0
    assert session_roi('M31', duration, projects=projects) == 0
    assert closure_bonus('M31', duration, projects=projects) == 0
    assert closure_bonus_for_remaining(2, duration) == 0
    assert simulated_portfolio_score(projects['M31'], duration) == 30


def test_omitted_session_capacity_is_neutral_but_explicit_three_hours_is_preserved():
    projects = {'M31': {'hours': 0, 'target_hours': 2, 'importance': 5}}
    assert portfolio_gain_if_shot('M31', projects=projects) == 0
    assert session_portfolio_gain('M31', projects=projects) == 0
    assert session_roi('M31', projects=projects) == 0
    assert closure_bonus('M31', projects=projects) == 0
    assert closure_bonus_for_remaining(2) == 0
    assert simulated_portfolio_score(projects['M31']) == 30
    assert session_portfolio_gain('M31', 3, projects=projects) == 100
    assert closure_bonus('M31', 3, projects=projects) == 15
    assert simulated_portfolio_score(projects['M31'], 3) == 45


def test_legacy_future_values_and_five_argument_constructor_remain_faithful():
    legacy = FutureOpportunity(20, 'FAIBLE', 1, 5, 4)
    assert (legacy.good_nights, legacy.risk, legacy.weather_ratio,
            legacy.needed_nights, legacy.opportunity_ratio) == (20, 'FAIBLE', 1, 5, 4)
    assert legacy.night_capacity is None


def test_real_roadmap_uses_history_instead_of_implicit_three_hours(engine):
    p = profile(100, history=observed(1))
    p['projects'] = {'M31': {'hours': 0, 'target_hours': 90, 'importance': 5},
                     'M51': {'hours': 0, 'target_hours': 12, 'importance': 8.5}}
    result = PortfolioForecastEngine(engine, simulated_portfolio_score).simulate_dynamic_portfolio_roadmap(
        [{'hours': 1}], profile=p)
    assert result[0]['project'] == 'M51'
    assert result[0]['future_capacity']['source'] == 'history'
    assert result[0]['future_capacity']['hours'] == 1
    assert result[0]['hours'] == 1


@pytest.mark.parametrize('hours', [1, 3, 100])
def test_future_scenario_cannot_improve_actual_tonight_ranking(engine, monkeypatch, hours):
    scenario = engine.estimate('M31', remaining_hours=15, profile=profile(),
        night_capacity=NightCapacityEstimate(hours, Source.SCENARIO, None))
    assert scenario.risk != 'INCONNU'
    result = [scenario]
    monkeypatch.setattr(astro_score, 'future_engine', type('ScenarioFuture', (), {
        'estimate': lambda *a, **k: result[0]})())
    def candidate():
        return astro_score.recommend_project_for_night(
            [{'name': 'M31', 'catalog_key': 'M31', 'global_score': 80}],
            available_hours=2, profile=profile())[0]
    unapproved = candidate()
    result[0] = FutureOpportunity(0, 'INCONNU', 0, 0, 0)
    unknown = candidate()
    assert unapproved.final_score == unknown.final_score
    assert unapproved.decision_score == unknown.decision_score
    assert unapproved.strategy_scores == unknown.strategy_scores
    assert unapproved.closure_bonus == unknown.closure_bonus
