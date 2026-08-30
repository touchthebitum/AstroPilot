from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from decision.weather.provider_reliability import WeatherLocation, WeatherVariable
from decision.weather.provider_reliability_metrics import (
    EvidenceStatus,
    ProviderReliabilityReport,
    ReliabilityReportScope,
)
from decision.weather.weather_ingress import WeatherFreshness, WeatherSnapshot


class WeatherEvidenceQuality(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    INVALID = "invalid"


class WeatherDecisionAdmissibility(str, Enum):
    ADMISSIBLE = "admissible"
    CAUTION = "caution"
    REFUSED = "refused"


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid_{name}")
    return value.strip()


@dataclass(frozen=True)
class WeatherDecisionContext:
    provider_id: str
    model_id: str | None
    reference_source_id: str
    horizon_bucket: str
    required_variables: tuple[WeatherVariable, ...]
    reliability_scope: ReliabilityReportScope
    decision_location: WeatherLocation

    def __post_init__(self):
        variables = tuple(self.required_variables)
        if not variables:
            raise ValueError("required_weather_variables_missing")
        if any(not isinstance(variable, WeatherVariable) for variable in variables):
            raise ValueError("invalid_required_weather_variable")
        if len(set(variables)) != len(variables):
            raise ValueError("duplicate_required_weather_variable")
        if not isinstance(self.reliability_scope, ReliabilityReportScope):
            raise ValueError("reliability_report_scope_required")
        if not isinstance(self.decision_location, WeatherLocation):
            raise ValueError("weather_decision_location_required")

        object.__setattr__(
            self,
            "provider_id",
            _identity(self.provider_id, "provider_id"),
        )
        object.__setattr__(
            self,
            "reference_source_id",
            _identity(self.reference_source_id, "reference_source_id"),
        )
        object.__setattr__(
            self,
            "horizon_bucket",
            _identity(self.horizon_bucket, "horizon_bucket"),
        )
        if self.model_id is not None:
            object.__setattr__(self, "model_id", _identity(self.model_id, "model_id"))
        object.__setattr__(
            self,
            "required_variables",
            tuple(sorted(variables, key=lambda variable: variable.value)),
        )


@dataclass(frozen=True)
class WeatherTrustEvidence:
    snapshot: WeatherSnapshot | None
    freshness: WeatherFreshness | None
    selected_window_covered: bool | None
    provider_reliability: ProviderReliabilityReport | None = None
    integrity_issues: tuple[str, ...] = ()

    def __post_init__(self):
        if self.snapshot is not None and not isinstance(self.snapshot, WeatherSnapshot):
            raise ValueError("invalid_weather_snapshot")
        if self.freshness is not None and not isinstance(
            self.freshness, WeatherFreshness
        ):
            raise ValueError("invalid_weather_freshness")
        if self.selected_window_covered not in (True, False, None):
            raise ValueError("invalid_selected_window_coverage")
        if self.provider_reliability is not None and not isinstance(
            self.provider_reliability,
            ProviderReliabilityReport,
        ):
            raise ValueError("invalid_provider_reliability_report")

        issues = tuple(self.integrity_issues)
        if any(not isinstance(issue, str) or not issue.strip() for issue in issues):
            raise ValueError("invalid_weather_integrity_issue")
        object.__setattr__(
            self,
            "integrity_issues",
            tuple(sorted(set(issue.strip() for issue in issues))),
        )


@dataclass(frozen=True)
class WeatherTrustDecision:
    evidence_quality: WeatherEvidenceQuality
    admissibility: WeatherDecisionAdmissibility
    reasons: tuple[str, ...]


class WeatherTrustDecisionEvaluator:
    @staticmethod
    def evaluate(
        evidence: WeatherTrustEvidence,
        *,
        context: WeatherDecisionContext,
    ) -> WeatherTrustDecision:
        if not isinstance(evidence, WeatherTrustEvidence):
            raise ValueError("weather_trust_evidence_required")
        if not isinstance(context, WeatherDecisionContext):
            raise ValueError("weather_decision_context_required")

        invalid_reasons = list(evidence.integrity_issues)
        if (
            evidence.snapshot is not None
            and evidence.snapshot.provider != context.provider_id
        ):
            invalid_reasons.append("weather_provider_mismatch")
        if evidence.snapshot is not None and (
            evidence.snapshot.requested_latitude
            != context.decision_location.latitude
            or evidence.snapshot.requested_longitude
            != context.decision_location.longitude
        ):
            invalid_reasons.append("weather_location_mismatch")
        if invalid_reasons:
            return WeatherTrustDecision(
                evidence_quality=WeatherEvidenceQuality.INVALID,
                admissibility=WeatherDecisionAdmissibility.REFUSED,
                reasons=tuple(sorted(set(invalid_reasons))),
            )

        required_reasons = []
        if evidence.snapshot is None:
            required_reasons.append("weather_snapshot_missing")
        if evidence.freshness is None:
            required_reasons.append("weather_freshness_missing")
        elif evidence.freshness.freshness_status != "fresh":
            required_reasons.append("weather_not_fresh")
        if evidence.selected_window_covered is not True:
            required_reasons.append(
                "selected_window_uncovered"
                if evidence.selected_window_covered is False
                else "selected_window_coverage_unknown"
            )
        if required_reasons:
            return WeatherTrustDecision(
                evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
                admissibility=WeatherDecisionAdmissibility.REFUSED,
                reasons=tuple(required_reasons),
            )

        report = evidence.provider_reliability
        if report is None:
            return WeatherTrustDecision(
                evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
                admissibility=WeatherDecisionAdmissibility.CAUTION,
                reasons=("provider_reliability_unavailable",),
            )
        if report.scope != context.reliability_scope:
            return WeatherTrustDecision(
                evidence_quality=WeatherEvidenceQuality.INSUFFICIENT,
                admissibility=WeatherDecisionAdmissibility.CAUTION,
                reasons=("provider_report_scope_mismatch",),
            )

        matching_metrics = {
            metric.variable: metric
            for metric in report.variable_metrics
            if metric.provider_id == context.provider_id
            and metric.model_id == context.model_id
            and metric.reference_source_id == context.reference_source_id
            and metric.horizon_bucket == context.horizon_bucket
        }
        reasons = []

        matching_exclusions = [
            exclusion
            for exclusion in report.context_exclusions
            if exclusion.provider_id == context.provider_id
            and exclusion.model_id == context.model_id
            and exclusion.reference_source_id == context.reference_source_id
        ]
        for exclusion in matching_exclusions:
            reasons.extend(
                f"provider_context_excluded:{reason}"
                for reason, _ in exclusion.reasons
            )

        matching_coverage = [
            coverage
            for coverage in report.coverage
            if coverage.provider_id == context.provider_id
            and coverage.model_id == context.model_id
            and coverage.reference_source_id == context.reference_source_id
            and coverage.horizon_bucket == context.horizon_bucket
        ]
        for coverage in matching_coverage:
            reasons.extend(
                f"provider_comparison_excluded:{reason}"
                for reason, _ in coverage.not_comparable_reasons
            )

        if not matching_metrics and not matching_coverage:
            reasons.append("provider_context_not_evaluated")

        insufficient = False
        for variable in context.required_variables:
            metric = matching_metrics.get(variable)
            if metric is None:
                reasons.append(f"provider_evidence_missing:{variable.value}")
                insufficient = True
                continue
            if metric.evidence_status is EvidenceStatus.INSUFFICIENT:
                reasons.append(f"provider_evidence_insufficient:{variable.value}")
                insufficient = True
            reasons.append(
                f"maximum_absolute_error:{variable.value}:"
                f"{metric.maximum_absolute_error:g}"
            )

        return WeatherTrustDecision(
            evidence_quality=(
                WeatherEvidenceQuality.INSUFFICIENT
                if insufficient
                else WeatherEvidenceQuality.SUFFICIENT
            ),
            admissibility=(
                WeatherDecisionAdmissibility.CAUTION
                if insufficient
                else WeatherDecisionAdmissibility.ADMISSIBLE
            ),
            reasons=tuple(dict.fromkeys(reasons)),
        )
