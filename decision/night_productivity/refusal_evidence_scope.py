"""Scope of a refusal diagnostic; never changes productive-window eligibility."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from math import isfinite

from decision.night_productivity.productivity_diagnostics import (
    PRODUCTIVE_SLICE_THRESHOLD,
    ProductivityBreakdown,
    SliceProductivityEvaluation,
)


def _utc(value):
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ProductivityEvidenceScope:
    candidate_start: datetime
    candidate_end: datetime
    availability_start: datetime | None
    availability_end: datetime | None
    evaluated_start: datetime | None
    evaluated_end: datetime | None
    partial_slice_count: int | None = None
    best_source_slice_start: datetime | None = None
    best_source_slice_end: datetime | None = None
    score_policy: str = "reuse_source_slice_scores"

    def __post_init__(self):
        for value in (
            self.candidate_start, self.candidate_end,
            self.availability_start, self.availability_end,
            self.evaluated_start, self.evaluated_end,
            self.best_source_slice_start, self.best_source_slice_end,
        ):
            if value is not None and (
                not isinstance(value, datetime) or value.utcoffset() is None
            ):
                raise ValueError("scope_aware_time_required")
        if not isinstance(self.candidate_start, datetime) or not isinstance(self.candidate_end, datetime):
            raise ValueError("scope_candidate_required")
        if _utc(self.candidate_end) <= _utc(self.candidate_start):
            raise ValueError("scope_candidate_not_forward")
        if (self.availability_start is not None and self.availability_end is not None
                and _utc(self.availability_end) <= _utc(self.availability_start)):
            raise ValueError("scope_availability_not_forward")
        lower = max(_utc(self.candidate_start), _utc(self.availability_start)) if self.availability_start else _utc(self.candidate_start)
        upper = min(_utc(self.candidate_end), _utc(self.availability_end)) if self.availability_end else _utc(self.candidate_end)
        if upper <= lower:
            if self.evaluated_start is not None or self.evaluated_end is not None:
                raise ValueError("scope_empty_intersection_required")
        elif (self.evaluated_start is None or self.evaluated_end is None
                or _utc(self.evaluated_start) != lower or _utc(self.evaluated_end) != upper):
            raise ValueError("scope_intersection_mismatch")
        if self.partial_slice_count is not None and (
            isinstance(self.partial_slice_count, bool)
            or not isinstance(self.partial_slice_count, int)
            or self.partial_slice_count < 0
        ):
            raise ValueError("scope_partial_count_invalid")
        if (self.best_source_slice_start is None) != (self.best_source_slice_end is None):
            raise ValueError("scope_source_pair_required")
        if self.best_source_slice_start is not None and not (
            _utc(self.candidate_start) <= _utc(self.best_source_slice_start)
            < _utc(self.best_source_slice_end) <= _utc(self.candidate_end)
        ):
            raise ValueError("scope_source_outside_candidate")
        if self.score_policy != "reuse_source_slice_scores":
            raise ValueError("scope_score_policy_invalid")


def scoped_refusal_breakdown(assessment, lower, upper):
    """Clip existing slice support and reuse exact evaluations, never rescore.

    A partial portion has its source slice's score/losses, explicitly reported.
    Missing/inconsistent per-slice evidence yields no scoped factor attribution.
    """
    start, end = _utc(assessment.window_start), _utc(assessment.window_end)
    lo = max(start, _utc(lower)) if lower else start
    hi = min(end, _utc(upper)) if upper else end
    zone = assessment.window_start.tzinfo
    scope = ProductivityEvidenceScope(
        candidate_start=assessment.window_start,
        candidate_end=assessment.window_end,
        availability_start=lower,
        availability_end=upper,
        evaluated_start=lo.astimezone(zone) if hi > lo else None,
        evaluated_end=hi.astimezone(zone) if hi > lo else None,
    )
    if hi <= lo:
        return (
            ProductivityBreakdown(0, 0, None, None, None, None, PRODUCTIVE_SLICE_THRESHOLD, None),
            replace(scope, partial_slice_count=0),
        )
    timeline = getattr(assessment.productivity, "timeline", None)
    slices = getattr(timeline, "slices", timeline)
    evaluations = assessment.productivity_slice_evaluations
    # Legacy/custom evaluators may supply only a global summary. Reuse it only
    # when its full original interval exactly matches the requested scope.
    if not slices or not evaluations or len(slices) != len(evaluations):
        breakdown = assessment.productivity_breakdown if lo == start and hi == end else None
        return breakdown, scope
    portions = []
    cursor = start
    for source, evaluation in zip(slices, evaluations):
        if not isinstance(evaluation, SliceProductivityEvaluation):
            return None, scope
        start_hour = getattr(source, "start_hour", None)
        end_hour = getattr(source, "end_hour", None)
        score = getattr(source, "productivity_score", None)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not isfinite(value) for value in (start_hour, end_hour, score)):
            return None, scope
        source_start = start + timedelta(hours=start_hour)
        source_end = start + timedelta(hours=end_hour)
        if (source_start != cursor or not source_start < source_end <= end
                or score != evaluation.score):
            return None, scope
        cursor = source_end
        portion_start, portion_end = max(lo, source_start), min(hi, source_end)
        if portion_end > portion_start:
            portions.append((portion_start, portion_end, source_start, source_end, evaluation))
    if cursor != end or not portions:
        return None, scope
    best_score = max(item[4].score for item in portions)
    chosen = next(item for item in portions if item[4].score == best_score)
    partial_count = sum(a != source_a or b != source_b for a, b, source_a, source_b, _ in portions)
    scope = replace(
        scope,
        partial_slice_count=partial_count,
        best_source_slice_start=chosen[2].astimezone(zone),
        best_source_slice_end=chosen[3].astimezone(zone),
    )
    return ProductivityBreakdown(
        evaluated_slice_count=len(portions),
        productive_slice_count=sum(item[4].score >= PRODUCTIVE_SLICE_THRESHOLD for item in portions),
        best_slice_start=chosen[0].astimezone(zone),
        best_slice_end=chosen[1].astimezone(zone),
        best_slice_score=best_score,
        best_slice_tie_count=sum(item[4].score == best_score for item in portions),
        productive_slice_threshold=PRODUCTIVE_SLICE_THRESHOLD,
        losses=chosen[4].losses,
    ), scope
