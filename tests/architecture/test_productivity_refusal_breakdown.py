from dataclasses import fields
from datetime import datetime, timedelta, timezone
from inspect import signature
from types import SimpleNamespace

import pytest

from decision.acceptance_lineage_persistence import SCHEMA_VERSION
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.night_productivity.night_productivity_context import (
    NightProductivityContext,
)
from decision.night_productivity.night_productivity_engine import (
    NightProductivityEngine,
)
from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)
from decision.night_productivity.night_slice import NightSlice
from decision.night_productivity.night_timeline_builder import (
    NightTimelineBuilder,
)
from decision.night_productivity.night_window_builder import NightWindowBuilder
from decision.night_productivity.night_window_merger import NightWindowMerger
from decision.night_productivity.productivity_diagnostics import (
    PRODUCTIVE_SLICE_THRESHOLD,
    ProductivityBreakdown,
    ProductivityLosses,
)
from decision.services.session_availability_windowing import (
    ActionabilityRefusalStatus,
    ProductivityRefusalStage,
    evaluate_continuous_actionable_productive_window,
)


START = datetime(2026, 9, 24, 22, tzinfo=timezone(timedelta(hours=2)))


def _slice(score: float, start: float = 0.0, end: float = 0.25):
    return SimpleNamespace(
        start_hour=start,
        end_hour=end,
        productivity_score=score,
        target_altitude=70.0,
        cloud_cover=0.0,
        moon_penalty=0.0,
        seeing=1.5,
    )


def _breakdown(*, productive_count: int) -> ProductivityBreakdown:
    return ProductivityBreakdown(
        evaluated_slice_count=8,
        productive_slice_count=productive_count,
        best_slice_start=START + timedelta(minutes=15),
        best_slice_end=START + timedelta(minutes=30),
        best_slice_score=0.394 if productive_count == 0 else 0.8,
        best_slice_tie_count=7 if productive_count == 0 else 1,
        productive_slice_threshold=PRODUCTIVE_SLICE_THRESHOLD,
        losses=ProductivityLosses(
            cloud=0.497,
            moon=0.109,
            altitude=0.0,
            humidity=0.0,
            wind=0.0,
        ),
    )


def test_slice_evaluation_is_single_authority_for_score_and_five_losses():
    evaluation = NightTimelineBuilder._evaluate_productivity(
        cloud_cover=71.0,
        moon_penalty=0.545,
        target_altitude=70.0,
        humidity=72.0,
        wind=2.9,
    )

    assert evaluation.losses == ProductivityLosses(
        cloud=pytest.approx(0.497),
        moon=pytest.approx(0.109),
        altitude=0.0,
        humidity=0.0,
        wind=0.0,
    )
    assert evaluation.score == pytest.approx(
        1.0
        - evaluation.losses.cloud
        - evaluation.losses.moon
        - evaluation.losses.altitude
        - evaluation.losses.humidity
        - evaluation.losses.wind
    )
    assert NightTimelineBuilder._compute_productivity(
        71.0, 0.545, 70.0, 72.0, 2.9
    ) == evaluation.score


@pytest.mark.parametrize(
    ("altitude", "humidity", "wind", "expected"),
    (
        (30.0, 85.0, 20.0, (0.10, 0.0, 0.0)),
        (29.999, 85.001, 20.001, (0.25, 0.15, 0.15)),
        (49.999, 50.0, 5.0, (0.10, 0.0, 0.0)),
        (50.0, 50.0, 5.0, (0.0, 0.0, 0.0)),
    ),
)
def test_loss_thresholds_are_exact(altitude, humidity, wind, expected):
    evaluation = NightTimelineBuilder._evaluate_productivity(
        0.0, 0.0, altitude, humidity, wind
    )
    assert (
        evaluation.losses.altitude,
        evaluation.losses.humidity,
        evaluation.losses.wind,
    ) == expected


def test_losses_can_exceed_one_while_score_clamps_and_seeing_is_not_an_input():
    evaluation = NightTimelineBuilder._evaluate_productivity(
        100.0, 1.0, 20.0, 90.0, 25.0
    )
    assert (
        evaluation.losses.cloud
        + evaluation.losses.moon
        + evaluation.losses.altitude
        + evaluation.losses.humidity
        + evaluation.losses.wind
    ) > 1.0
    assert evaluation.score == 0.0
    assert "seeing" not in signature(
        NightTimelineBuilder._evaluate_productivity
    ).parameters


def test_productive_threshold_is_shared_and_inclusive():
    timeline = SimpleNamespace(slices=[_slice(PRODUCTIVE_SLICE_THRESHOLD)])

    assert NightWindowMerger.DEFAULT_THRESHOLD == 0.70
    assert len(NightWindowMerger.merge(timeline)) == 1
    assert NightWindowBuilder.build(None, timeline)[0].productive is True


def test_reference_case_selects_first_of_seven_exact_ties_without_ranking_effect(
    monkeypatch,
):
    monkeypatch.setattr(
        "decision.night_productivity.night_timeline_builder."
        "NightConditionsProvider.cloud",
        lambda current, _context: 80.0 if current == 0 else 71.0,
    )
    monkeypatch.setattr(
        "decision.night_productivity.night_timeline_builder."
        "NightConditionsProvider.humidity",
        lambda *_: 72.0,
    )
    monkeypatch.setattr(
        "decision.night_productivity.night_timeline_builder."
        "NightConditionsProvider.wind",
        lambda *_: 2.9,
    )
    monkeypatch.setattr(
        "decision.night_productivity.night_timeline_builder."
        "NightConditionsProvider.seeing",
        lambda *_: 99.0,
    )
    monkeypatch.setattr(
        "decision.night_productivity.night_timeline_builder."
        "NightConditionsProvider.altitude",
        lambda *_: 75.0,
    )
    monkeypatch.setattr(
        "decision.night_productivity.night_timeline_builder."
        "NightConditionsProvider.moon_penalty",
        lambda *_: 0.545,
    )
    context = NightProductivityContext(
        astronomical_hours=2.0,
        cloud_cover=71.0,
        moon_penalty=0.545,
        altitude_score=8.0,
        humidity=72.0,
        wind=2.9,
        seeing=99.0,
        observation_time=START,
    )

    evaluation = NightProductivityEngine.evaluate_with_breakdown(context)
    ordinary_result = NightProductivityEngine.evaluate(context)
    breakdown = evaluation.breakdown

    assert breakdown is not None
    assert breakdown.evaluated_slice_count == 8
    assert breakdown.productive_slice_count == 0
    assert breakdown.best_slice_score == pytest.approx(0.394)
    assert breakdown.best_slice_start == START + timedelta(minutes=15)
    assert breakdown.best_slice_end == START + timedelta(minutes=30)
    assert breakdown.best_slice_tie_count == 7
    assert breakdown.losses.cloud == pytest.approx(0.497)
    assert breakdown.losses.moon == pytest.approx(0.109)
    assert evaluation.result.windows == ordinary_result.windows == []
    assert [item.productivity_score for item in evaluation.result.timeline.slices] == [
        item.productivity_score for item in ordinary_result.timeline.slices
    ]


def test_refusal_stage_and_breakdown_are_attached_after_constraints():
    breakdown = _breakdown(productive_count=4)
    slices = tuple(_slice(0.8, index * 0.25, (index + 1) * 0.25) for index in range(4))
    assessment = ProductiveWindowAssessment(
        window_start=START,
        window_end=START + timedelta(hours=1),
        recommended_hours=1.0,
        expected_gain=1.0,
        productivity=SimpleNamespace(
            windows=NightWindowMerger.merge(SimpleNamespace(slices=slices)),
            timeline=slices,
        ),
        productivity_breakdown=breakdown,
    )
    availability = SessionAvailability(
        SessionAvailabilityMode.DURATION,
        duration=timedelta(minutes=45),
    )

    refusal = evaluate_continuous_actionable_productive_window(
        assessment, availability
    ).refusal

    assert refusal.status is ActionabilityRefusalStatus.CONSTRAINTS_REFUSAL
    assert refusal.refusal_stage is ProductivityRefusalStage.CONTINUOUS_WINDOW_TOO_SHORT
    assert refusal.productivity_breakdown is breakdown
    assert refusal.best_productive_window_minutes == 45
    assert refusal.limiting_factors == ()


def test_insufficient_evidence_has_no_stage_or_causal_breakdown():
    assessment = ProductiveWindowAssessment(
        window_start=None,
        window_end=None,
        recommended_hours=0.0,
        expected_gain=0.0,
        productivity=SimpleNamespace(windows=None),
        productivity_breakdown=_breakdown(productive_count=0),
    )

    refusal = evaluate_continuous_actionable_productive_window(
        assessment, None
    ).refusal

    assert refusal.status is ActionabilityRefusalStatus.INSUFFICIENT_EVIDENCE
    assert refusal.refusal_stage is None
    assert refusal.productivity_breakdown is None


def test_persistent_lineage_productivity_structures_and_schema_are_unchanged():
    assert SCHEMA_VERSION == 9
    assert [item.name for item in fields(NightSlice)] == [
        "start_hour", "end_hour", "target_altitude", "target_azimuth",
        "moon_altitude", "moon_separation", "moon_penalty", "cloud_cover",
        "humidity", "wind", "seeing", "sqm", "astro_score",
        "conditions_score", "productivity_score",
    ]
    assert [item.name for item in fields(NightProductivityResult)] == [
        "astronomical_hours", "productive_hours", "confidence", "cloud_loss",
        "moon_loss", "altitude_loss", "weather_loss", "windows", "timeline",
        "display_start_hour",
    ]
