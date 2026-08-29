from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from math import sqrt

from decision.weather.provider_reliability import (
    ComparisonStatus,
    WeatherForecastVerification,
    WeatherVariable,
)


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


@dataclass(frozen=True)
class ProviderReliabilityReport:
    coverage: tuple[ProviderComparisonCoverage, ...]
    variable_metrics: tuple[ProviderVariableMetrics, ...]


def build_provider_reliability_report(
    verifications: tuple[WeatherForecastVerification, ...],
    *,
    policy: ReliabilityMetricsPolicy,
) -> ProviderReliabilityReport:
    if not isinstance(policy, ReliabilityMetricsPolicy):
        raise ValueError("reliability_metrics_policy_required")

    coverage = defaultdict(lambda: {"total": 0, "comparable": 0, "reasons": Counter()})
    samples = defaultdict(list)

    for verification in tuple(verifications):
        if not isinstance(verification, WeatherForecastVerification):
            raise ValueError("invalid_forecast_verification")
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
            )
        )

    return ProviderReliabilityReport(
        coverage=tuple(coverage_results),
        variable_metrics=tuple(metric_results),
    )
