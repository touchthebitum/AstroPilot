from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import ceil, isfinite, sqrt

from decision.weather.provider_reliability import (
    ComparisonStatus,
    WeatherForecastVerification,
    WeatherLocation,
    WeatherVariable,
)


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _distance_km(first: WeatherLocation, second: WeatherLocation) -> float:
    from math import asin, cos, radians, sin

    delta_lat = radians(second.latitude - first.latitude)
    delta_lon = radians(second.longitude - first.longitude)
    first_latitude = radians(first.latitude)
    second_latitude = radians(second.latitude)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(first_latitude)
        * cos(second_latitude)
        * sin(delta_lon / 2) ** 2
    )
    return 2 * 6371.0 * asin(sqrt(haversine))


@dataclass(frozen=True)
class ReliabilityReportScope:
    center: WeatherLocation
    radius_km: float
    starts_at_utc: datetime
    ends_at_utc: datetime

    def __post_init__(self):
        if not isinstance(self.center, WeatherLocation):
            raise ValueError("invalid_reliability_scope_center")
        if (
            isinstance(self.radius_km, bool)
            or not isinstance(self.radius_km, (int, float))
            or not isfinite(float(self.radius_km))
            or self.radius_km < 0
        ):
            raise ValueError("invalid_reliability_scope_radius")
        starts_at = _utc(self.starts_at_utc, "scope_starts_at")
        ends_at = _utc(self.ends_at_utc, "scope_ends_at")
        if ends_at < starts_at:
            raise ValueError("invalid_reliability_scope_interval")
        object.__setattr__(self, "radius_km", float(self.radius_km))
        object.__setattr__(self, "starts_at_utc", starts_at)
        object.__setattr__(self, "ends_at_utc", ends_at)

    def exclusion_reasons(
        self, verification: WeatherForecastVerification
    ) -> tuple[str, ...]:
        reasons = []
        if not self.starts_at_utc <= verification.forecast_for_utc <= self.ends_at_utc:
            reasons.append("forecast_time_outside_report_scope")
        if _distance_km(self.center, verification.requested_location) > self.radius_km:
            reasons.append("requested_location_outside_report_scope")
        return tuple(reasons)


@dataclass(frozen=True)
class HorizonBucket:
    name: str
    start: timedelta
    end: timedelta | None

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("invalid_horizon_bucket_name")
        if not isinstance(self.start, timedelta) or self.start < timedelta(0):
            raise ValueError("invalid_horizon_bucket_start")
        if self.end is not None and (
            not isinstance(self.end, timedelta) or self.end <= self.start
        ):
            raise ValueError("invalid_horizon_bucket_end")
        object.__setattr__(self, "name", self.name.strip())

    def contains(self, horizon: timedelta) -> bool:
        return horizon >= self.start and (self.end is None or horizon < self.end)


@dataclass(frozen=True)
class ReliabilityMetricsPolicy:
    horizon_buckets: tuple[HorizonBucket, ...]
    minimum_sample_size: int

    def __post_init__(self):
        buckets = tuple(self.horizon_buckets)
        if not buckets:
            raise ValueError("horizon_buckets_required")
        if isinstance(self.minimum_sample_size, bool) or not isinstance(
            self.minimum_sample_size, int
        ) or self.minimum_sample_size <= 0:
            raise ValueError("invalid_minimum_sample_size")
        if buckets[0].start != timedelta(0):
            raise ValueError("horizon_buckets_must_start_at_zero")
        for previous, current in zip(buckets, buckets[1:]):
            if previous.end is None or previous.end != current.start:
                raise ValueError("horizon_buckets_must_be_contiguous")
        if buckets[-1].end is not None:
            raise ValueError("horizon_buckets_must_cover_all_horizons")
        names = [bucket.name for bucket in buckets]
        if len(set(names)) != len(names):
            raise ValueError("duplicate_horizon_bucket_name")
        object.__setattr__(self, "horizon_buckets", buckets)

    def bucket_for(self, horizon: timedelta) -> HorizonBucket:
        if not isinstance(horizon, timedelta) or horizon < timedelta(0):
            raise ValueError("invalid_forecast_horizon")
        for bucket in self.horizon_buckets:
            if bucket.contains(horizon):
                return bucket
        raise ValueError("forecast_horizon_not_covered")


class EvidenceStatus(str, Enum):
    INSUFFICIENT = "insufficient"
    ELIGIBLE = "eligible"


@dataclass(frozen=True)
class ProviderComparisonCoverage:
    provider_id: str
    model_id: str | None
    horizon_bucket: str
    total_count: int
    comparable_count: int
    not_comparable_count: int
    not_comparable_reasons: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ProviderVariableMetrics:
    provider_id: str
    model_id: str | None
    variable: WeatherVariable
    unit: str
    horizon_bucket: str
    sample_count: int
    evidence_status: EvidenceStatus
    mean_signed_error: float
    mean_absolute_error: float
    root_mean_squared_error: float
    median_absolute_error: float
    percentile_90_absolute_error: float
    maximum_absolute_error: float


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = ceil(percentile * len(ordered))
    return ordered[rank - 1]


@dataclass(frozen=True)
class ProviderReliabilityReport:
    scope: ReliabilityReportScope
    coverage: tuple[ProviderComparisonCoverage, ...]
    variable_metrics: tuple[ProviderVariableMetrics, ...]
    context_exclusions: tuple["ProviderContextExclusions", ...] = ()


@dataclass(frozen=True)
class ProviderContextExclusions:
    provider_id: str
    model_id: str | None
    excluded_count: int
    reasons: tuple[tuple[str, int], ...]


def build_provider_reliability_report(
    verifications: tuple[WeatherForecastVerification, ...],
    *,
    policy: ReliabilityMetricsPolicy,
    scope: ReliabilityReportScope,
) -> ProviderReliabilityReport:
    if not isinstance(policy, ReliabilityMetricsPolicy):
        raise ValueError("reliability_metrics_policy_required")
    if not isinstance(scope, ReliabilityReportScope):
        raise ValueError("reliability_report_scope_required")

    coverage = defaultdict(lambda: {"total": 0, "comparable": 0, "reasons": Counter()})
    samples = defaultdict(list)
    exclusions = defaultdict(lambda: {"count": 0, "reasons": Counter()})

    for verification in tuple(verifications):
        if not isinstance(verification, WeatherForecastVerification):
            raise ValueError("invalid_forecast_verification")
        context_reasons = scope.exclusion_reasons(verification)
        if context_reasons:
            exclusion = exclusions[(verification.provider_id, verification.model_id)]
            exclusion["count"] += 1
            exclusion["reasons"].update(context_reasons)
            continue
        bucket = policy.bucket_for(verification.horizon)
        coverage_key = (verification.provider_id, verification.model_id, bucket.name)
        group = coverage[coverage_key]
        group["total"] += 1

        if verification.status is not ComparisonStatus.COMPARABLE:
            group["reasons"].update(verification.reasons)
            continue

        group["comparable"] += 1
        for error in verification.errors:
            sample_key = (
                verification.provider_id,
                verification.model_id,
                error.variable,
                error.unit,
                bucket.name,
            )
            samples[sample_key].append(error)

    coverage_results = []
    for (provider_id, model_id, bucket_name), group in sorted(
        coverage.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2])
    ):
        comparable_count = group["comparable"]
        coverage_results.append(
            ProviderComparisonCoverage(
                provider_id=provider_id,
                model_id=model_id,
                horizon_bucket=bucket_name,
                total_count=group["total"],
                comparable_count=comparable_count,
                not_comparable_count=group["total"] - comparable_count,
                not_comparable_reasons=tuple(sorted(group["reasons"].items())),
            )
        )

    metric_results = []
    for (provider_id, model_id, variable, unit, bucket_name), errors in sorted(
        samples.items(),
        key=lambda item: (
            item[0][0],
            item[0][1] or "",
            item[0][2].value,
            item[0][4],
        ),
    ):
        sample_count = len(errors)
        absolute_errors = [error.absolute_error for error in errors]
        metric_results.append(
            ProviderVariableMetrics(
                provider_id=provider_id,
                model_id=model_id,
                variable=variable,
                unit=unit,
                horizon_bucket=bucket_name,
                sample_count=sample_count,
                evidence_status=(
                    EvidenceStatus.ELIGIBLE
                    if sample_count >= policy.minimum_sample_size
                    else EvidenceStatus.INSUFFICIENT
                ),
                mean_signed_error=(
                    sum(error.signed_error for error in errors) / sample_count
                ),
                mean_absolute_error=(
                    sum(error.absolute_error for error in errors) / sample_count
                ),
                root_mean_squared_error=sqrt(
                    sum(error.signed_error**2 for error in errors) / sample_count
                ),
                median_absolute_error=_median(absolute_errors),
                percentile_90_absolute_error=_nearest_rank_percentile(
                    absolute_errors, 0.90
                ),
                maximum_absolute_error=max(absolute_errors),
            )
        )

    exclusion_results = tuple(
        ProviderContextExclusions(
            provider_id=provider_id,
            model_id=model_id,
            excluded_count=values["count"],
            reasons=tuple(sorted(values["reasons"].items())),
        )
        for (provider_id, model_id), values in sorted(
            exclusions.items(), key=lambda item: (item[0][0], item[0][1] or "")
        )
    )

    return ProviderReliabilityReport(
        scope=scope,
        coverage=tuple(coverage_results),
        variable_metrics=tuple(metric_results),
        context_exclusions=exclusion_results,
    )
