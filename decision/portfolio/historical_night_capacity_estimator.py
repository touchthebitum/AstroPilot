from dataclasses import dataclass


@dataclass(frozen=True)
class NightCapacityEstimate:
    productive_hours_per_night: float
    source: str
    historical_nights: int


class HistoricalNightCapacityEstimator:

    MINIMUM_NIGHTS = 3

    @staticmethod
    def estimate(
        sessions: list[dict],
        fallback: float,
    ) -> NightCapacityEstimate:
        hours_by_night = {}

        for session in sessions:
            date = session.get("date")
            hours = float(session.get("hours", 0))

            if not date or hours <= 0:
                continue

            hours_by_night[date] = (
                hours_by_night.get(date, 0.0)
                + hours
            )

        historical_nights = len(hours_by_night)

        if (
            historical_nights
            < HistoricalNightCapacityEstimator.MINIMUM_NIGHTS
        ):
            return NightCapacityEstimate(
                productive_hours_per_night=fallback,
                source="profile",
                historical_nights=historical_nights,
            )

        return NightCapacityEstimate(
            productive_hours_per_night=(
                sum(hours_by_night.values())
                / historical_nights
            ),
            source="history",
            historical_nights=historical_nights,
        )
