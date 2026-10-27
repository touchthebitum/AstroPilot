"""Existing scores restricted to availability; eligibility thresholds stay unchanged."""
from dataclasses import replace
from datetime import timedelta, timezone
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.night_productivity.productivity_diagnostics import ProductivityLosses, SliceProductivityEvaluation
from decision.night_productivity.refusal_evidence_scope import scoped_refusal_breakdown, ProductivityEvidenceScope
from decision.services.session_availability_windowing import evaluate_physical_productive_window
from datetime import datetime

START = datetime(2026, 10, 28, 4, tzinfo=timezone(timedelta(hours=1)))
AVAIL = SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW,
    start=START-timedelta(hours=2, minutes=28), end=START+timedelta(hours=1, minutes=27))


def window(scores):
    evaluations = tuple(SliceProductivityEvaluation(s, ProductivityLosses(1-s, 0, 0, 0, 0)) for s in scores)
    slices = [NS(start_hour=i/4, end_hour=(i+1)/4, productivity_score=s) for i,s in enumerate(scores)]
    windows=[]
    for i,s in enumerate(scores):
        if s < .7: continue
        if windows and windows[-1].end_hour == i/4:
            windows[-1].end_hour=(i+1)/4
        else: windows.append(NS(start_hour=i/4, end_hour=(i+1)/4, productivity=.9, productive=True))
    return ProductiveWindowAssessment(START, START+timedelta(hours=2), 2, 0,
        NS(windows=windows, timeline=NS(slices=slices)), productivity_slice_evaluations=evaluations)


@pytest.mark.parametrize('scores,stage,minutes', [
    ([.2]*8, 'no_productive_slice', 0),
    ([.2]*6+[.9]*2, 'no_productive_slice', 0),
    ([.2]*2+[.9]*4+[.2]*2, 'continuous_window_too_short', 57),
    ([.2]*4+[.9]*4, 'continuous_window_too_short', 27),
    ([.9]*6+[.2]*2, None, 87),
    ([.9]*4+[.2]*4, None, 60),
])
def test_operator_bounds_and_unchanged_sixty_minute_rule(scores, stage, minutes):
    outcome = evaluate_physical_productive_window(window(scores), AVAIL)
    if stage is None:
        assert outcome.refusal is None
        assert (outcome.window.window_end-outcome.window.window_start).total_seconds()/60 == minutes
    else:
        refusal=outcome.refusal
        assert refusal.refusal_stage.value == stage
        assert refusal.best_productive_window_minutes == minutes
        assert refusal.required_continuous_minutes == 60
        assert refusal.evidence_scope.evaluated_end == AVAIL.end
        assert refusal.productivity_breakdown.evaluated_slice_count == 6
        assert refusal.evidence_scope.partial_slice_count == 1
        assert refusal.productivity_breakdown.best_slice_score == max(scores[:6])
        assert refusal.productivity_breakdown.productive_slice_count == sum(s>=.7 for s in scores[:6])


def test_partial_both_bounds_keep_original_score_losses_and_source_times():
    assessment=window([.2,.3,.4,.5,.6,.65,.95,.99])
    lo,hi=START+timedelta(minutes=7),START+timedelta(minutes=87)
    breakdown,scope=scoped_refusal_breakdown(assessment,lo,hi)
    assert scope.partial_slice_count == 2
    assert breakdown.best_slice_score == .65
    assert breakdown.losses is assessment.productivity_slice_evaluations[5].losses
    assert breakdown.best_slice_end == hi
    assert scope.best_source_slice_end == START+timedelta(minutes=90)
    assert scope.best_source_slice_start == START+timedelta(minutes=75)
    assert scope.score_policy == 'reuse_source_slice_scores'
    assert breakdown.evaluated_slice_count == 6


def test_no_overlap_has_no_best_score_or_losses():
    availability=replace(AVAIL,end=START-timedelta(minutes=1))
    refusal=evaluate_physical_productive_window(window([.9]*8),availability).refusal
    assert refusal.refusal_stage.value == 'no_productive_slice'
    assert refusal.productivity_breakdown.evaluated_slice_count == 0
    assert refusal.productivity_breakdown.best_slice_score is None
    assert refusal.productivity_breakdown.losses is None
    assert refusal.evidence_scope.evaluated_start is None


def test_missing_or_inconsistent_slice_provenance_never_borrows_global_losses():
    assessment=window([.2]*8)
    for malformed in (replace(assessment,productivity_slice_evaluations=()),
                      replace(assessment,productivity_slice_evaluations=assessment.productivity_slice_evaluations[:1])):
        breakdown,scope=scoped_refusal_breakdown(malformed,AVAIL.start,AVAIL.end)
        assert breakdown is None and scope.partial_slice_count is None


def test_scope_intersection_validates_absolute_times_at_dst_fold():
    zone=ZoneInfo('Europe/Zurich')
    start=datetime(2026,10,25,2,0,tzinfo=zone,fold=0)
    end=datetime(2026,10,25,3,0,tzinfo=zone)
    lo=datetime(2026,10,25,2,30,tzinfo=zone,fold=1)
    scope=ProductivityEvidenceScope(start,end,lo,end,lo,end)
    assert scope.evaluated_start.fold == 1
    with pytest.raises(ValueError,match='scope_intersection_mismatch'):
        replace(scope,evaluated_start=lo.replace(fold=0))


def test_real_engine_keeps_single_pass_slice_provenance(monkeypatch):
    from decision.night_productivity.night_productivity_engine import NightProductivityEngine
    from decision.night_productivity.night_productivity_context import NightProductivityContext
    from decision.night_productivity.night_timeline_builder import NightTimelineBuilder
    monkeypatch.setattr('decision.night_productivity.night_timeline_builder.NightConditionsProvider.altitude',lambda *_:75.)
    monkeypatch.setattr('decision.night_productivity.night_timeline_builder.NightConditionsProvider.moon_penalty',lambda *_:0.)
    original=NightTimelineBuilder._evaluate_productivity
    calls=[]
    def evaluated(**kwargs):
        value=original(**kwargs)
        calls.append(value)
        return value
    monkeypatch.setattr(NightTimelineBuilder,'_evaluate_productivity',staticmethod(evaluated))
    evaluated=NightProductivityEngine.evaluate_with_breakdown(NightProductivityContext(
        astronomical_hours=2,cloud_cover=100,moon_penalty=0,altitude_score=8,
        humidity=95,wind=0,seeing=1.5,observation_time=START))
    assessment=replace(window([.2]*8),productivity=evaluated.result,
        productivity_breakdown=evaluated.breakdown,productivity_slice_evaluations=evaluated.slice_evaluations)
    refusal=evaluate_physical_productive_window(assessment,AVAIL).refusal
    assert len(calls)==8
    assert refusal.productivity_breakdown.evaluated_slice_count==6
    assert refusal.productivity_breakdown.losses is evaluated.slice_evaluations[0].losses
    assert len(calls)==8  # Diagnostic clipping cannot call the scoring model again.
