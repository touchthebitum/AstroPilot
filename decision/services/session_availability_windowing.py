from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import isfinite

from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityReason,
    AcquisitionIntentEvidenceGap,
)
from decision.night_productivity.productivity_diagnostics import (
    ProductivityBreakdown,
)


MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW = timedelta(hours=1)


class ActionabilityRefusalConclusion(str, Enum):
    NO_PRODUCTIVE_WINDOW = "no_productive_window"


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
        if self.productivity_breakdown is not None:
            expected_stage = (
                ProductivityRefusalStage.NO_PRODUCTIVE_SLICE
                if self.productivity_breakdown.productive_slice_count == 0
                else ProductivityRefusalStage.CONTINUOUS_WINDOW_TOO_SHORT
            )
            if self.refusal_stage is not expected_stage:
                raise ValueError("productivity_breakdown_stage_mismatch")


@dataclass(frozen=True, slots=True)
class ActionableProductiveWindowSelection:
    window: "SessionAvailabilityWindow | None"
    refusal: ActionabilityRefusal | None

    def __post_init__(self) -> None:
        if (self.window is None) == (self.refusal is None):
            raise ValueError("actionability_selection_requires_one_outcome")


@dataclass(frozen=True, slots=True)
class SessionAvailabilityWindow:
    window_start: datetime
    window_end: datetime


def _elapsed_hours(start: datetime, end: datetime) -> float:
    return (
        end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    ).total_seconds() / 3600


def _at_elapsed_hour(start: datetime, elapsed_hour: float) -> datetime:
    return (
        start.astimezone(timezone.utc) + timedelta(hours=elapsed_hour)
    ).astimezone(start.tzinfo)


def select_continuous_actionable_productive_window(
    assessment: ProductiveWindowAssessment,
    availability: SessionAvailability | None,
) -> SessionAvailabilityWindow | None:
    """Select one real productive interval meeting the V1 session minimum."""
    return evaluate_continuous_actionable_productive_window(
        assessment,
        availability,
    ).window


def _required_continuous_minutes() -> int:
    return int(MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW.total_seconds() / 60)


def _refusal(
    *,
    status: ActionabilityRefusalStatus,
    cause_code: str | None,
    best_minutes: float | None,
    refusal_stage: ProductivityRefusalStage | None = None,
    productivity_breakdown: ProductivityBreakdown | None = None,
) -> ActionableProductiveWindowSelection:
    return ActionableProductiveWindowSelection(
        window=None,
        refusal=ActionabilityRefusal(
            conclusion=ActionabilityRefusalConclusion.NO_PRODUCTIVE_WINDOW,
            status=status,
            cause_code=cause_code,
            best_productive_window_minutes=best_minutes,
            required_continuous_minutes=_required_continuous_minutes(),
            refusal_stage=refusal_stage,
            productivity_breakdown=productivity_breakdown,
        ),
    )


def _missing_evidence_refusal() -> ActionableProductiveWindowSelection:
    return _refusal(
        status=ActionabilityRefusalStatus.INSUFFICIENT_EVIDENCE,
        cause_code=(
            AcquisitionIntentEvidenceGap.PRODUCTIVE_WINDOW_EVIDENCE_MISSING.value
        ),
        best_minutes=None,
    )


def evaluate_continuous_actionable_productive_window(
    assessment: ProductiveWindowAssessment,
    availability: SessionAvailability | None,
) -> ActionableProductiveWindowSelection:
    """Select a window and preserve the authoritative refusal diagnostic."""
    if not isinstance(assessment, ProductiveWindowAssessment):
        raise TypeError("Expected ProductiveWindowAssessment")
    if availability is not None and not isinstance(
        availability,
        SessionAvailability,
    ):
        raise TypeError("Expected SessionAvailability or None")

    analysis_start = assessment.window_start
    analysis_end = assessment.window_end
    if analysis_start is None and analysis_end is None:
        return _missing_evidence_refusal()
    if (
        not isinstance(analysis_start, datetime)
        or not isinstance(analysis_end, datetime)
        or analysis_start.tzinfo is None
        or analysis_end.tzinfo is None
        or analysis_start.utcoffset() is None
        or analysis_end.utcoffset() is None
        or analysis_end.astimezone(timezone.utc)
        <= analysis_start.astimezone(timezone.utc)
    ):
        return _missing_evidence_refusal()

    lower_bound = None
    upper_bound = None
    duration_caps = []
    maximum_mission_hours = assessment.maximum_mission_hours
    if maximum_mission_hours is not None:
        if (
            not isinstance(maximum_mission_hours, (int, float))
            or isinstance(maximum_mission_hours, bool)
            or not isfinite(maximum_mission_hours)
            or maximum_mission_hours < 0
        ):
            raise ValueError("maximum_mission_hours_invalid")
        duration_caps.append(timedelta(hours=maximum_mission_hours))
    if availability is not None:
        if availability.mode is SessionAvailabilityMode.FIXED_WINDOW:
            lower_bound = availability.start
            upper_bound = availability.end
        elif availability.mode is SessionAvailabilityMode.START_AND_DURATION:
            lower_bound = availability.start
            upper_bound = (
                availability.start.astimezone(timezone.utc)
                + availability.duration
            ).astimezone(availability.start.tzinfo)
        elif availability.mode is SessionAvailabilityMode.UNTIL:
            upper_bound = availability.end
        elif availability.mode is SessionAvailabilityMode.DURATION:
            duration_caps.append(availability.duration)
        elif availability.mode is not SessionAvailabilityMode.ALL_NIGHT:
            raise ValueError("session_availability_mode_inactive")

    duration_cap = min(duration_caps) if duration_caps else None
    productive_windows = getattr(assessment.productivity, "windows", None)
    if productive_windows is None:
        return _missing_evidence_refusal()

    analysis_hours = _elapsed_hours(analysis_start, analysis_end)
    candidates = []
    best_rejected_duration = timedelta(0)
    for window in productive_windows:
        values = (
            getattr(window, "start_hour", None),
            getattr(window, "end_hour", None),
            getattr(window, "productivity", None),
        )
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            for value in values
        ):
            return _missing_evidence_refusal()
        start_hour, end_hour, productivity = values
        if (
            start_hour < 0
            or end_hour <= start_hour
            or end_hour > analysis_hours + 1e-9
            or not getattr(window, "productive", False)
        ):
            return _missing_evidence_refusal()

        start = _at_elapsed_hour(analysis_start, start_hour)
        end = _at_elapsed_hour(analysis_start, end_hour)
        if (
            lower_bound is not None
            and lower_bound.astimezone(timezone.utc)
            > start.astimezone(timezone.utc)
        ):
            start = lower_bound
        if (
            upper_bound is not None
            and upper_bound.astimezone(timezone.utc)
            < end.astimezone(timezone.utc)
        ):
            end = upper_bound
        available_duration = (
            end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
        )
        duration = max(
            timedelta(0),
            min(available_duration, duration_cap)
            if duration_cap is not None
            else available_duration,
        )
        best_rejected_duration = max(best_rejected_duration, duration)
        if duration < MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW:
            continue
        candidate_productivity = productivity
        if duration < available_duration:
            if (
                availability is not None
                and availability.mode is SessionAvailabilityMode.DURATION
            ):
                for score, selected_start_hour in _scored_duration_window_starts(
                    assessment,
                    analysis_hours,
                    _elapsed_hours(analysis_start, start),
                    _elapsed_hours(analysis_start, end),
                    duration.total_seconds() / 3600,
                ):
                    selected_start = _at_elapsed_hour(
                        analysis_start,
                        selected_start_hour,
                    )
                    selected_end = (
                        selected_start.astimezone(timezone.utc) + duration
                    ).astimezone(selected_start.tzinfo)
                    candidates.append(
                        (duration, score, selected_start, selected_end)
                    )
                continue
            end = (
                start.astimezone(timezone.utc) + duration
            ).astimezone(start.tzinfo)
        candidates.append((duration, candidate_productivity, start, end))

    if not candidates:
        breakdown = assessment.productivity_breakdown
        has_productive_slice = (
            breakdown.productive_slice_count > 0
            if breakdown is not None
            else bool(productive_windows)
        )
        refusal_stage = (
            ProductivityRefusalStage.CONTINUOUS_WINDOW_TOO_SHORT
            if has_productive_slice
            else ProductivityRefusalStage.NO_PRODUCTIVE_SLICE
        )
        return _refusal(
            status=ActionabilityRefusalStatus.CONSTRAINTS_REFUSAL,
            cause_code=(
                AcquisitionIntentEligibilityReason
                .INSUFFICIENT_ACTIONABLE_PRODUCTIVE_WINDOW.value
            ),
            best_minutes=best_rejected_duration.total_seconds() / 60,
            refusal_stage=refusal_stage,
            productivity_breakdown=breakdown,
        )
    if (
        availability is not None
        and availability.mode is SessionAvailabilityMode.DURATION
    ):
        best_duration = max(candidate[0] for candidate in candidates)
        best_productivity = max(
            candidate[1]
            for candidate in candidates
            if candidate[0] == best_duration
        )
        best_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate[0] == best_duration
            and candidate[1] == best_productivity
        )
        if len(best_candidates) != 1:
            raise ValueError("ambiguous_best_duration_window")
        _, _, selected_start, selected_end = best_candidates[0]
        return ActionableProductiveWindowSelection(
            window=SessionAvailabilityWindow(selected_start, selected_end),
            refusal=None,
        )
    _, _, selected_start, selected_end = max(
        candidates,
        key=lambda candidate: (
            candidate[0],
            candidate[1],
            -candidate[2].timestamp(),
        ),
    )
    return ActionableProductiveWindowSelection(
        window=SessionAvailabilityWindow(selected_start, selected_end),
        refusal=None,
    )


def _productivity_between(slices, start_hour: float, end_hour: float) -> float:
    return sum(
        max(
            0.0,
            min(end_hour, slice_.end_hour) - max(start_hour, slice_.start_hour),
        ) * slice_.productivity_score
        for slice_ in slices
    )


def _validated_timeline(assessment, total_hours: float):
    timeline = getattr(assessment.productivity, "timeline", None)
    if not timeline:
        raise ValueError("duration_window_temporal_evidence_required")

    cursor = 0.0
    for slice_ in timeline:
        values = (
            getattr(slice_, "start_hour", None),
            getattr(slice_, "end_hour", None),
            getattr(slice_, "productivity_score", None),
        )
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            for value in values
        ):
            raise ValueError("duration_window_temporal_evidence_required")
        start_hour, end_hour, productivity_score = values
        if (
            start_hour != cursor
            or end_hour <= start_hour
            or end_hour > total_hours
            or not 0.0 <= productivity_score <= 1.0
        ):
            raise ValueError("duration_window_temporal_evidence_required")
        cursor = end_hour

    if cursor != total_hours:
        raise ValueError("duration_window_temporal_evidence_required")
    return tuple(timeline)


def _scored_duration_window_starts(
    assessment: ProductiveWindowAssessment,
    total_hours: float,
    window_start_hour: float,
    window_end_hour: float,
    capacity_hours: float,
) -> tuple[tuple[float, float], ...]:
    timeline = _validated_timeline(assessment, total_hours)
    latest_start = window_end_hour - capacity_hours
    boundaries = {
        boundary
        for slice_ in timeline
        for boundary in (slice_.start_hour, slice_.end_hour)
    }
    candidate_starts = {window_start_hour, latest_start}
    for boundary in boundaries:
        if window_start_hour <= boundary <= latest_start:
            candidate_starts.add(boundary)
        shifted = boundary - capacity_hours
        if window_start_hour <= shifted <= latest_start:
            candidate_starts.add(shifted)

    return tuple(
        (
            _productivity_between(
                timeline,
                start_hour,
                start_hour + capacity_hours,
            ) / capacity_hours,
            start_hour,
        )
        for start_hour in sorted(candidate_starts)
    )


def _best_duration_window_start(
    assessment: ProductiveWindowAssessment,
    total_hours: float,
    window_start_hour: float,
    window_end_hour: float,
    capacity_hours: float,
) -> tuple[float, float]:
    scored_starts = _scored_duration_window_starts(
        assessment,
        total_hours,
        window_start_hour,
        window_end_hour,
        capacity_hours,
    )
    best_productivity = max(score for score, _ in scored_starts)
    best_starts = tuple(
        start_hour
        for score, start_hour in scored_starts
        if score == best_productivity
    )
    if len(best_starts) != 1:
        raise ValueError("ambiguous_best_duration_window")
    return best_starts[0], best_productivity


def select_duration_availability_window(
    assessment: ProductiveWindowAssessment,
    availability: SessionAvailability,
) -> SessionAvailabilityWindow | None:
    if not isinstance(assessment, ProductiveWindowAssessment):
        raise TypeError("Expected ProductiveWindowAssessment")
    if not isinstance(availability, SessionAvailability):
        raise TypeError("Expected SessionAvailability")
    if availability.mode not in {
        SessionAvailabilityMode.ALL_NIGHT,
        SessionAvailabilityMode.DURATION,
        SessionAvailabilityMode.FIXED_WINDOW,
        SessionAvailabilityMode.START_AND_DURATION,
        SessionAvailabilityMode.UNTIL,
    }:
        raise ValueError("session_availability_mode_inactive")

    window_start = assessment.window_start
    window_end = assessment.window_end
    if (
        availability.mode is SessionAvailabilityMode.ALL_NIGHT
        and (window_start is None or window_end is None)
    ):
        return None
    if (
        not isinstance(window_start, datetime)
        or not isinstance(window_end, datetime)
        or window_start.tzinfo is None
        or window_end.tzinfo is None
        or window_start.utcoffset() is None
        or window_end.utcoffset() is None
        or window_end.astimezone(timezone.utc)
        <= window_start.astimezone(timezone.utc)
    ):
        raise ValueError("productive_window_bounds_required")

    if availability.mode is SessionAvailabilityMode.ALL_NIGHT:
        return SessionAvailabilityWindow(
            window_start=window_start,
            window_end=window_end,
        )

    if availability.mode is SessionAvailabilityMode.FIXED_WINDOW:
        availability_start = availability.start
        availability_end = availability.end
        availability_start_utc = availability_start.astimezone(timezone.utc)
        availability_end_utc = availability_end.astimezone(timezone.utc)
        window_start_utc = window_start.astimezone(timezone.utc)
        window_end_utc = window_end.astimezone(timezone.utc)
        overlap_start_utc = max(window_start_utc, availability_start_utc)
        overlap_end_utc = min(window_end_utc, availability_end_utc)
        if overlap_end_utc <= overlap_start_utc:
            return None
        return SessionAvailabilityWindow(
            window_start=(
                window_start
                if overlap_start_utc == window_start_utc
                else availability_start
            ),
            window_end=(
                window_end
                if overlap_end_utc == window_end_utc
                else availability_end
            ),
        )

    if availability.mode is SessionAvailabilityMode.UNTIL:
        until = availability.end
        until_utc = until.astimezone(timezone.utc)
        window_start_utc = window_start.astimezone(timezone.utc)
        window_end_utc = window_end.astimezone(timezone.utc)
        if until_utc <= window_start_utc:
            return None
        return SessionAvailabilityWindow(
            window_start=window_start,
            window_end=(window_end if until_utc >= window_end_utc else until),
        )

    if availability.mode is SessionAvailabilityMode.START_AND_DURATION:
        availability_start = availability.start
        availability_start_utc = availability_start.astimezone(timezone.utc)
        availability_end_utc = availability_start_utc + availability.duration
        window_start_utc = window_start.astimezone(timezone.utc)
        window_end_utc = window_end.astimezone(timezone.utc)
        overlap_start_utc = max(window_start_utc, availability_start_utc)
        overlap_end_utc = min(window_end_utc, availability_end_utc)
        if overlap_end_utc <= overlap_start_utc:
            return None
        overlap_start = (
            window_start
            if overlap_start_utc == window_start_utc
            else availability_start
        )
        overlap_end = (
            window_end
            if overlap_end_utc == window_end_utc
            else availability_end_utc.astimezone(availability_start.tzinfo)
        )
        return SessionAvailabilityWindow(
            window_start=overlap_start,
            window_end=overlap_end,
        )

    capacity = availability.duration
    total_hours = _elapsed_hours(window_start, window_end)
    capacity_hours = capacity.total_seconds() / 3600
    if total_hours <= capacity_hours:
        return SessionAvailabilityWindow(
            window_start=window_start,
            window_end=window_end,
        )

    best_start, _ = _best_duration_window_start(
        assessment,
        total_hours,
        0.0,
        total_hours,
        capacity_hours,
    )

    start_utc = window_start.astimezone(timezone.utc)
    selected_start = (
        start_utc + timedelta(hours=best_start)
    ).astimezone(window_start.tzinfo)
    selected_end = (
        start_utc + timedelta(hours=best_start + capacity_hours)
    ).astimezone(window_start.tzinfo)
    return SessionAvailabilityWindow(
        window_start=selected_start,
        window_end=selected_end,
    )
