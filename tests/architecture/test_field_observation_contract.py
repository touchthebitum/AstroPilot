from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from decision.field_observation import (
    CaptureMethod,
    CloudState,
    Confidence,
    FieldObservation,
    ObservationProvenance,
    ObservationQuality,
    ObservationSourceType,
    ObservedAcquisition,
    ObservedConditions,
    ObservedTechnical,
    QualityFlag,
    StopReason,
    SurfaceCondition,
    Transparency,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, 17, tzinfo=timezone.utc)
RECORDED_AT = OBSERVED_AT + timedelta(minutes=3)


def observation(**overrides):
    values = {
        "observation_id": "observation-123",
        "decision_id": "decision-123",
        "execution_id": None,
        "observed_at_utc": OBSERVED_AT,
        "recorded_at_utc": RECORDED_AT,
        "supersedes_observation_id": None,
        "conditions": ObservedConditions(cloud_state=CloudState.FEW),
        "acquisition": ObservedAcquisition(),
        "technical": ObservedTechnical(),
        "provenance": ObservationProvenance(
            source_type=ObservationSourceType.USER,
            capture_method=CaptureMethod.MANUAL,
        ),
        "quality": ObservationQuality(
            confidence=Confidence.MEDIUM,
            flags=(QualityFlag.ESTIMATED,),
        ),
    }
    values.update(overrides)
    return FieldObservation(**values)


def test_observation_and_nested_values_are_immutable():
    source = observation()
    with pytest.raises(FrozenInstanceError):
        source.decision_id = "other"
    with pytest.raises(FrozenInstanceError):
        source.conditions.cloud_state = CloudState.CLEAR


def test_minimal_enums_are_exact_string_enums():
    assert {item.value for item in CloudState} == {
        "clear", "few", "partly_cloudy", "mostly_cloudy", "overcast", "unknown"
    }
    assert {item.value for item in SurfaceCondition} == {
        "dry", "damp", "dew_present", "frost_present", "unknown"
    }
    assert {item.value for item in StopReason} == {
        "completed", "clouds", "dew", "wind", "technical", "target_lost",
        "user", "daylight", "not_started", "other", "unknown"
    }


@pytest.mark.parametrize("field", ["observation_id", "decision_id"])
@pytest.mark.parametrize("value", ["", "../escape", "nested/path", ".hidden"])
def test_required_identities_are_safe(field, value):
    with pytest.raises(ValueError, match=f"invalid_{field}"):
        observation(**{field: value})


def test_decision_is_required_and_execution_is_optional():
    assert observation().execution_id is None
    with pytest.raises(ValueError, match="decision_id_required"):
        observation(decision_id=None)


def test_none_means_unknown_and_false_or_zero_are_observed_facts():
    source = observation(
        conditions=ObservedConditions(moon_halo=False),
        acquisition=ObservedAcquisition(attempted_frames=0),
    )
    assert source.conditions.temperature_c is None
    assert source.conditions.moon_halo is False
    assert source.acquisition.attempted_frames == 0


def test_at_least_one_observed_fact_is_required():
    with pytest.raises(ValueError, match="field_observation_value_required"):
        observation(
            conditions=ObservedConditions(),
            acquisition=ObservedAcquisition(),
            technical=ObservedTechnical(),
        )


@pytest.mark.parametrize(
    "factory,code",
    [
        (lambda: ObservedAcquisition(attempted_frames=2, usable_frames=3), "usable_frames_exceed_attempted_frames"),
        (lambda: ObservedAcquisition(usable_frames=1), "usable_frames_requires_attempted_frames"),
    ],
)
def test_frame_counts_are_coherent(factory, code):
    with pytest.raises(ValueError, match=code):
        factory()


@pytest.mark.parametrize(
    "factory,code",
    [
        (lambda: ObservedConditions(relative_humidity_percent=101), "invalid_relative_humidity_percent"),
        (lambda: ObservedConditions(wind_speed_kmh=-0.1), "invalid_wind_speed_kmh"),
        (lambda: ObservedTechnical(guiding_rms_arcsec=float("nan")), "invalid_guiding_rms_arcsec"),
        (lambda: ObservedTechnical(hfr=1.2), "hfr_unit_required"),
        (lambda: ObservedTechnical(hfr_unit="px"), "hfr_unit_without_value"),
    ],
)
def test_numeric_measurements_are_finite_bounded_and_unit_explicit(factory, code):
    with pytest.raises(ValueError, match=code):
        factory()


def test_timestamps_are_normalized_to_utc_and_recording_cannot_precede_observation():
    offset = timezone(timedelta(hours=2))
    source = observation(
        observed_at_utc=OBSERVED_AT.astimezone(offset),
        recorded_at_utc=RECORDED_AT.astimezone(offset),
    )
    assert source.observed_at_utc.tzinfo is timezone.utc
    with pytest.raises(ValueError, match="recorded_at_precedes_observed_at"):
        observation(recorded_at_utc=OBSERVED_AT - timedelta(seconds=1))


def test_self_supersession_is_rejected():
    with pytest.raises(ValueError, match="observation_cannot_supersede_itself"):
        observation(supersedes_observation_id="observation-123")


def test_quality_flags_are_immutable_unique_and_strict():
    with pytest.raises(ValueError, match="duplicate_quality_flags"):
        ObservationQuality(
            flags=(QualityFlag.PARTIAL, QualityFlag.PARTIAL)
        )
    assert observation().calibration_eligible is True


def test_technical_units_and_compatibility_read_properties():
    source = observation(
        conditions=ObservedConditions(
            cloud_state=CloudState.CLEAR,
            transparency=Transparency.GOOD,
            surface_condition=SurfaceCondition.DRY,
        ),
        technical=ObservedTechnical(
            hfr=2.1,
            hfr_unit="px",
            sky_background=850,
            sky_background_unit="adu",
        ),
    )
    assert source.cloud_condition is CloudState.CLEAR
    assert source.transparency is Transparency.GOOD
    assert source.dew_detected is False
