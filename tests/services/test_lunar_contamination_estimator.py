import ast
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

import pytest

from decision.definitions.production_filter_optical_profiles import (
    FILTER_OPTICAL_PROFILES,
)
from decision.models.equipment.filter_optical_profile import (
    FilterOpticalProfile,
)
from decision.models.intent_night_evidence import IntentNightEvidence
from decision.services.lunar_contamination_estimator import (
    IncompleteLunarEvidenceError,
    LunarContaminationEstimationError,
    LunarContaminationEstimator,
)


START = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)
END = datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc)


def _evidence(**overrides) -> IntentNightEvidence:
    values = {
        "imaging_field_id": "sh2-129_ou4",
        "actionable_window_start": START,
        "actionable_window_end": END,
        "actionable_duration_hours": 2.0,
        "reference_time": START,
        "moon_illumination": 0.8,
        "moon_altitude_deg": 45.0,
        "moon_separation_deg": 30.0,
    }
    values.update(overrides)
    return IntentNightEvidence(**values)


def _profile(**overrides) -> FilterOpticalProfile:
    values = {
        "filter_profile_id": "synthetic",
        "filter_type": "synthetic",
        "central_wavelength_nm": 550.0,
        "fwhm_nm": 1.0,
        "fast_optics_optimized": False,
    }
    values.update(overrides)
    return FilterOpticalProfile(**values)


@pytest.mark.parametrize(
    ("evidence", "profile"),
    [
        (None, _profile()),
        (object(), _profile()),
        (_evidence(), None),
        (_evidence(), object()),
    ],
)
def test_rejects_wrong_input_types(evidence, profile):
    with pytest.raises(LunarContaminationEstimationError):
        LunarContaminationEstimator().estimate(evidence, profile)


@pytest.mark.parametrize(
    "missing_field",
    ["moon_illumination", "moon_altitude_deg", "moon_separation_deg"],
)
def test_incomplete_lunar_evidence_fails_closed(missing_field):
    with pytest.raises(IncompleteLunarEvidenceError, match=missing_field):
        LunarContaminationEstimator().estimate(
            _evidence(**{missing_field: None}),
            _profile(),
        )


@pytest.mark.parametrize("altitude", [-90.0, -0.1, 0.0])
def test_moon_at_or_below_horizon_returns_only_zeroes(altitude):
    result = LunarContaminationEstimator().estimate(
        _evidence(moon_altitude_deg=altitude),
        _profile(),
    )

    assert result.lunar_source_factor == 0.0
    assert result.rayleigh_relative_index == 0.0
    assert result.mie_relative_index == 0.0


def test_full_moon_is_reference_and_new_moon_is_near_zero():
    estimator = LunarContaminationEstimator()

    full = estimator.estimate(_evidence(moon_illumination=1.0), _profile())
    new = estimator.estimate(_evidence(moon_illumination=0.0), _profile())

    assert full.lunar_source_factor == pytest.approx(1.0)
    assert 0.0 <= new.lunar_source_factor < 0.001


def test_internal_reference_geometry_normalizes_each_component_to_one():
    result = LunarContaminationEstimator().estimate(
        _evidence(
            moon_illumination=1.0,
            moon_altitude_deg=90.0,
            moon_separation_deg=0.0,
        ),
        _profile(central_wavelength_nm=550.0, fwhm_nm=1.0),
    )

    assert result.rayleigh_relative_index == pytest.approx(1.0)
    assert result.mie_relative_index == pytest.approx(1.0)


def test_shorter_wavelength_has_more_rayleigh_at_equal_bandwidth():
    estimator = LunarContaminationEstimator()
    evidence = _evidence()

    oiii = estimator.estimate(
        evidence,
        _profile(central_wavelength_nm=500.7, filter_type="OIII"),
    )
    ha = estimator.estimate(
        evidence,
        _profile(central_wavelength_nm=656.3, filter_type="Ha"),
    )

    assert oiii.rayleigh_relative_index > ha.rayleigh_relative_index


def test_wider_bandwidth_has_more_of_each_relative_component():
    estimator = LunarContaminationEstimator()
    evidence = _evidence()
    narrow = estimator.estimate(evidence, _profile(fwhm_nm=3.0))
    wide = estimator.estimate(evidence, _profile(fwhm_nm=6.5))

    assert wide.rayleigh_relative_index > narrow.rayleigh_relative_index
    assert wide.mie_relative_index > narrow.mie_relative_index


def test_smaller_separation_increases_mie_component():
    estimator = LunarContaminationEstimator()
    profile = _profile()
    close = estimator.estimate(
        _evidence(moon_separation_deg=5.0),
        profile,
    )
    far = estimator.estimate(
        _evidence(moon_separation_deg=90.0),
        profile,
    )

    assert close.mie_relative_index > far.mie_relative_index


def test_higher_moon_altitude_does_not_reduce_components():
    estimator = LunarContaminationEstimator()
    profile = _profile()
    low = estimator.estimate(_evidence(moon_altitude_deg=10.0), profile)
    high = estimator.estimate(_evidence(moon_altitude_deg=70.0), profile)

    assert high.rayleigh_relative_index > low.rayleigh_relative_index
    assert high.mie_relative_index > low.mie_relative_index


def test_filter_type_and_fast_optics_do_not_influence_result():
    estimator = LunarContaminationEstimator()
    evidence = _evidence()
    first = estimator.estimate(
        evidence,
        _profile(filter_type="Ha", fast_optics_optimized=True),
    )
    second = estimator.estimate(
        evidence,
        _profile(filter_type="OIII", fast_optics_optimized=False),
    )

    assert first == second


def test_synthetic_monotonicity_for_each_physical_input():
    estimator = LunarContaminationEstimator()
    profile = _profile()

    dim = estimator.estimate(_evidence(moon_illumination=0.2), profile)
    bright = estimator.estimate(_evidence(moon_illumination=0.9), profile)
    assert bright.lunar_source_factor > dim.lunar_source_factor
    assert bright.rayleigh_relative_index > dim.rayleigh_relative_index
    assert bright.mie_relative_index > dim.mie_relative_index

    evidence = _evidence()
    blue = estimator.estimate(
        evidence,
        _profile(central_wavelength_nm=450.0),
    )
    red = estimator.estimate(evidence, _profile(central_wavelength_nm=700.0))
    assert blue.rayleigh_relative_index > red.rayleigh_relative_index
    assert blue.mie_relative_index > red.mie_relative_index

    for separation in (0.0, 20.0, 60.0, 120.0, 180.0):
        current = estimator.estimate(
            _evidence(moon_separation_deg=separation),
            profile,
        )
        if separation > 0.0:
            assert previous.mie_relative_index > current.mie_relative_index
        previous = current


def test_production_baader_profiles_give_coherent_relative_results():
    estimator = LunarContaminationEstimator()
    evidence = _evidence(
        moon_illumination=0.75,
        moon_altitude_deg=50.0,
        moon_separation_deg=35.0,
    )
    results = {
        profile.filter_type: estimator.estimate(evidence, profile)
        for profile in FILTER_OPTICAL_PROFILES
    }

    assert (
        results["OIII"].rayleigh_relative_index
        > results["Ha"].rayleigh_relative_index
    )
    assert (
        results["Ha"].rayleigh_relative_index
        > results["SII"].rayleigh_relative_index
    )
    assert results["OIII"].mie_relative_index > results["Ha"].mie_relative_index
    assert results["Ha"].mie_relative_index > results["SII"].mie_relative_index
    assert all(result.lunar_source_factor > 0.0 for result in results.values())


def test_service_has_no_legacy_scoring_or_selection_dependency():
    source_path = (
        Path(__file__).resolve().parents[2]
        / "decision"
        / "services"
        / "lunar_contamination_estimator.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = {
        "SkyEngine",
        "CATALOG",
        "moon_penalty",
        "FilterSelectionEngine",
        "ProjectFilterProgress",
    }

    assert imported_names.isdisjoint(forbidden)


def test_v1_exposes_no_combined_or_judgment_field():
    field_names = {
        field.name
        for field in fields(
            LunarContaminationEstimator().estimate(_evidence(), _profile())
        )
    }

    assert field_names.isdisjoint(
        {
            "combined_score",
            "total_contamination",
            "preference",
            "status",
            "quality",
            "confidence",
        }
    )
