from datetime import datetime, timedelta, timezone
from inspect import getsource
from types import SimpleNamespace

import pytest

import astro_score
from decision.validation.decision_consistency import DecisionConsistencyError


EXPLICIT_START = datetime(2026, 9, 10, 22, 15, tzinfo=timezone.utc)
EXPLICIT_END = datetime(2026, 9, 11, 0, 45, tzinfo=timezone.utc)


def complete_best():
    return {
        "start": EXPLICIT_START,
        "end": EXPLICIT_END,
        "clouds": 20,
        "humidity": 60,
        "wind": 5,
        "seeing": 1.5,
        "visibility": 10000,
        "sqm": 21.0,
        "moon_sep": 120,
        "target_altitude": 70,
    }


def setup_profile():
    return {
        "camera_manufacturer": "ZWO",
        "camera_model": "ASI183MM",
        "pixel_size_um": 2.4,
        "sensor_width_px": 5496,
        "sensor_height_px": 3672,
        "monochrome": True,
        "optics_manufacturer": "Samyang",
        "optics_model": "135mm",
        "focal_length_mm": 135,
        "aperture_mm": 48,
        "f_ratio": 2.8,
    }


def build_context(*, best=None):
    return astro_score.build_decision_context(
        obj_name="M31",
        best=complete_best() if best is None else best,
        selected_setup_profile=setup_profile(),
        profile={"preferences": {"bortle": 3}},
        illumination=0.3,
        site_name="Mont Sujet",
        lat=46.7508,
        lon=6.5495,
        bortle=3,
    )


def test_decision_context_uses_selected_project_state(
    monkeypatch,
):
    monkeypatch.setattr(
        astro_score,
        "project_state",
        lambda name, projects: {
            "hours": 3.0,
            "target_hours": 20.0,
            "remaining": 17.0,
            "progress": 15.0,
        },
    )

    monkeypatch.setattr(
        astro_score,
        "project_priority",
        lambda name, projects: 27.2,
    )

    context = astro_score.build_decision_context(
        obj_name="M31",
        best=complete_best(),
        selected_setup_profile=setup_profile(),
        profile={
            "projects": {
                "M31": {},
                "IC1396": {},
            },
            "preferences": {
                "bortle": 3,
                "min_altitude_deg": 42,
                "productive_hours_per_night": 5.5,
            },
            "sessions": [
                {
                    "date": "2026-08-16",
                    "object": "M31",
                    "hours": 2.0,
                },
                {
                    "date": "2026-08-16",
                    "object": "Rosette",
                    "hours": 1.0,
                },
                {
                    "date": "2026-08-17",
                    "object": "IC1396",
                    "hours": 5.0,
                },
                {
                    "date": "2026-08-18",
                    "object": "M31",
                    "hours": 4.0,
                },
            ],
        },
        illumination=0.3,
        site_name="Mont Sujet",
        lat=46.7508,
        lon=6.5495,
        bortle=6,
    )

    assert context.portfolio.active_projects == 2
    assert context.portfolio.total_remaining_hours == 17.0
    assert context.portfolio.highest_priority == 27.2
    assert context.portfolio.average_progress == 15.0
    assert context.portfolio.productive_hours_per_night == 4.0
    assert context.portfolio.night_capacity_source == "history"
    assert context.portfolio.historical_nights == 3
    assert context.preferences.minimum_altitude_deg == 42
    assert context.site.name == "Mont Sujet"
    assert context.site.latitude == 46.7508
    assert context.site.longitude == 6.5495
    assert context.site.bortle == 6

def test_decision_context_session_times_are_timezone_aware():
    context = astro_score.build_decision_context(
        obj_name="M31",
        best=complete_best(),
        selected_setup_profile=setup_profile(),
        profile={
            "preferences": {
                "bortle": 3,
                "observing_nights_per_week": 2.0,
            }
        },
        illumination=0.3,
        site_name="La Chaux-de-Fonds",
        lat=46.7508,
        lon=6.5495,
        bortle=3,
    )

    assert context.portfolio.productive_hours_per_night == 4.0
    assert context.session.start_time.tzinfo is not None
    assert context.session.end_time.tzinfo is not None
    assert context.session.start_time is EXPLICIT_START
    assert context.session.end_time is EXPLICIT_END
    assert context.portfolio.night_capacity_source == "profile"
    assert context.portfolio.historical_nights == 0
    assert (
        context.portfolio.observing_nights_per_week
        == 2.0
)


def test_decision_context_uses_exact_explicit_window_without_current_time():
    context = build_context()
    source = getsource(astro_score.build_decision_context)

    assert context.session.start_time is EXPLICIT_START
    assert context.session.end_time is EXPLICIT_END
    assert context.session.available_duration == timedelta(hours=2, minutes=30)
    assert "datetime.now" not in source
    assert "utcnow" not in source
    assert "timedelta(hours=3)" not in source


@pytest.mark.parametrize("missing_field", ["start", "end"])
def test_missing_decision_timing_fails_without_synthetic_window(missing_field):
    best = complete_best()
    best.pop(missing_field)

    with pytest.raises(DecisionConsistencyError) as caught:
        build_context(best=best)

    assert f"missing_session_{missing_field}" in caught.value.issues


@pytest.mark.parametrize(
    "missing_field",
    ["clouds", "humidity", "wind", "seeing", "visibility"],
)
def test_missing_critical_weather_fails_without_zero_or_favorable_default(
    missing_field,
):
    best = complete_best()
    best.pop(missing_field)

    with pytest.raises(DecisionConsistencyError) as caught:
        build_context(best=best)

    assert f"missing_{missing_field}" in caught.value.issues


def test_complete_explicit_weather_is_preserved_in_decision_context():
    context = build_context()

    assert context.weather.cloud_cover == 20
    assert context.weather.humidity == 60
    assert context.weather.wind_speed_kmh == 5
    assert context.weather.seeing_arcsec == 1.5
    assert context.weather.visibility == 10000


@pytest.mark.parametrize(
    ("missing_field", "expected_issue"),
    [
        ("start", "missing_session_start"),
        ("clouds", "missing_clouds"),
    ],
)
def test_evaluate_object_fails_closed_before_decision_engine_on_incomplete_inputs(
    monkeypatch,
    missing_field,
    expected_issue,
):
    best = {**complete_best(), "score": 80}
    best.pop(missing_field)
    monkeypatch.setattr(
        astro_score,
        "compute_best_window_for_object",
        lambda *args, **kwargs: best,
    )
    monkeypatch.setattr(
        astro_score,
        "select_best_setup_for_object",
        lambda *args, **kwargs: (
            "test_setup",
            20,
            [{"reasons": [], "arcsec_pixel": 2.0}],
        ),
    )
    monkeypatch.setattr(
        astro_score,
        "resolve_equipment_definition",
        lambda profile, setup_name: setup_profile(),
    )
    monkeypatch.setattr(
        astro_score,
        "build_decision_engine",
        lambda: SimpleNamespace(
            evaluate=lambda *args, **kwargs: pytest.fail(
                "decision engine must not evaluate incomplete inputs"
            )
        ),
    )

    with pytest.raises(DecisionConsistencyError) as caught:
        astro_score.evaluate_object(
            "M31",
            object(),
            [],
            0.3,
            SimpleNamespace(name="Mont Sujet"),
            46.7508,
            6.5495,
            3,
            "deep_sky",
            {"projects": {}},
        )

    assert expected_issue in caught.value.issues
