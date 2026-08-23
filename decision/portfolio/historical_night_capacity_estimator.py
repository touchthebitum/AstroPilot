class HistoricalNightCapacityEstimator:

    @staticmethod
    def estimate(
        sessions: list[dict],
        fallback: float,
    ) -> float:
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

        if not hours_by_night:
            return fallback

        return (
            sum(hours_by_night.values())
            / len(hours_by_night)
        )
