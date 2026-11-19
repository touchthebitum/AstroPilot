"""Immutable diagnostics produced by productive-window evaluation, without recalculation."""

from datetime import timezone
from dataclasses import dataclass
from enum import Enum
from math import isfinite

from decision.night_productivity.productivity_diagnostics import ProductivityBreakdown
from decision.night_productivity.refusal_evidence_scope import ProductivityEvidenceScope


class ActionabilityRefusalConclusion(str, Enum):
    NO_PRODUCTIVE_WINDOW = "no_productive_window"
    USER_AVAILABILITY_REQUIRED = "user_availability_required"


class ActionabilityRefusalStatus(str, Enum):
    CONSTRAINTS_REFUSAL = "constraints_refusal"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ProductivityRefusalStage(str, Enum):
    NO_PRODUCTIVE_SLICE = "no_productive_slice"
    CONTINUOUS_WINDOW_TOO_SHORT = "continuous_window_too_short"


@dataclass(frozen=True, slots=True)
class ActionabilityRefusal:
    conclusion: ActionabilityRefusalConclusion
    status: ActionabilityRefusalStatus
    cause_code: str | None
    best_productive_window_minutes: float | None
    required_continuous_minutes: int
    limiting_factors: tuple[dict[str, str], ...] = ()
    refusal_stage: ProductivityRefusalStage | None = None
    productivity_breakdown: ProductivityBreakdown | None = None
    evidence_scope: ProductivityEvidenceScope | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.conclusion, ActionabilityRefusalConclusion):
            raise TypeError("Expected ActionabilityRefusalConclusion")
        if not isinstance(self.status, ActionabilityRefusalStatus):
            raise TypeError("Expected ActionabilityRefusalStatus")
        if self.cause_code is not None and not isinstance(self.cause_code, str):
            raise TypeError("actionability_refusal_cause_code_must_be_string")
        if (
            self.best_productive_window_minutes is not None
            and (
                not isinstance(self.best_productive_window_minutes, (int, float))
                or isinstance(self.best_productive_window_minutes, bool)
                or not isfinite(self.best_productive_window_minutes)
                or self.best_productive_window_minutes < 0
            )
        ):
            raise ValueError("best_productive_window_minutes_invalid")
        if (
            not isinstance(self.required_continuous_minutes, int)
            or isinstance(self.required_continuous_minutes, bool)
            or self.required_continuous_minutes <= 0
        ):
            raise ValueError("required_continuous_minutes_invalid")
        if not isinstance(self.limiting_factors, tuple):
            raise TypeError("limiting_factors_must_be_tuple")
        if (
            self.refusal_stage is not None
            and not isinstance(self.refusal_stage, ProductivityRefusalStage)
        ):
            raise TypeError("Expected ProductivityRefusalStage or None")
        if (
            self.productivity_breakdown is not None
            and not isinstance(
                self.productivity_breakdown,
                ProductivityBreakdown,
            )
        ):
            raise TypeError("Expected ProductivityBreakdown or None")
        if (
            self.status is ActionabilityRefusalStatus.CONSTRAINTS_REFUSAL
            and self.best_productive_window_minutes is None
        ):
            raise ValueError("constraint_refusal_requires_known_duration")
        if (
            self.status is ActionabilityRefusalStatus.INSUFFICIENT_EVIDENCE
            and self.best_productive_window_minutes is not None
        ):
            raise ValueError("insufficient_evidence_requires_unknown_duration")
        if (
            self.status is ActionabilityRefusalStatus.INSUFFICIENT_EVIDENCE
            and (
                self.refusal_stage is not None
                or self.productivity_breakdown is not None
            )
        ):
            raise ValueError("insufficient_evidence_forbids_productivity_breakdown")
        if self.evidence_scope is not None:
            if not isinstance(self.evidence_scope, ProductivityEvidenceScope):
                raise TypeError("Expected ProductivityEvidenceScope")
            if self.status is not ActionabilityRefusalStatus.CONSTRAINTS_REFUSAL:
                raise ValueError("scope_requires_constraints_refusal")
            breakdown = self.productivity_breakdown
            if breakdown is not None:
                count = self.evidence_scope.partial_slice_count
                if count is not None and count > breakdown.evaluated_slice_count:
                    raise ValueError("scope_partial_count_exceeds_evaluated")
                if breakdown.evaluated_slice_count:
                    scope = self.evidence_scope
                    if (scope.evaluated_start is None or scope.evaluated_end is None
                            or not scope.evaluated_start.astimezone(timezone.utc) <= breakdown.best_slice_start.astimezone(timezone.utc) < breakdown.best_slice_end.astimezone(timezone.utc) <= scope.evaluated_end.astimezone(timezone.utc)):
                        raise ValueError("scope_best_slice_outside_intersection")
        if self.productivity_breakdown is not None:
            expected_stage = (
                ProductivityRefusalStage.NO_PRODUCTIVE_SLICE
                if self.productivity_breakdown.productive_slice_count == 0
                else ProductivityRefusalStage.CONTINUOUS_WINDOW_TOO_SHORT
            )
            if self.refusal_stage is not expected_stage:
                raise ValueError("productivity_breakdown_stage_mismatch")
