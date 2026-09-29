import ast
import struct
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta, timezone, tzinfo
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
    _canonical_evidence,
    _digest,
    _fingerprint_is_persistable,
    _safe_fingerprint_token,
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
MODEL_PATH = (
    Path(__file__).parents[2]
    / "decision"
    / "models"
    / "forecast_observation_comparison.py"
)

ALLOWED_IMPORTS = {
    MODEL_PATH: {
        ("__future__", "annotations"),
        ("dataclasses", "dataclass"),
        ("dataclasses", "field"),
        ("datetime", "datetime"),
        ("datetime", "timedelta"),
        ("datetime", "timezone"),
        ("enum", "Enum"),
        ("decision.field_observation", "CaptureMethod"),
        ("decision.field_observation", "CloudState"),
        ("decision.field_observation", "Confidence"),
        ("decision.field_observation", "ObservationSourceType"),
        ("decision.field_observation", "QualityFlag"),
        ("decision.weather.provider_reliability", "WeatherVariable"),
    },
    SERVICE_PATH: {
        ("__future__", "annotations"),
        ("hashlib", None),
        ("json", None),
        ("struct", None),
        ("dataclasses", "asdict"),
        ("datetime", "date"),
        ("datetime", "datetime"),
        ("datetime", "time"),
        ("datetime", "timedelta"),
        ("datetime", "timezone"),
        ("datetime", "tzinfo"),
        ("enum", "Enum"),
        ("types", "MemberDescriptorType"),
        ("zoneinfo", "ZoneInfo"),
        ("decision.field_observation", "CaptureMethod"),
        ("decision.field_observation", "CloudState"),
        ("decision.field_observation", "Confidence"),
        ("decision.field_observation", "FieldObservation"),
        ("decision.field_observation", "HfrUnit"),
        ("decision.field_observation", "ObservationProvenance"),
        ("decision.field_observation", "ObservationQuality"),
        ("decision.field_observation", "ObservationSourceType"),
        ("decision.field_observation", "ObservedAcquisition"),
        ("decision.field_observation", "ObservedConditions"),
        ("decision.field_observation", "ObservedTechnical"),
        ("decision.field_observation", "QualityFlag"),
        ("decision.field_observation", "SeeingCondition"),
        ("decision.field_observation", "StopReason"),
        ("decision.field_observation", "SurfaceCondition"),
        ("decision.field_observation", "Transparency"),
        ("decision.models.forecast_observation_comparison", "ALGORITHM_VERSION"),
        ("decision.models.forecast_observation_comparison", "FORECAST_SCOPE"),
        ("decision.models.forecast_observation_comparison", "CloudComparisonOutcome"),
        ("decision.models.forecast_observation_comparison", "CloudMappingComparisonPolicy"),
        ("decision.models.forecast_observation_comparison", "CloudVariableComparison"),
        ("decision.models.forecast_observation_comparison", "ComparisonReason"),
        ("decision.models.forecast_observation_comparison", "ForecastObservationComparison"),
        ("decision.models.forecast_observation_comparison", "ForecastObservationComparisonStatus"),
        ("decision.models.forecast_observation_comparison", "ForecastObservationParameters"),
        ("decision.models.forecast_observation_comparison", "ForecastPointProvenance"),
        ("decision.models.forecast_observation_comparison", "NumericVariableComparison"),
        ("decision.models.forecast_observation_comparison", "ObservationComparisonProvenance"),
        ("decision.models.forecast_observation_comparison", "TemporalComparisonPolicy"),
        ("decision.models.forecast_observation_comparison", "VariableComparison"),
        ("decision.models.forecast_observation_comparison", "VariableComparisonStatus"),
        ("decision.weather.cloud_mapping_policy", "map_cloud_cover_to_condition"),
        ("decision.weather.decision_forecast_evidence", "DecisionForecastEvidence"),
        ("decision.weather.forecast_temporal_candidates", "build_forecast_temporal_candidates"),
        ("decision.weather.forecast_temporal_selection", "ForecastTemporalSelectionError"),
        ("decision.weather.forecast_temporal_selection", "select_forecast_temporal_candidate"),
        ("decision.weather.provider_reliability", "CANONICAL_UNITS"),
        ("decision.weather.provider_reliability", "WeatherForecastPoint"),
        ("decision.weather.provider_reliability", "WeatherLocation"),
        ("decision.weather.provider_reliability", "WeatherValue"),
        ("decision.weather.provider_reliability", "WeatherVariable"),
        ("decision.weather.provider_reliability", "calculate_weather_variable_error"),
    },
}


def import_boundary_violations(source, allowed_imports):
    violations = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports = ((alias.name, None, alias.asname) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                for alias in node.names:
                    violations.append((node.module, alias.name, alias.asname))
                continue
            imports = (
                (node.module, alias.name, alias.asname) for alias in node.names
            )
        else:
            continue
        for module, symbol, alias in imports:
            if (module, symbol) not in allowed_imports or alias is not None:
                violations.append((module, symbol, alias))
    return tuple(violations)


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


def multi_value_point(*values):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        model_id="best_match",
        retrieved_at_utc=RETRIEVED_AT,
        forecast_for_utc=OBSERVED_AT,
        requested_location=LOCATION,
        grid_location=LOCATION,
        values=tuple(values),
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


def test_v1_temporal_policy_accepts_exactly_thirty_minutes():
    policy = TemporalComparisonPolicy(
        maximum_absolute_offset=timedelta(minutes=30)
    )

    assert policy.maximum_absolute_offset == timedelta(minutes=30)


@pytest.mark.parametrize(
    "maximum_absolute_offset",
    [
        timedelta(minutes=30, microseconds=1),
        timedelta(minutes=31),
    ],
)
def test_v1_temporal_policy_rejects_custom_tolerance_above_thirty_minutes(
    maximum_absolute_offset,
):
    with pytest.raises(ValueError, match="^v1_maximum_absolute_offset_exceeded$"):
        TemporalComparisonPolicy(
            version="nearest_forecast_utc.v1",
            maximum_absolute_offset=maximum_absolute_offset,
        )


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


def test_logical_duplicates_with_permuted_values_share_selection_and_identity():
    temperature = WeatherValue(
        variable=WeatherVariable.TEMPERATURE_C,
        value=9.0,
        unit="°C",
    )
    wind = WeatherValue(
        variable=WeatherVariable.WIND_SPEED_KMH,
        value=0.0,
        unit="km/h",
    )
    ordered = multi_value_point(temperature, wind)
    permuted = multi_value_point(wind, temperature)
    source = observation(
        conditions=ObservedConditions(temperature_c=8.0, wind_speed_kmh=0.0)
    )

    single = compare(source, ordered)
    repeated = compare(source, ordered, permuted)

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


def test_signed_zero_is_normalized_in_observation_forecast_digest_and_id():
    negative_zero = compare(
        observation(conditions=ObservedConditions(wind_speed_kmh=-0.0)),
        point(WeatherVariable.WIND_SPEED_KMH, -0.0),
    )
    positive_zero = compare(
        observation(conditions=ObservedConditions(wind_speed_kmh=0.0)),
        point(WeatherVariable.WIND_SPEED_KMH, 0.0),
    )

    assert negative_zero.results == positive_zero.results
    assert negative_zero.source_digest == positive_zero.source_digest
    assert negative_zero.comparison_id == positive_zero.comparison_id


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


def test_list_corruption_of_canonical_point_values_fails_closed():
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    evidence = DecisionForecastEvidence((forecast_point,))
    object.__setattr__(forecast_point, "values", list(forecast_point.values))

    result = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)
    assert result.results[0].reasons[0].code == (
        "decision_forecast_evidence_invalid"
    )


def test_runtime_error_while_normalizing_corrupted_datetime_fails_closed():
    class CorruptedDatetime(datetime):
        def astimezone(self, tz=None):
            raise RuntimeError("corrupted datetime")

    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    evidence = DecisionForecastEvidence((forecast_point,))
    corrupted_datetime = CorruptedDatetime(
        2026, 9, 1, 17, 0, tzinfo=timezone.utc
    )
    object.__setattr__(
        forecast_point, "retrieved_at_utc", corrupted_datetime
    )

    result = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)
    assert result.results[0].reasons[0].code == (
        "decision_forecast_evidence_invalid"
    )


def test_named_utc_evidence_timestamp_fails_closed_without_normalization():
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    named_utc = timezone(timedelta(0), "NAMED")
    object.__setattr__(
        forecast_point,
        "forecast_for_utc",
        OBSERVED_AT.replace(tzinfo=named_utc),
    )

    result = compare_forecast_to_field_observation(
        DecisionForecastEvidence((forecast_point,)),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)


def test_opaque_zero_offset_evidence_timestamp_fails_closed():
    class OpaqueZeroTimezone(tzinfo):
        def utcoffset(self, value):
            return timedelta(0)

        def dst(self, value):
            return timedelta(0)

        def tzname(self, value):
            return "UTC"

    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(
        forecast_point,
        "retrieved_at_utc",
        RETRIEVED_AT.replace(tzinfo=OpaqueZeroTimezone()),
    )

    result = compare_forecast_to_field_observation(
        DecisionForecastEvidence((forecast_point,)),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)


def test_fold_one_evidence_timestamp_fails_closed():
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(
        forecast_point,
        "forecast_for_utc",
        OBSERVED_AT.replace(fold=1),
    )

    result = compare_forecast_to_field_observation(
        DecisionForecastEvidence((forecast_point,)),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)


def test_same_instant_with_non_canonical_tzinfo_is_not_equivalent_evidence():
    canonical = compare(
        observation(),
        point(WeatherVariable.TEMPERATURE_C, 8.0),
    )
    non_canonical_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(
        non_canonical_point,
        "forecast_for_utc",
        OBSERVED_AT.replace(tzinfo=ZoneInfo("UTC")),
    )
    non_canonical = compare(
        observation(),
        non_canonical_point,
    )

    assert canonical.status is ForecastObservationComparisonStatus.COMPARABLE
    assert (
        non_canonical.status
        is ForecastObservationComparisonStatus.NOT_COMPARABLE
    )
    assert reason_codes(non_canonical) == (
        "decision_forecast_evidence_invalid",
    )


def test_invalid_nan_payload_bits_are_preserved_in_redacted_identity():
    def corrupted_evidence(bits):
        invalid_value = struct.unpack(">d", struct.pack(">Q", bits))[0]
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(forecast_point.values[0], "value", invalid_value)
        return DecisionForecastEvidence((forecast_point,))

    first = compare_forecast_to_field_observation(
        corrupted_evidence(0x7FF8000000000001),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated_first = compare_forecast_to_field_observation(
        corrupted_evidence(0x7FF8000000000001),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    second = compare_forecast_to_field_observation(
        corrupted_evidence(0x7FF8000000000002),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert reason_codes(first) == ("decision_forecast_evidence_invalid",)
    assert first.source_digest == repeated_first.source_digest
    assert first.comparison_id == repeated_first.comparison_id
    assert first.source_digest != second.source_digest
    assert first.comparison_id != second.comparison_id


def test_invalid_infinities_have_distinct_redacted_identity():
    def corrupted_result(value):
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(forecast_point.values[0], "value", value)
        return compare_forecast_to_field_observation(
            DecisionForecastEvidence((forecast_point,)),
            observation(),
            computed_at_utc=COMPUTED_AT,
        )

    positive = corrupted_result(float("inf"))
    negative = corrupted_result(float("-inf"))

    assert reason_codes(positive) == ("decision_forecast_evidence_invalid",)
    assert reason_codes(negative) == ("decision_forecast_evidence_invalid",)
    assert positive.source_digest != negative.source_digest
    assert positive.comparison_id != negative.comparison_id


def test_materially_different_invalid_evidence_has_distinct_identity():
    invalid_provider_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(invalid_provider_point, "provider_id", "")
    invalid_unit_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(invalid_unit_point.values[0], "unit", "K")

    invalid_provider = compare_forecast_to_field_observation(
        DecisionForecastEvidence((invalid_provider_point,)),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated_invalid_provider = compare_forecast_to_field_observation(
        DecisionForecastEvidence((invalid_provider_point,)),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    invalid_unit = compare_forecast_to_field_observation(
        DecisionForecastEvidence((invalid_unit_point,)),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert (
        invalid_provider.status
        is ForecastObservationComparisonStatus.NOT_COMPARABLE
    )
    assert (
        invalid_unit.status
        is ForecastObservationComparisonStatus.NOT_COMPARABLE
    )
    assert reason_codes(invalid_provider) == (
        "decision_forecast_evidence_invalid",
    )
    assert reason_codes(invalid_unit) == ("decision_forecast_evidence_invalid",)
    assert invalid_provider.source_digest != invalid_unit.source_digest
    assert invalid_provider.comparison_id != invalid_unit.comparison_id
    assert (
        repeated_invalid_provider.source_digest
        == invalid_provider.source_digest
    )
    assert (
        repeated_invalid_provider.comparison_id
        == invalid_provider.comparison_id
    )


def test_distinct_corrupted_dicts_have_distinct_redacted_stable_identity():
    def corrupted_evidence(requested_location):
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(
            forecast_point, "requested_location", requested_location
        )
        return DecisionForecastEvidence((forecast_point,))

    first_evidence = corrupted_evidence({"latitude": 1})
    second_evidence = corrupted_evidence(
        {"latitude": 999, "secret": "materially-different"}
    )

    first = compare_forecast_to_field_observation(
        first_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated_first = compare_forecast_to_field_observation(
        first_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    second = compare_forecast_to_field_observation(
        second_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert first.source_digest == repeated_first.source_digest
    assert first.comparison_id == repeated_first.comparison_id
    assert first.source_digest != second.source_digest
    assert first.comparison_id != second.comparison_id
    invalid_document = _canonical_evidence(second_evidence)
    assert invalid_document["invalid_identity_persistable"] is True
    assert "materially-different" not in str(invalid_document)


def test_distinct_corrupted_datetimes_have_distinct_stable_identity():
    class CorruptedDatetime(datetime):
        def astimezone(self, tz=None):
            raise RuntimeError("corrupted datetime")

    def corrupted_evidence(day):
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(
            forecast_point,
            "retrieved_at_utc",
            CorruptedDatetime(2026, 9, day, 17, 0, tzinfo=timezone.utc),
        )
        return DecisionForecastEvidence((forecast_point,))

    first_evidence = corrupted_evidence(1)
    second_evidence = corrupted_evidence(2)

    first = compare_forecast_to_field_observation(
        first_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated_first = compare_forecast_to_field_observation(
        first_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    second = compare_forecast_to_field_observation(
        second_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert first.source_digest == repeated_first.source_digest
    assert first.comparison_id == repeated_first.comparison_id
    assert first.source_digest != second.source_digest
    assert first.comparison_id != second.comparison_id


def test_same_named_timezones_with_distinct_offsets_have_distinct_identity():
    def corrupted_evidence(offset_hours):
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(
            forecast_point,
            "retrieved_at_utc",
            datetime(
                2026,
                9,
                1,
                17,
                0,
                tzinfo=timezone(timedelta(hours=offset_hours), "SAME"),
            ),
        )
        return DecisionForecastEvidence((forecast_point,))

    plus_one_evidence = corrupted_evidence(1)
    plus_two_evidence = corrupted_evidence(2)

    plus_one = compare_forecast_to_field_observation(
        plus_one_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    plus_two = compare_forecast_to_field_observation(
        plus_two_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert plus_one.identity_persistable is True
    assert plus_two.identity_persistable is True
    assert plus_one.source_digest != plus_two.source_digest
    assert plus_one.comparison_id != plus_two.comparison_id


def test_zoneinfo_wall_times_keep_structured_distinct_identity():
    def corrupted_evidence(zone_name):
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(
            forecast_point,
            "retrieved_at_utc",
            datetime(2026, 9, 1, 17, 0, tzinfo=ZoneInfo(zone_name)),
        )
        return DecisionForecastEvidence((forecast_point,))

    zurich_evidence = corrupted_evidence("Europe/Zurich")
    london_evidence = corrupted_evidence("Europe/London")
    zurich = compare_forecast_to_field_observation(
        zurich_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated_zurich = compare_forecast_to_field_observation(
        zurich_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    london = compare_forecast_to_field_observation(
        london_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert zurich.identity_persistable is False
    assert london.identity_persistable is False
    assert zurich.source_digest == repeated_zurich.source_digest
    assert zurich.comparison_id == repeated_zurich.comparison_id
    assert zurich.source_digest != london.source_digest
    assert zurich.comparison_id != london.comparison_id


def test_opaque_timezone_makes_invalid_identity_non_persistable_and_stable():
    class OpaqueTimezone(tzinfo):
        __slots__ = ()

        def utcoffset(self, value):
            return timedelta(hours=1)

        def dst(self, value):
            return timedelta(0)

        def tzname(self, value):
            return "OPAQUE"

    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(
        forecast_point,
        "retrieved_at_utc",
        datetime(2026, 9, 1, 17, 0, tzinfo=OpaqueTimezone()),
    )
    evidence = DecisionForecastEvidence((forecast_point,))

    first = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    second = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert first.identity_persistable is False
    assert first.source_digest == second.source_digest
    assert first.comparison_id == second.comparison_id


def test_datetime_subclass_slot_state_is_not_hidden_by_primitive_digest():
    class ExtendedDatetime(datetime):
        __slots__ = ("marker",)

    def corrupted_evidence(marker):
        value = ExtendedDatetime(
            2026,
            9,
            1,
            17,
            0,
            tzinfo=timezone.utc,
        )
        value.marker = marker
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(forecast_point, "retrieved_at_utc", value)
        return DecisionForecastEvidence((forecast_point,))

    first_evidence = corrupted_evidence("first")
    first = compare_forecast_to_field_observation(
        first_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated_first = compare_forecast_to_field_observation(
        first_evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    second = compare_forecast_to_field_observation(
        corrupted_evidence("second"),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert first.identity_persistable is True
    assert second.identity_persistable is True
    assert first.source_digest == repeated_first.source_digest
    assert first.comparison_id == repeated_first.comparison_id
    assert first.source_digest != second.source_digest
    assert first.comparison_id != second.comparison_id


@pytest.mark.parametrize(
    ("base_type", "arguments"),
    [
        (date, (2026, 9, 1)),
        (time, (17, 0)),
        (timedelta, (0, 1)),
    ],
)
def test_other_temporal_subclass_slot_state_is_fully_fingerprinted(
    base_type,
    arguments,
):
    class ExtendedTemporal(base_type):
        __slots__ = ("marker",)

    first = ExtendedTemporal(*arguments)
    first.marker = "first"
    second = ExtendedTemporal(*arguments)
    second.marker = "second"
    first_token = _safe_fingerprint_token(first)
    repeated_first_token = _safe_fingerprint_token(first)
    second_token = _safe_fingerprint_token(second)

    assert _fingerprint_is_persistable(first_token) is True
    assert _fingerprint_is_persistable(second_token) is True
    assert _digest(first_token) == _digest(repeated_first_token)
    assert _digest(first_token) != _digest(second_token)


def test_hybrid_dict_and_slots_state_is_fully_fingerprinted():
    class HybridState:
        __slots__ = ("slot_state", "__dict__")

        def __init__(self, slot_state):
            self.dictionary_state = "same"
            self.slot_state = slot_state

    def corrupted_evidence(slot_state):
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(
            forecast_point,
            "requested_location",
            HybridState(slot_state),
        )
        return DecisionForecastEvidence((forecast_point,))

    first = compare_forecast_to_field_observation(
        corrupted_evidence("first"),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    second = compare_forecast_to_field_observation(
        corrupted_evidence("second"),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert first.identity_persistable is True
    assert second.identity_persistable is True
    assert first.source_digest != second.source_digest
    assert first.comparison_id != second.comparison_id


@pytest.mark.parametrize("mutated_slots", [(), ("renamed",)])
def test_material_slot_survives_mutated_slots_metadata(mutated_slots):
    class SlottedLocation:
        __slots__ = ("marker",)

    first_location = SlottedLocation()
    first_location.marker = "first"
    second_location = SlottedLocation()
    second_location.marker = "second"
    SlottedLocation.__slots__ = mutated_slots

    def result_for(location):
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(forecast_point, "requested_location", location)
        return compare_forecast_to_field_observation(
            DecisionForecastEvidence((forecast_point,)),
            observation(),
            computed_at_utc=COMPUTED_AT,
        )

    first = result_for(first_location)
    repeated_first = result_for(first_location)
    second = result_for(second_location)

    assert first.identity_persistable is True
    assert second.identity_persistable is True
    assert first.source_digest == repeated_first.source_digest
    assert first.comparison_id == repeated_first.comparison_id
    assert first.source_digest != second.source_digest
    assert first.comparison_id != second.comparison_id


def test_material_slots_across_multilevel_and_multiple_inheritance_are_unique():
    class RootState:
        __slots__ = ("root",)

    class IntermediateState(RootState):
        __slots__ = ("middle",)

    class EmptyBranch:
        __slots__ = ()

    class CombinedState(IntermediateState, EmptyBranch):
        __slots__ = ("leaf",)

    def token(root, middle, leaf):
        value = CombinedState()
        value.root = root
        value.middle = middle
        value.leaf = leaf
        return _safe_fingerprint_token(value)

    baseline = token("root", "middle", "leaf")
    repeated = token("root", "middle", "leaf")
    changed_root = token("changed", "middle", "leaf")
    changed_middle = token("root", "changed", "leaf")
    changed_leaf = token("root", "middle", "changed")

    assert _fingerprint_is_persistable(baseline) is True
    assert _digest(baseline) == _digest(repeated)
    assert len(baseline["state"]["slots"]) == 3
    assert len(
        {
            _digest(slot["slot"])
            for slot in baseline["state"]["slots"]
        }
    ) == 3
    assert _digest(baseline) != _digest(changed_root)
    assert _digest(baseline) != _digest(changed_middle)
    assert _digest(baseline) != _digest(changed_leaf)


def test_same_named_dynamic_classes_include_material_slot_state():
    class_attributes = {
        "__module__": "same.dynamic.module",
        "__qualname__": "SameIdentity",
        "__slots__": ("marker",),
    }
    first_type = type("SameIdentity", (), class_attributes)
    second_type = type("SameIdentity", (), class_attributes)
    first = first_type()
    first.marker = "first"
    second = second_type()
    second.marker = "second"

    def result_for(location):
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(forecast_point, "requested_location", location)
        return compare_forecast_to_field_observation(
            DecisionForecastEvidence((forecast_point,)),
            observation(),
            computed_at_utc=COMPUTED_AT,
        )

    first_result = result_for(first)
    repeated_first_result = result_for(first)
    second_result = result_for(second)

    assert first_result.identity_persistable is True
    assert second_result.identity_persistable is True
    assert first_result.source_digest == repeated_first_result.source_digest
    assert first_result.comparison_id == repeated_first_result.comparison_id
    assert first_result.source_digest != second_result.source_digest
    assert first_result.comparison_id != second_result.comparison_id


def test_foreign_slot_descriptor_alias_is_explicitly_non_persistable():
    class ForeignState:
        __slots__ = ("foreign",)

    class LocalState:
        __slots__ = ("local",)

    LocalState.ambiguous = vars(ForeignState)["foreign"]
    value = LocalState()
    value.local = "material"

    token = _safe_fingerprint_token(value)

    assert _fingerprint_is_persistable(token) is False


def test_temporal_material_slot_survives_mutated_slots_metadata():
    class ExtendedDatetime(datetime):
        __slots__ = ("marker",)

    first = ExtendedDatetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc)
    first.marker = "first"
    second = ExtendedDatetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc)
    second.marker = "second"
    ExtendedDatetime.__slots__ = ()

    first_token = _safe_fingerprint_token(first)
    repeated_first_token = _safe_fingerprint_token(first)
    second_token = _safe_fingerprint_token(second)

    assert _fingerprint_is_persistable(first_token) is True
    assert _fingerprint_is_persistable(second_token) is True
    assert _digest(first_token) == _digest(repeated_first_token)
    assert _digest(first_token) != _digest(second_token)


@pytest.mark.parametrize("unsafe_state", ["opaque", "cycle", "depth"])
def test_non_canonicalizable_identity_is_publicly_non_persistable(unsafe_state):
    if unsafe_state == "opaque":
        replacement = object()
    elif unsafe_state == "cycle":
        replacement = []
        replacement.append(replacement)
    else:
        replacement = "leaf"
        for _ in range(10):
            replacement = [replacement]
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(forecast_point, "requested_location", replacement)

    result = compare_forecast_to_field_observation(
        DecisionForecastEvidence((forecast_point,)),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.identity_persistable is False
    assert len(result.comparison_id) == 64
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)


@pytest.mark.parametrize("target", ["evidence", "point", "location", "value"])
def test_undeclared_material_on_known_evidence_types_fails_closed(target):
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    if target == "location":
        local_location = WeatherLocation(46.7508, 6.5495, altitude_m=1245.0)
        object.__setattr__(forecast_point, "requested_location", local_location)
        corrupted = local_location
    elif target == "value":
        corrupted = forecast_point.values[0]
    elif target == "point":
        corrupted = forecast_point
    evidence = DecisionForecastEvidence((forecast_point,))
    if target == "evidence":
        corrupted = evidence
    object.__setattr__(corrupted, "undeclared_material", "redacted-secret")

    result = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)
    assert result.identity_persistable is True
    assert "redacted-secret" not in str(_canonical_evidence(evidence))


@pytest.mark.parametrize(
    ("target", "attribute", "invalid_value"),
    [
        ("point", "values", "broken"),
        ("point", "values", ("not-a-weather-value",)),
        ("value", "variable", "temperature_c"),
        ("value", "unit", "K"),
        ("point", "provider_id", ""),
        ("point", "model_id", ""),
        ("point", "retrieved_at_utc", datetime(2026, 9, 1, 17, 0)),
        ("point", "forecast_for_utc", "broken"),
        ("point", "requested_location", "broken"),
        ("point", "grid_location", "broken"),
    ],
)
def test_deeply_corrupted_evidence_fails_closed(
    target,
    attribute,
    invalid_value,
):
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    evidence = DecisionForecastEvidence((forecast_point,))
    corrupted = forecast_point if target == "point" else forecast_point.values[0]
    object.__setattr__(corrupted, attribute, invalid_value)

    result = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)
    assert result.results[0].reasons[0].code == (
        "decision_forecast_evidence_invalid"
    )


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


def test_legacy_observation_keeps_invalid_evidence_reason_first():
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(forecast_point, "requested_location", {"latitude": 1})

    result = compare_forecast_to_field_observation(
        DecisionForecastEvidence((forecast_point,)),
        legacy_observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert result.results == ()
    assert reason_codes(result) == (
        "decision_forecast_evidence_invalid",
        "legacy_lineage_incomplete",
    )


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


def test_structurally_corrupted_observation_is_rejected_before_digest():
    source = observation()
    object.__setattr__(source, "conditions", "broken")

    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^field_observation_invalid$",
    ):
        compare_forecast_to_field_observation(
            DecisionForecastEvidence(()),
            source,
            computed_at_utc=COMPUTED_AT,
        )


def test_observation_subclass_extra_state_is_rejected_without_identity():
    class ExtendedFieldObservation(FieldObservation):
        __slots__ = ("marker",)

    def extended_observation(marker):
        source = observation()
        extended = ExtendedFieldObservation(
            observation_id=source.observation_id,
            decision_id=source.decision_id,
            execution_id=source.execution_id,
            observed_at_utc=source.observed_at_utc,
            recorded_at_utc=source.recorded_at_utc,
            supersedes_observation_id=source.supersedes_observation_id,
            conditions=source.conditions,
            acquisition=source.acquisition,
            technical=source.technical,
            provenance=source.provenance,
            quality=source.quality,
        )
        object.__setattr__(extended, "marker", marker)
        return extended

    for marker in ("first", "second"):
        with pytest.raises(
            ForecastObservationComparisonInputError,
            match="^field_observation_invalid$",
        ):
            compare_forecast_to_field_observation(
                DecisionForecastEvidence(()),
                extended_observation(marker),
                computed_at_utc=COMPUTED_AT,
            )


def test_observation_section_subclass_extra_state_is_rejected():
    class ExtendedConditions(ObservedConditions):
        __slots__ = ("marker",)

    for marker in ("first", "second"):
        conditions = ExtendedConditions(temperature_c=8.0)
        object.__setattr__(conditions, "marker", marker)
        source = observation()
        object.__setattr__(source, "conditions", conditions)
        with pytest.raises(
            ForecastObservationComparisonInputError,
            match="^field_observation_invalid$",
        ):
            compare_forecast_to_field_observation(
                DecisionForecastEvidence(()),
                source,
                computed_at_utc=COMPUTED_AT,
            )


def test_original_observation_primitives_are_validated_before_reconstruction():
    class FloatSubclass(float):
        pass

    class IntSubclass(int):
        pass

    class StringSubclass(str):
        pass

    class DatetimeSubclass(datetime):
        pass

    subclassed_datetime = DatetimeSubclass(
        2026,
        9,
        1,
        21,
        0,
        tzinfo=timezone.utc,
    )
    corruptions = (
        ("conditions", "temperature_c", 8),
        ("conditions", "temperature_c", FloatSubclass(8.0)),
        ("acquisition", "attempted_frames", IntSubclass(1)),
        ("provenance", "source_id", " station-42 "),
        ("provenance", "source_id", StringSubclass("station-42")),
        ("conditions", "cloud_state", Confidence.HIGH),
        (None, "observed_at_utc", subclassed_datetime),
        ("quality", "flags", [QualityFlag.ESTIMATED]),
    )

    for section_name, field_name, invalid_value in corruptions:
        source = observation()
        target = source if section_name is None else getattr(source, section_name)
        object.__setattr__(target, field_name, invalid_value)

        with pytest.raises(
            ForecastObservationComparisonInputError,
            match="^field_observation_invalid$",
        ):
            compare_forecast_to_field_observation(
                DecisionForecastEvidence(()),
                source,
                computed_at_utc=COMPUTED_AT,
            )


def test_fold_one_observation_timestamp_is_rejected_before_reconstruction():
    source = observation()
    object.__setattr__(source, "observed_at_utc", OBSERVED_AT.replace(fold=1))

    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^field_observation_invalid$",
    ):
        compare_forecast_to_field_observation(
            DecisionForecastEvidence(()),
            source,
            computed_at_utc=COMPUTED_AT,
        )


def test_named_utc_observation_timestamp_is_rejected_before_reconstruction():
    source = observation()
    object.__setattr__(
        source,
        "recorded_at_utc",
        source.recorded_at_utc.replace(
            tzinfo=timezone(timedelta(0), "NAMED")
        ),
    )

    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^field_observation_invalid$",
    ):
        compare_forecast_to_field_observation(
            DecisionForecastEvidence(()),
            source,
            computed_at_utc=COMPUTED_AT,
        )


@pytest.mark.parametrize("invalid_parameters", [False, 0, "", (), [], {}])
def test_falsy_non_parameter_values_are_rejected(invalid_parameters):
    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^invalid_forecast_observation_parameters$",
    ):
        compare_forecast_to_field_observation(
            DecisionForecastEvidence(()),
            observation(),
            computed_at_utc=COMPUTED_AT,
            parameters=invalid_parameters,
        )


def test_parameter_subclass_is_rejected_by_exact_type_contract():
    class ExtendedParameters(ForecastObservationParameters):
        __slots__ = ("marker",)

    parameters = ExtendedParameters()
    object.__setattr__(parameters, "marker", "material")

    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^invalid_forecast_observation_parameters$",
    ):
        compare_forecast_to_field_observation(
            DecisionForecastEvidence(()),
            observation(),
            computed_at_utc=COMPUTED_AT,
            parameters=parameters,
        )


def test_policy_subclasses_with_distinct_material_state_are_rejected():
    class ExtendedTemporalPolicy(TemporalComparisonPolicy):
        __slots__ = ("marker",)

    class ExtendedCloudPolicy(CloudMappingComparisonPolicy):
        __slots__ = ("marker",)

    temporal_policies = []
    cloud_policies = []
    for marker in ("first", "second"):
        temporal_policy = ExtendedTemporalPolicy()
        object.__setattr__(temporal_policy, "marker", marker)
        temporal_policies.append(
            ForecastObservationParameters(temporal_policy=temporal_policy)
        )
        cloud_policy = ExtendedCloudPolicy()
        object.__setattr__(cloud_policy, "marker", marker)
        cloud_policies.append(
            ForecastObservationParameters(cloud_mapping_policy=cloud_policy)
        )

    for parameters in (*temporal_policies, *cloud_policies):
        with pytest.raises(
            ForecastObservationComparisonInputError,
            match="^invalid_forecast_observation_parameters$",
        ):
            compare_forecast_to_field_observation(
                DecisionForecastEvidence(()),
                observation(),
                computed_at_utc=COMPUTED_AT,
                parameters=parameters,
            )


def test_corrupted_parameter_primitives_fail_closed_without_technical_errors():
    class TimedeltaSubclass(timedelta):
        __slots__ = ("marker",)

    class UnreadableTemporalPolicy(TemporalComparisonPolicy):
        @property
        def version(self):
            raise RuntimeError("must not escape")

    corruptions = []

    offset_is_integer = ForecastObservationParameters()
    object.__setattr__(
        offset_is_integer.temporal_policy,
        "maximum_absolute_offset",
        0,
    )
    corruptions.append(offset_is_integer)

    offset_has_extra_state = TimedeltaSubclass(minutes=30)
    offset_has_extra_state.marker = "material"
    offset_is_subclassed = ForecastObservationParameters()
    object.__setattr__(
        offset_is_subclassed.temporal_policy,
        "maximum_absolute_offset",
        offset_has_extra_state,
    )
    corruptions.append(offset_is_subclassed)

    non_canonical_version = ForecastObservationParameters()
    object.__setattr__(
        non_canonical_version.temporal_policy,
        "version",
        " nearest_forecast_utc.v1 ",
    )
    corruptions.append(non_canonical_version)

    non_canonical_mapping = ForecastObservationParameters()
    object.__setattr__(
        non_canonical_mapping.cloud_mapping_policy,
        "version",
        " cloud_mapping.v1 ",
    )
    corruptions.append(non_canonical_mapping)

    unreadable_policy = object.__new__(UnreadableTemporalPolicy)
    corruptions.append(
        ForecastObservationParameters(temporal_policy=unreadable_policy)
    )

    for parameters in corruptions:
        with pytest.raises(
            ForecastObservationComparisonInputError,
            match="^invalid_forecast_observation_parameters$",
        ):
            compare_forecast_to_field_observation(
                DecisionForecastEvidence(()),
                observation(),
                computed_at_utc=COMPUTED_AT,
                parameters=parameters,
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


def test_no_supported_variables_keeps_invalid_evidence_reason_first():
    source = observation(
        conditions=ObservedConditions(
            transparency=Transparency.GOOD,
            seeing=SeeingCondition.POOR,
            surface_condition=SurfaceCondition.DEW_PRESENT,
        )
    )
    forecast_point = point(WeatherVariable.DEW_POINT_C, 3.0)
    object.__setattr__(forecast_point, "requested_location", {"latitude": 1})

    result = compare_forecast_to_field_observation(
        DecisionForecastEvidence((forecast_point,)),
        source,
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert result.results == ()
    assert reason_codes(result) == (
        "decision_forecast_evidence_invalid",
        "no_supported_observed_variables",
    )


@pytest.mark.parametrize(
    ("evidence", "expected_evidence_reason"),
    [
        (None, "decision_forecast_evidence_missing"),
        (DecisionForecastEvidence(()), "decision_forecast_evidence_empty"),
    ],
)
def test_no_supported_variables_keeps_missing_or_empty_evidence_reason_first(
    evidence,
    expected_evidence_reason,
):
    source = observation(
        conditions=ObservedConditions(
            transparency=Transparency.GOOD,
            seeing=SeeingCondition.POOR,
            surface_condition=SurfaceCondition.DEW_PRESENT,
        )
    )

    result = compare_forecast_to_field_observation(
        evidence,
        source,
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert result.results == ()
    assert reason_codes(result) == (
        expected_evidence_reason,
        "no_supported_observed_variables",
    )


def test_all_applicable_blocking_reasons_are_aggregated_in_contract_order():
    source = observation(
        decision_id=None,
        execution_id=None,
        flags=(
            QualityFlag.LEGACY_LINEAGE_INCOMPLETE,
            QualityFlag.TIME_UNCERTAIN,
            QualityFlag.LOCATION_UNCERTAIN,
        ),
        conditions=ObservedConditions(
            transparency=Transparency.GOOD,
            seeing=SeeingCondition.POOR,
            surface_condition=SurfaceCondition.DEW_PRESENT,
        ),
    )
    forecast_point = point(WeatherVariable.DEW_POINT_C, 3.0)
    object.__setattr__(forecast_point, "requested_location", object())

    result = compare_forecast_to_field_observation(
        DecisionForecastEvidence((forecast_point,)),
        source,
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert result.results == ()
    assert reason_codes(result) == (
        "decision_forecast_evidence_invalid",
        "legacy_lineage_incomplete",
        "observation_time_uncertain",
        "observation_location_uncertain",
        "no_supported_observed_variables",
    )
    assert result.identity_persistable is False


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


def test_algorithm_version_subclass_is_rejected_without_calling_strip():
    class ExplodingString(str):
        def strip(self, *args, **kwargs):
            raise RuntimeError("must not be called")

    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^invalid_algorithm_version$",
    ):
        compare(
            observation(),
            point(WeatherVariable.TEMPERATURE_C, 8.0),
            algorithm_version=ExplodingString("forecast_observation.v1"),
        )


def test_algorithm_version_subclasses_with_material_state_are_rejected():
    class StatefulString(str):
        pass

    for marker in ("first", "second"):
        version = StatefulString("forecast_observation.v1")
        version.marker = marker
        with pytest.raises(
            ForecastObservationComparisonInputError,
            match="^invalid_algorithm_version$",
        ):
            compare(
                observation(),
                point(WeatherVariable.TEMPERATURE_C, 8.0),
                algorithm_version=version,
            )


@pytest.mark.parametrize("algorithm_version", ["", " ", " version", "version "])
def test_algorithm_version_must_be_nonempty_and_already_canonical(
    algorithm_version,
):
    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^invalid_algorithm_version$",
    ):
        compare(
            observation(),
            point(WeatherVariable.TEMPERATURE_C, 8.0),
            algorithm_version=algorithm_version,
        )


@pytest.mark.parametrize("surrogate", ["\ud800", "\udc00"])
def test_algorithm_version_with_isolated_surrogate_is_rejected(surrogate):
    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^invalid_algorithm_version$",
    ):
        compare(
            observation(),
            point(WeatherVariable.TEMPERATURE_C, 8.0),
            algorithm_version=surrogate,
        )


@pytest.mark.parametrize("surrogate", ["\ud800", "\udc00"])
@pytest.mark.parametrize(
    "policy_name",
    ["temporal_policy", "cloud_mapping_policy"],
)
def test_policy_version_with_isolated_surrogate_is_rejected(
    surrogate,
    policy_name,
):
    parameters = ForecastObservationParameters()
    object.__setattr__(getattr(parameters, policy_name), "version", surrogate)

    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^invalid_forecast_observation_parameters$",
    ):
        compare(
            observation(),
            point(WeatherVariable.TEMPERATURE_C, 8.0),
            parameters=parameters,
        )


@pytest.mark.parametrize("surrogate", ["\ud800", "\udc00"])
def test_observation_source_id_with_isolated_surrogate_is_rejected(surrogate):
    source = observation()
    object.__setattr__(source.provenance, "source_id", surrogate)

    with pytest.raises(
        ForecastObservationComparisonInputError,
        match="^field_observation_invalid$",
    ):
        compare(
            source,
            point(WeatherVariable.TEMPERATURE_C, 8.0),
        )


@pytest.mark.parametrize("surrogate", ["\ud800", "\udc00"])
def test_evidence_provider_id_with_isolated_surrogate_is_structured_invalid(
    surrogate,
):
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(forecast_point, "provider_id", surrogate)
    evidence = DecisionForecastEvidence((forecast_point,))

    result = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert result.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(result) == ("decision_forecast_evidence_invalid",)
    assert result.identity_persistable is True
    invalid_document = _canonical_evidence(evidence)
    assert invalid_document["invalid_reason_code"] == (
        "non_canonical_provider_id"
    )
    assert invalid_document["invalid_path"] == "forecast_points[0].provider_id"
    assert surrogate not in str(invalid_document)


@pytest.mark.parametrize("surrogate", ["\ud800", "\udc00"])
@pytest.mark.parametrize("metadata_name", ["__qualname__", "__module__"])
def test_opaque_evidence_type_metadata_is_redacted_and_total(
    surrogate,
    metadata_name,
):
    class OpaqueEvidence:
        pass

    setattr(OpaqueEvidence, metadata_name, surrogate)
    evidence = OpaqueEvidence()

    first = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert first.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(first) == ("decision_forecast_evidence_invalid",)
    assert first.identity_persistable is True
    assert first.source_digest == repeated.source_digest
    assert first.comparison_id == repeated.comparison_id
    assert surrogate not in str(_canonical_evidence(evidence))


@pytest.mark.parametrize("metadata_name", ["__qualname__", "__module__"])
def test_opaque_evidence_type_metadata_corruptions_remain_distinct(
    metadata_name,
):
    class OpaqueEvidence:
        pass

    setattr(OpaqueEvidence, metadata_name, "\ud800")
    high = compare_forecast_to_field_observation(
        OpaqueEvidence(),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    setattr(OpaqueEvidence, metadata_name, "\udc00")
    low = compare_forecast_to_field_observation(
        OpaqueEvidence(),
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert high.identity_persistable is True
    assert low.identity_persistable is True
    assert high.source_digest != low.source_digest
    assert high.comparison_id != low.comparison_id


@pytest.mark.parametrize("surrogate", ["\ud800", "\udc00"])
def test_qualified_slot_metadata_is_redacted_and_total(surrogate):
    class SlottedLocation:
        __slots__ = ("marker",)

    location = SlottedLocation()
    location.marker = "same-state"
    marker_descriptor = vars(SlottedLocation)["marker"]
    SlottedLocation.__slots__ = (surrogate,)
    setattr(SlottedLocation, surrogate, marker_descriptor)
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(forecast_point, "requested_location", location)
    evidence = DecisionForecastEvidence((forecast_point,))

    first = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert first.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(first) == ("decision_forecast_evidence_invalid",)
    assert first.identity_persistable is True
    assert first.source_digest == repeated.source_digest
    assert first.comparison_id == repeated.comparison_id
    assert surrogate not in str(_canonical_evidence(evidence))


def test_qualified_slot_metadata_corruptions_remain_distinct():
    def result_with_slot_name(slot_name):
        class SlottedLocation:
            __slots__ = ("marker",)

        location = SlottedLocation()
        location.marker = "same-state"
        marker_descriptor = vars(SlottedLocation)["marker"]
        SlottedLocation.__slots__ = (slot_name,)
        setattr(SlottedLocation, slot_name, marker_descriptor)
        forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
        object.__setattr__(forecast_point, "requested_location", location)
        return compare_forecast_to_field_observation(
            DecisionForecastEvidence((forecast_point,)),
            observation(),
            computed_at_utc=COMPUTED_AT,
        )

    high = result_with_slot_name("\ud800")
    low = result_with_slot_name("\udc00")

    assert high.identity_persistable is True
    assert low.identity_persistable is True
    assert high.source_digest != low.source_digest
    assert high.comparison_id != low.comparison_id


@pytest.mark.parametrize("surrogate", ["\ud800", "\udc00"])
def test_arbitrary_tzinfo_type_metadata_is_redacted_and_total(surrogate):
    class CorruptedTimezone(tzinfo):
        __slots__ = ()

        def utcoffset(self, value):
            return timedelta(0)

        def dst(self, value):
            return timedelta(0)

        def tzname(self, value):
            return "CORRUPTED"

    CorruptedTimezone.__qualname__ = surrogate
    forecast_point = point(WeatherVariable.TEMPERATURE_C, 8.0)
    object.__setattr__(
        forecast_point,
        "retrieved_at_utc",
        RETRIEVED_AT.replace(tzinfo=CorruptedTimezone()),
    )
    evidence = DecisionForecastEvidence((forecast_point,))

    first = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )
    repeated = compare_forecast_to_field_observation(
        evidence,
        observation(),
        computed_at_utc=COMPUTED_AT,
    )

    assert first.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
    assert reason_codes(first) == ("decision_forecast_evidence_invalid",)
    assert first.identity_persistable is False
    assert first.source_digest == repeated.source_digest
    assert first.comparison_id == repeated.comparison_id
    assert surrogate not in str(_canonical_evidence(evidence))


def test_valid_unicode_identity_strings_remain_deterministic():
    source = observation()
    object.__setattr__(
        source.provenance,
        "source_id",
        "station-météo-東京-🔭",
    )
    forecast_point = point(
        WeatherVariable.TEMPERATURE_C,
        8.0,
        provider="météo-東京-☀️",
        model="modèle-気象-🌙",
    )
    parameters = ForecastObservationParameters()
    object.__setattr__(
        parameters.temporal_policy,
        "version",
        "nearest-prévision-時間-⏱️",
    )
    object.__setattr__(
        parameters.cloud_mapping_policy,
        "version",
        "nuages-échelle-雲-☁️",
    )

    first = compare(
        source,
        forecast_point,
        algorithm_version="comparaison-prévision-観測-🔭",
        parameters=parameters,
    )
    second = compare(
        source,
        forecast_point,
        algorithm_version="comparaison-prévision-観測-🔭",
        parameters=parameters,
    )

    assert first.status is ForecastObservationComparisonStatus.COMPARABLE
    assert first.identity_persistable is True
    assert first.source_digest == second.source_digest
    assert first.comparison_id == second.comparison_id


def test_valid_evidence_identity_is_unchanged_by_redacted_metadata_tokens():
    result = compare(
        observation(),
        point(WeatherVariable.TEMPERATURE_C, 8.0),
    )

    assert result.source_digest == (
        "ce68eaedc955bf4a0a31093a5494ba8eb35f54a66ed1b97ddd12fe328e35fbe1"
    )
    assert result.comparison_id == (
        "a7a6e47d84cb64bcff124e59802c3e18566b015501ab7e88b4482aaed23bcf36"
    )


def test_canonical_algorithm_version_is_stable():
    first = compare(
        observation(),
        point(WeatherVariable.TEMPERATURE_C, 8.0),
        algorithm_version="forecast_observation.v1",
    )
    second = compare(
        observation(),
        point(WeatherVariable.TEMPERATURE_C, 8.0),
        algorithm_version="forecast_observation.v1",
    )

    assert first.algorithm_version == "forecast_observation.v1"
    assert first.comparison_id == second.comparison_id


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


@pytest.mark.parametrize("path", [MODEL_PATH, SERVICE_PATH])
def test_model_and_engine_imports_match_explicit_dependency_allowlist(path):
    source = path.read_text(encoding="utf-8")

    assert import_boundary_violations(source, ALLOWED_IMPORTS[path]) == ()


def test_import_guard_rejects_forbidden_symbol_from_allowed_generic_module():
    source = "from decision.field_observation import OutcomeAssessment as harmless"
    allowed = {("decision.field_observation", "FieldObservation")}

    assert import_boundary_violations(source, allowed) == (
        ("decision.field_observation", "OutcomeAssessment", "harmless"),
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from . import persistence", ((None, "persistence", None),)),
        (
            "from .decision.field_observation import FieldObservation",
            (("decision.field_observation", "FieldObservation", None),),
        ),
    ],
)
def test_import_guard_rejects_all_relative_imports(source, expected):
    allowed = {("decision.field_observation", "FieldObservation")}

    assert import_boundary_violations(source, allowed) == expected
