from dataclasses import dataclass
from enum import StrEnum
import math


class NightCapacitySource(StrEnum):
    HISTORY = "history"
    PROFILE = "profile"
    SCENARIO = "scenario"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NightCapacityEstimate:
    productive_hours_per_night: float | None
    source: NightCapacitySource
    historical_nights: int | None

    @property
    def scenario_eligible(self) -> bool:
        return (self.source in (NightCapacitySource.HISTORY, NightCapacitySource.PROFILE,
                                NightCapacitySource.SCENARIO)
                and self.productive_hours_per_night is not None
                and math.isfinite(self.productive_hours_per_night)
                and self.productive_hours_per_night > 0)

    @property
    def observed(self) -> bool:
        return (self.source == NightCapacitySource.HISTORY
                and self.historical_nights is not None
                and self.historical_nights >= 3
                and self.productive_hours_per_night is not None
                and math.isfinite(self.productive_hours_per_night)
                and self.productive_hours_per_night > 0)

    @property
    def estimated(self) -> bool:
        return not self.observed

    @property
    def confidence(self) -> str:
        return "medium" if self.observed else (
            "low" if self.scenario_eligible else "unknown")

    @property
    def decision_eligible(self) -> bool:
        # Eligibility for empirical risk pressure only, never mission availability.
        return self.observed


class HistoricalNightCapacityEstimator:
    MINIMUM_NIGHTS = 3

    @staticmethod
    def estimate(sessions: list[dict] | None, fallback: float | None = None,
                 *, fallback_source: NightCapacitySource = NightCapacitySource.PROFILE
                 ) -> NightCapacityEstimate:
        fallback_source = NightCapacitySource(fallback_source)
        if fallback_source not in (NightCapacitySource.PROFILE, NightCapacitySource.SCENARIO):
            raise ValueError("fallback must be an explicit profile or scenario")
        hours_by_night = {}
        for session in sessions or []:
            date = session.get("date")
            hours = float(session.get("hours", 0))
            if not date or not math.isfinite(hours) or hours <= 0:
                continue
            hours_by_night[date] = hours_by_night.get(date, 0.0) + hours
        count = len(hours_by_night) if sessions is not None else None
        if count is not None and count >= HistoricalNightCapacityEstimator.MINIMUM_NIGHTS:
            return NightCapacityEstimate(sum(hours_by_night.values()) / count,
                                         NightCapacitySource.HISTORY, count)
        if fallback is not None and math.isfinite(fallback) and fallback > 0:
            return NightCapacityEstimate(fallback, fallback_source, count)
        return NightCapacityEstimate(None, NightCapacitySource.UNKNOWN, count)
