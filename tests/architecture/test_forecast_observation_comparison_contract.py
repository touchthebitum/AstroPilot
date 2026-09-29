import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
    SeeingCondition,
    SurfaceCondition,
    Transparency,
)
from decision.models.forecast_observation_comparison import (
    CloudComparisonOutcome,
    CloudMappingComparisonPolicy,
    CloudVariableComparison,
    ForecastObservationComparisonStatus,
    ForecastObservationParameters,
    NumericVariableComparison,
    TemporalComparisonPolicy,
    VariableComparisonStatus,
)
from decision.services.forecast_observation_comparison import (
    ForecastObservationComparisonInputError,
    compare_forecast_to_field_observation,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, 0, tzinfo=timezone.utc)
COMPUTED_AT = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
RETRIEVED_AT = OBSERVED_AT - timedelta(hours=4)
LOCATION = WeatherLocation(46.7508, 6.5495, altitude_m=1245.0)
SERVICE_PATH = (
    Path(__file__).parents[2]
    / "decision"
    / "services"
    / "forecast_observation_comparison.py"
)


def observation(
    *,
    observed_at=OBSERVED_AT,
    decision_id="decision-123",
    execution_id="execution-123",
    conditions=None,
    flags=(),
    confidence=Confidence.HIGH,
):
    conditions = conditions or ObservedConditions(temperature_c=8.0)
    return FieldObservation(
        observation_id="observation-123",
        decision_id=decision_id,
        execution_id=execution_id,
        observed_at_utc=observed_at,
        recorded_at_utc=(
            observed_at.astimezone(timezone.utc) + timedelta(minutes=1)
        ),
        supersedes_observation_id=None,
        conditions=conditions,
        acquisition=ObservedAcquisition(),
        technical=ObservedTechnical(),
        provenance=ObservationProvenance(
            source_type=ObservationSourceType.WEATHER_STATION,
            capture_method=CaptureMethod.AUTOMATIC,
            source_id="station-42",
        ),
        quality=ObservationQuality(confidence=confidence, flags=tuple(flags)),
    )


def legacy_observation():
    return observation(
        decision_id=None,
        execution_id=None,
        flags=(QualityFlag.LEGACY_LINEAGE_INCOMPLETE,),
    )


def point(
    variable,
    value,
    *,
    offset=timedelta(0),
    forecast_for=None,
    retrieved_at=RETRIEVED_AT,
    provider="open_meteo",
    model="best_match",
):
    return WeatherForecastPoint(
        provider_id=provider,
        model_id=model,
        retrieved_at_utc=retrieved_at,
        forecast_for_utc=forecast_for or OBSERVED_AT + offset,
        requested_location=LOCATION,
        grid_location=LOCATION,
        values=(
            WeatherValue(
                variable=variable,
                value=value,
                unit={
                    WeatherVariable.TEMPERATURE_C: "°C",
                    WeatherVariable.RELATIVE_HUMIDITY_PERCENT: "%",
                    WeatherVariable.WIND_SPEED_KMH: "km/h",
                    WeatherVariable.CLOUD_COVER_PERCENT: "%",
                    WeatherVariable.DEW_POINT_C: "°C",
                }[variable],
            ),
        ),
    )


def compare(source, *points, **overrides):
    return compare_forecast_to_field_observation(
        DecisionForecastEvidence(tuple(points)),
        source,
        computed_at_utc=COMPUTED_AT,
        **overrides,
    )


def result_for(comparison, variable):
    return next(result for result in comparison.results if result.variable is variable)


def reason_codes(comparison):
    return tuple(reason.code for reason in comparison.reasons)


def test_exact_point_produces_typed_immutable_numeric_result_and_provenance():
    source = observation(conditions=ObservedConditions(temperature_c=7.0))

    result = compare(
        source,
        point(WeatherVariable.TEMPERATURE_C, 8.5),
    )

    temperature = result_for(result, WeatherVariable.TEMPERATURE_C)
    assert result.status is ForecastObservationComparisonStatus.COMPARABLE
    assert result.algorithm_version == "forecast_observation.v1"
    assert result.forecast_scope == "decision_attached_evidence"
    assert result.decision_id == source.decision_id
    assert result.observation_id == source.observation_id
    assert result.execution_id == source.execution_id
    assert len(result.source_digest) == 64
    assert isinstance(temperature, NumericVariableComparison)
    assert temperature.forecast_point.forecast_for_utc == OBSERVED_AT
    assert temperature.forecast_point.temporal_offset == timedelta(0)
    assert temperature.forecast_point.provider_id == "open_meteo"
    assert result.observation_provenance.source_id == "station-42"
    with pytest.raises(FrozenInstanceError):
        result.status = ForecastObservationComparisonStatus.PARTIAL


@pytest.mark.parametrize("minutes", [-11, 9])
def test_selects_nearest_point_before_or_after(minutes):
    source = observation()
    farther = point(
        WeatherVariable.TEMPERATURE_C,
        1.0,
        offset=timedelta(minutes=-20 if minutes > 0 else 20),
    )
    nearest = point(
        WeatherVariable.TEMPERATURE_C,
        9.0,
        offset=timedelta(minutes=minutes),
    )

    result = compare(source, farther, nearest)

    selected = result_for(result, WeatherVariable.TEMPERATURE_C)
    assert selected.forecast_value == 9.0
    assert selected.forecast_point.temporal_offset == timedelta(minutes=minutes)


@pytest.mark.parametrize("minutes", [-30, 30])
def test_inclusive_thirty_minute_boundary_is_comparable(minutes):
    result = compare(
        observation(),
        point(
            WeatherVariable.TEMPERATURE_C,
            8.0,
            offset=timedelta(minutes=minutes),
        ),
    )

    assert result.status is ForecastObservationComparisonStatus.COMPARABLE


def test_thirty_minutes_plus_one_microsecond_is_rejected():
    result = compare(
        observation(),
        point(
            WeatherVariable.TEMPERATURE_C,
            8.0,
            offset=timedelta(minutes=30, microseconds=1),
        ),
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("forecast_outside_temporal_tolerance",)


def test_equal_before_and_after_is_fail_closed_for_variable():
    result = compare(
        observation(),
        point(
            WeatherVariable.TEMPERATURE_C,
            7.0,
            offset=timedelta(minutes=-5),
        ),
        point(
            WeatherVariable.TEMPERATURE_C,
            9.0,
            offset=timedelta(minutes=5),
        ),
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("ambiguous_nearest_forecast",)


def test_conflicting_values_at_same_timestamp_are_ambiguous():
    result = compare(
        observation(),
        point(WeatherVariable.TEMPERATURE_C, 7.0),
        point(WeatherVariable.TEMPERATURE_C, 9.0),
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("ambiguous_nearest_forecast",)


def test_strictly_identical_duplicates_are_deduplicated():
    duplicate = point(WeatherVariable.TEMPERATURE_C, 9.0)

    single = compare(observation(), duplicate)
    repeated = compare(observation(), duplicate, duplicate)

    assert repeated.status is ForecastObservationComparisonStatus.COMPARABLE
    assert repeated.results == single.results
    assert repeated.source_digest == single.source_digest
    assert repeated.comparison_id == single.comparison_id


def test_selection_is_independent_for_each_variable():
    source = observation(
        conditions=ObservedConditions(
            temperature_c=8.0,
            relative_humidity_percent=80.0,
        )
    )

    result = compare(
        source,
        point(
            WeatherVariable.TEMPERATURE_C,
            7.0,
            offset=timedelta(minutes=-4),
        ),
        point(
            WeatherVariable.TEMPERATURE_C,
            20.0,
            offset=timedelta(minutes=12),
        ),
        point(
            WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
            20.0,
            offset=timedelta(minutes=-15),
        ),
        point(
            WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
            82.0,
            offset=timedelta(minutes=3),
        ),
    )

    temperature = result_for(result, WeatherVariable.TEMPERATURE_C)
    humidity = result_for(result, WeatherVariable.RELATIVE_HUMIDITY_PERCENT)
    assert temperature.forecast_value == 7.0
    assert temperature.forecast_point.temporal_offset == timedelta(minutes=-4)
    assert humidity.forecast_value == 82.0
    assert humidity.forecast_point.temporal_offset == timedelta(minutes=3)


@pytest.mark.parametrize(
    ("variable", "forecast", "observed", "signed", "absolute", "unit"),
    [
        (WeatherVariable.TEMPERATURE_C, -8.0, -5.0, -3.0, 3.0, "°C"),
        (WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 100.0, 0.0, 100.0, 100.0, "%"),
        (WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 0.0, 100.0, -100.0, 100.0, "%"),
        (WeatherVariable.WIND_SPEED_KMH, 0.0, 0.0, 0.0, 0.0, "km/h"),
    ],
)
def test_numeric_errors_use_exact_forecast_minus_observed_formula(
    variable,
    forecast,
    observed,
    signed,
    absolute,
    unit,
):
    condition_arguments = {
        WeatherVariable.TEMPERATURE_C: {"temperature_c": observed},
        WeatherVariable.RELATIVE_HUMIDITY_PERCENT: {
            "relative_humidity_percent": observed
        },
        WeatherVariable.WIND_SPEED_KMH: {"wind_speed_kmh": observed},
    }[variable]

    result = compare(
        observation(conditions=ObservedConditions(**condition_arguments)),
        point(variable, forecast),
    )

    numeric = result_for(result, variable)
    assert numeric.unit == unit
    assert numeric.signed_error == signed
    assert numeric.absolute_error == absolute


@pytest.mark.parametrize(
    ("coverage", "expected"),
    [
        (9.999, CloudState.CLEAR),
        (10.0, CloudState.FEW),
        (24.999, CloudState.FEW),
        (25.0, CloudState.PARTLY_CLOUDY),
        (49.999, CloudState.PARTLY_CLOUDY),
        (50.0, CloudState.MOSTLY_CLOUDY),
        (79.999, CloudState.MOSTLY_CLOUDY),
        (80.0, CloudState.OVERCAST),
    ],
)
def test_cloud_mapping_boundaries_are_reused(coverage, expected):
    result = compare(
        observation(conditions=ObservedConditions(cloud_state=expected)),
        point(WeatherVariable.CLOUD_COVER_PERCENT, coverage),
    )

    cloud = result_for(result, WeatherVariable.CLOUD_COVER_PERCENT)
    assert cloud.predicted_condition is expected
    assert cloud.outcome is CloudComparisonOutcome.MATCH
    assert cloud.confusion_cell == (expected, expected)


def test_cloud_mismatch_and_confusion_cell_are_factual():
    result = compare(
        observation(
            conditions=ObservedConditions(cloud_state=CloudState.OVERCAST)
        ),
        point(WeatherVariable.CLOUD_COVER_PERCENT, 12.0),
    )

    cloud = result_for(result, WeatherVariable.CLOUD_COVER_PERCENT)
    assert isinstance(cloud, CloudVariableComparison)
    assert cloud.outcome is CloudComparisonOutcome.MISMATCH
    assert cloud.confusion_cell == (CloudState.FEW, CloudState.OVERCAST)
    assert not hasattr(result, "score")
    assert not hasattr(cloud, "accurate")


def test_unknown_observed_cloud_is_not_comparable_but_other_variable_can_be():
    source = observation(
        conditions=ObservedConditions(
            temperature_c=8.0,
            cloud_state=CloudState.UNKNOWN,
        )
    )

    result = compare(
        source,
        point(WeatherVariable.TEMPERATURE_C, 8.0),
        point(WeatherVariable.CLOUD_COVER_PERCENT, 5.0),
    )

    cloud = result_for(result, WeatherVariable.CLOUD_COVER_PERCENT)
    assert result.status is ForecastObservationComparisonStatus.PARTIAL
    assert cloud.status is VariableComparisonStatus.NOT_COMPARABLE
    assert cloud.reasons[0].code == "observed_cloud_unknown"


@pytest.mark.parametrize(
    ("evidence", "expected_reason"),
    [
        (None, "decision_forecast_evidence_missing"),
        (DecisionForecastEvidence(()), "decision_forecast_evidence_empty"),
        ("corrupt", "decision_forecast_evidence_invalid"),
    ],
)
def test_missing_empty_or_invalid_evidence_returns_structured_reason(
    evidence,
    expected_reason,
):
    result = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == (expected_reason,)
    assert result.results[0].reasons[0].code == expected_reason


def test_malformed_evidence_container_returns_structured_invalid_reason():
    corrupted = DecisionForecastEvidence(())
    object.__setattr__(corrupted, "forecast_points", ("not-a-point",))

    result = compare_forecast_to_field_observation(
        corrupted,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)


@pytest.mark.parametrize(
    ("source", "expected_reasons"),
    [
        (legacy_observation(), ("legacy_lineage_incomplete",)),
        (
            observation(flags=(QualityFlag.TIME_UNCERTAIN,)),
            ("observation_time_uncertain",),
        ),
        (
            observation(flags=(QualityFlag.LOCATION_UNCERTAIN,)),
            ("observation_location_uncertain",),
        ),
        (
            observation(
                flags=(
                    QualityFlag.TIME_UNCERTAIN,
                    QualityFlag.LOCATION_UNCERTAIN,
                )
            ),
            (
                "observation_time_uncertain",
                "observation_location_uncertain",
            ),
        ),
    ],
)
def test_legacy_and_uncertain_observations_fail_closed(source, expected_reasons):
    result = compare(
        source,
        point(WeatherVariable.TEMPERATURE_C, 8.0),
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert result.results == ()
    assert reason_codes(result) == expected_reasons


@pytest.mark.parametrize(
    ("invalid", "code"),
    [(None, "field_observation_missing"), ("corrupt", "field_observation_invalid")],
)
def test_missing_or_invalid_observation_raises_typed_input_error(invalid, code):
    with pytest.raises(ForecastObservationComparisonInputError, match=f"^{code}$"):
        compare_forecast_to_field_observation(
            DecisionForecastEvidence(()),
            invalid,
            computed_at_utc=COMPUTED_AT,
        )


def test_unsupported_observation_dimensions_and_forecasts_are_excluded():
    source = observation(
        conditions=ObservedConditions(
            transparency=Transparency.GOOD,
            seeing=SeeingCondition.POOR,
            surface_condition=SurfaceCondition.DEW_PRESENT,
        )
    )

    result = compare(
        source,
        point(WeatherVariable.DEW_POINT_C, 3.0),
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert result.results == ()
    assert reason_codes(result) == ("no_supported_observed_variables",)


def test_different_offsets_representing_same_instant_match_exactly():
    plus_two = timezone(timedelta(hours=2))
    local_instant = OBSERVED_AT.astimezone(plus_two)
    source = observation(observed_at=local_instant)

    result = compare(
        source,
        point(WeatherVariable.TEMPERATURE_C, 8.0),
    )

    selected = result_for(result, WeatherVariable.TEMPERATURE_C)
    assert source.observed_at_utc == OBSERVED_AT
    assert selected.forecast_point.temporal_offset == timedelta(0)


def test_dst_fold_is_resolved_by_instant_in_utc():
    zurich = ZoneInfo("Europe/Zurich")
    local_after_fallback = datetime(2026, 10, 25, 2, 30, tzinfo=zurich, fold=1)
    utc_instant = datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)
    source = observation(observed_at=local_after_fallback)

    result = compare(
        source,
        point(
            WeatherVariable.TEMPERATURE_C,
            8.0,
            forecast_for=utc_instant,
            retrieved_at=utc_instant - timedelta(hours=4),
        ),
    )

    selected = result_for(result, WeatherVariable.TEMPERATURE_C)
    assert source.observed_at_utc == utc_instant
    assert selected.forecast_point.temporal_offset == timedelta(0)


def test_id_and_logical_content_are_deterministic_and_version_sensitive():
    source = observation()
    evidence_point = point(WeatherVariable.TEMPERATURE_C, 9.0)

    first = compare(source, evidence_point)
    second = compare(source, evidence_point)
    new_algorithm = compare(
        source,
        evidence_point,
        algorithm_version="forecast_observation.v2",
    )
    new_policy = compare(
        source,
        evidence_point,
        parameters=ForecastObservationParameters(
            temporal_policy=TemporalComparisonPolicy(
                version="nearest_forecast_utc.v2"
            ),
            cloud_mapping_policy=CloudMappingComparisonPolicy(),
        ),
    )

    assert first == second
    assert first.comparison_id == second.comparison_id
    assert new_algorithm.comparison_id != first.comparison_id
    assert new_policy.comparison_id != first.comparison_id


def test_sources_are_not_mutated_by_comparison():
    source = observation(
        conditions=ObservedConditions(
            temperature_c=8.0,
            relative_humidity_percent=70.0,
            wind_speed_kmh=0.0,
            cloud_state=CloudState.CLEAR,
        )
    )
    evidence = DecisionForecastEvidence(
        (
            point(WeatherVariable.TEMPERATURE_C, 9.0),
            point(WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 72.0),
            point(WeatherVariable.WIND_SPEED_KMH, 0.0),
            point(WeatherVariable.CLOUD_COVER_PERCENT, 5.0),
        )
    )
    source_before = deepcopy(source)
    evidence_before = deepcopy(evidence)

    compare_forecast_to_field_observation(
        evidence,
        source,
        computed_at_utc=COMPUTED_AT,
    )

    assert source == source_before
    assert evidence == evidence_before


def test_engine_import_graph_excludes_product_decision_and_learning_layers():
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    forbidden_fragments = (
        "scoring",
        "recommendation",
        "learning",
        "calibration",
        "outcome_assessment",
    )
    assert all(
        fragment not in module
        for module in imported_modules
        for fragment in forbidden_fragments
    )
