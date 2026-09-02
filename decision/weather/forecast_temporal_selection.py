from datetime import timedelta

from decision.weather.forecast_temporal_candidates import (
    ForecastTemporalCandidate,
)


class ForecastTemporalSelectionError(ValueError):
    pass


def select_forecast_temporal_candidate(
    candidates: tuple[ForecastTemporalCandidate, ...],
    *,
    maximum_absolute_offset: timedelta,
) -> ForecastTemporalCandidate | None:
    if (
        not isinstance(maximum_absolute_offset, timedelta)
        or maximum_absolute_offset < timedelta(0)
    ):
        raise ValueError("invalid_maximum_absolute_offset")

    admissible = tuple(
        candidate
        for candidate in candidates
        if abs(candidate.temporal_offset) <= maximum_absolute_offset
    )
    if not admissible:
        return None

    minimum_offset = min(abs(candidate.temporal_offset) for candidate in admissible)
    nearest = tuple(
        candidate
        for candidate in admissible
        if abs(candidate.temporal_offset) == minimum_offset
    )
    if len(nearest) != 1:
        raise ForecastTemporalSelectionError("ambiguous_nearest_forecast")
    return nearest[0]
