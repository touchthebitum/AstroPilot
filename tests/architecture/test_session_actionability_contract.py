from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from decision.mission.mission_assembler import (
    ProductiveWindowAssessment,
    _mission_timing_for_availability,
)
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.night_productivity.night_window_merger import NightWindowMerger
from decision.services.candidate_assessment import (
    CandidateAssessment,
    CandidateViabilityEvaluator,
    select_actionable_alternatives,
)
from decision.services.session_availability_windowing import (
    MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW,
    select_continuous_actionable_productive_window,
)
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)


START = datetime(2026, 9, 20, 3, tzinfo=timezone(timedelta(hours=2)))


def assessment(scores, *, slice_duration=timedelta(minutes=15)):
    slice_hours = slice_duration.total_seconds() / 3600
    slices = tuple(
        SimpleNamespace(
            start_hour=index * slice_hours,
            end_hour=(index + 1) * slice_hours,
            productivity_score=score,
            target_altitude=70.0,
            cloud_cover=0.0 if score >= 0.70 else 80.0,
            moon_penalty=0.0,
            seeing=1.5,
        )
        for index, score in enumerate(scores)
    )
    total_hours = len(slices) * slice_hours
    weighted_hours = round(
        sum(
            (slice_.end_hour - slice_.start_hour)
            * slice_.productivity_score
            for slice_ in slices
        ),
        2,
    )
    return ProductiveWindowAssessment(
        window_start=START,
        window_end=START + timedelta(hours=total_hours),
        recommended_hours=weighted_hours,
        expected_gain=0.0,
        productivity=SimpleNamespace(
            astronomical_hours=total_hours,
            productive_hours=weighted_hours,
            confidence=(
                round(weighted_hours / total_hours, 2) if total_hours else 0.0
            ),
            windows=NightWindowMerger.merge(SimpleNamespace(slices=slices)),
            timeline=slices,
        ),
    )


def candidate(source, admissibility=WeatherDecisionAdmissibility.ADMISSIBLE):
    return CandidateAssessment(
        productive_window=source,
        weather_decision=WeatherTrustDecision(
            evidence_quality=WeatherEvidenceQuality.SUFFICIENT,
            admissibility=admissibility,
            reasons=(),
        ),
    )


def test_soul_weighted_equivalent_does_not_create_an_actionable_window():
    soul = assessment([0.713, 0.44, 0.44, 0.44, 0.44, 0.44, 0.44, 0.44])

    assert MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW == timedelta(hours=1)
    assert soul.productivity.astronomical_hours == 2.0
    assert soul.productivity.productive_hours == pytest.approx(0.95)
    assert len(soul.productivity.windows) == 1
    assert soul.productivity.windows[0].end_hour - soul.productivity.windows[0].start_hour == 0.25
    assert select_continuous_actionable_productive_window(soul, None) is None
    assert CandidateViabilityEvaluator.is_viable(candidate(soul)) is False
    assert _mission_timing_for_availability(soul, None) is None


@pytest.mark.parametrize(
    ("slice_duration", "expected_actionable"),
    (
        (timedelta(seconds=3599), False),
        (timedelta(minutes=60), True),
        (timedelta(minutes=75), True),
    ),
)
def test_continuous_minimum_is_inclusive_at_exactly_sixty_minutes(
    slice_duration,
    expected_actionable,
):
    source = assessment([0.8], slice_duration=slice_duration)

    selected = select_continuous_actionable_productive_window(source, None)

    assert (selected is not None) is expected_actionable
    assert CandidateViabilityEvaluator.is_viable(candidate(source)) is expected_actionable


def test_separated_productive_windows_are_never_summed_to_reach_minimum():
    source = assessment([1.0, 1.0, 0.2, 1.0, 1.0])

    assert source.productivity.productive_hours > 1.0
    assert [
        window.end_hour - window.start_hour
        for window in source.productivity.windows
    ] == [0.5, 0.5]
    assert select_continuous_actionable_productive_window(source, None) is None


def test_fixed_availability_applies_minimum_after_intersection():
    source = assessment([0.8] * 6)
    truncated = SessionAvailability(
        SessionAvailabilityMode.FIXED_WINDOW,
        start=START,
        end=START + timedelta(minutes=59),
    )
    retained = SessionAvailability(
        SessionAvailabilityMode.FIXED_WINDOW,
        start=START + timedelta(minutes=15),
        end=START + timedelta(minutes=75),
    )

    assert select_continuous_actionable_productive_window(source, truncated) is None
    selected = select_continuous_actionable_productive_window(source, retained)
    assert selected.window_start == retained.start
    assert selected.window_end == retained.end


def test_weather_caution_preserves_actionability_and_refused_blocks_it():
    source = assessment([0.8] * 4)

    assert CandidateViabilityEvaluator.is_viable(candidate(
        source,
        WeatherDecisionAdmissibility.CAUTION,
    )) is True
    assert CandidateViabilityEvaluator.is_viable(candidate(
        source,
        WeatherDecisionAdmissibility.REFUSED,
    )) is False


def test_only_candidates_with_a_continuous_hour_are_exposed_as_alternatives():
    primary = SimpleNamespace(catalog_key="IC1396")
    soul = SimpleNamespace(catalog_key="Soul")
    actionable = SimpleNamespace(catalog_key="M31")
    assessments = {
        "Soul": candidate(
            assessment([0.713, 0.44, 0.44, 0.44, 0.44, 0.44, 0.44, 0.44])
        ),
        "M31": candidate(assessment([0.8] * 4)),
    }

    alternatives = select_actionable_alternatives(
        (primary, soul, actionable),
        {"Soul", "M31"},
        assessments,
        SessionAvailability(SessionAvailabilityMode.ALL_NIGHT),
        primary_catalog_key="IC1396",
    )

    assert alternatives == (actionable,)


def test_classic_ui_never_labels_weighted_productivity_as_real_duration():
    script = (
        __import__("pathlib").Path(__file__).parents[2]
        / "astropilot"
        / "web"
        / "app.js"
    ).read_text(encoding="utf-8")

    assert "productive_hours ?? decision.recommended_hours" not in script
    assert 'const actionableHours = decision.recommended_hours' in script
    assert '"Durée de mission exploitable"' in script
