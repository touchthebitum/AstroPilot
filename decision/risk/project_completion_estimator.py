import math


class ProjectCompletionEstimator:
    @staticmethod
    def required_nights(remaining_hours: float | None,
                       productive_hours_per_night: float | None = None) -> int | None:
        """Explicit capacity scenario; this calculation supplies no historical evidence."""
        if (remaining_hours is None or productive_hours_per_night is None
                or not math.isfinite(remaining_hours)
                or not math.isfinite(productive_hours_per_night)
                or remaining_hours < 0 or productive_hours_per_night <= 0):
            return None
        return math.ceil(remaining_hours / productive_hours_per_night)
