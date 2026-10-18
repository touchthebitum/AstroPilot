"""A refusal must never attribute clouds from partial or mixed evidence."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from decision.services.refusal_weather_summary import refusal_weather_summary
from decision.weather.provider_reliability import WeatherVariable


def fixture():
    start = datetime(2026, 10, 18, 21, tzinfo=timezone(timedelta(hours=2)))
    points = [NS(forecast_for_utc=start+timedelta(hours=i),
                 retrieved_at_utc=start-timedelta(hours=8), provider_id='fixture',
                 values=(NS(variable=WeatherVariable.CLOUD_COVER_PERCENT, value=100),))
              for i in range(2)]
    candidate = NS(catalog_key='fixture', acquisition_intent_assessments=(
        NS(reason_codes=('insufficient_actionable_productive_window',)),
        NS(reason_codes=('intent_not_targeted_by_project',))))
    return NS(creation_refusal='no_eligible_acquisition_intent',
              recommendation=NS(opportunity=NS(candidate=candidate)),
              night={'object_evaluations':{'fixture':{'window':{'start':start,'end':start+timedelta(hours=2)}}}},
              forecast_evidence=NS(forecast_points=points))


def test_exact_complete_evidence_retains_actual_window_and_source():
    result = fixture()
    summary = refusal_weather_summary(result)
    assert summary.cloud_cover_min == summary.cloud_cover_max == 100
    assert summary.window_start == '2026-10-18T21:00:00+02:00'
    assert summary.provider == 'fixture'


@pytest.mark.parametrize('defect', ['missing_hour','duplicate_hour','mixed_provider',
    'mixed_retrieval','invalid_number','missing_evidence','fractional_window','other_refusal','other_reason'])
def test_uncertain_evidence_never_becomes_weather_explanation(defect):
    result = fixture()
    points = result.forecast_evidence.forecast_points
    if defect == 'missing_hour': points.pop()
    elif defect == 'duplicate_hour': points.append(points[0])
    elif defect == 'mixed_provider': points[1].provider_id = 'other'
    elif defect == 'mixed_retrieval': points[1].retrieved_at_utc += timedelta(minutes=1)
    elif defect == 'invalid_number': points[1].values[0].value = float('nan')
    elif defect == 'missing_evidence': result.forecast_evidence = None
    elif defect == 'fractional_window': result.night['object_evaluations']['fixture']['window']['start'] += timedelta(minutes=15)
    elif defect == 'other_refusal': result.creation_refusal = 'modern_mission_authorization_required'
    elif defect == 'other_reason': result.recommendation.opportunity.candidate.acquisition_intent_assessments[0].reason_codes = ('required_filter_unavailable',)
    assert refusal_weather_summary(result) is None
