import math


class ProjectCompletionEstimator:

    @staticmethod
    def required_nights(
        remaining_hours: float,
        productive_hours_per_night: float = 4.0,
    ) -> int:
        return math.ceil(
            remaining_hours / productive_hours_per_night
        )
