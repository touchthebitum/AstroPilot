from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite

from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)


@dataclass(frozen=True, slots=True)
class SessionAvailabilityWindow:
    window_start: datetime
    window_end: datetime


def _elapsed_hours(start: datetime, end: datetime) -> float:
    return (
        end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    ).total_seconds() / 3600


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


def select_duration_availability_window(
    assessment: ProductiveWindowAssessment,
    availability: SessionAvailability,
) -> SessionAvailabilityWindow | None:
    if not isinstance(assessment, ProductiveWindowAssessment):
        raise TypeError("Expected ProductiveWindowAssessment")
    if not isinstance(availability, SessionAvailability):
        raise TypeError("Expected SessionAvailability")
    if availability.mode not in {
        SessionAvailabilityMode.DURATION,
        SessionAvailabilityMode.START_AND_DURATION,
    }:
        raise ValueError("session_availability_mode_inactive")

    window_start = assessment.window_start
    window_end = assessment.window_end
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

    timeline = _validated_timeline(assessment, total_hours)
    latest_start = total_hours - capacity_hours
    boundaries = {
        boundary
        for slice_ in timeline
        for boundary in (slice_.start_hour, slice_.end_hour)
    }
    candidate_starts = {0.0, latest_start}
    for boundary in boundaries:
        if 0.0 <= boundary <= latest_start:
            candidate_starts.add(boundary)
        shifted = boundary - capacity_hours
        if 0.0 <= shifted <= latest_start:
            candidate_starts.add(shifted)

    scored_starts = tuple(
        (
            _productivity_between(
                timeline,
                start_hour,
                start_hour + capacity_hours,
            ),
            start_hour,
        )
        for start_hour in sorted(candidate_starts)
    )
    best_productivity = max(score for score, _ in scored_starts)
    best_starts = tuple(
        start_hour
        for score, start_hour in scored_starts
        if score == best_productivity
    )
    if len(best_starts) != 1:
        raise ValueError("ambiguous_best_duration_window")

    start_utc = window_start.astimezone(timezone.utc)
    selected_start = (
        start_utc + timedelta(hours=best_starts[0])
    ).astimezone(window_start.tzinfo)
    selected_end = (
        start_utc + timedelta(hours=best_starts[0] + capacity_hours)
    ).astimezone(window_start.tzinfo)
    return SessionAvailabilityWindow(
        window_start=selected_start,
        window_end=selected_end,
    )
