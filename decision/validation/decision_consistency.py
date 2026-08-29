from __future__ import annotations

from datetime import datetime
from math import isfinite


class DecisionConsistencyError(ValueError):
    code = "decision_invalid"

    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = tuple(issues)


class DecisionConsistencyGate:
    TOLERANCE = 0.011

    @staticmethod
    def _is_finite(value):
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(float(value))
        )

    @staticmethod
    def _finite(value, name, issues, *, minimum=None, maximum=None):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
        ):
            issues.append(f"invalid_{name}")
            return
        if minimum is not None and value < minimum:
            issues.append(f"{name}_below_minimum")
        if maximum is not None and value > maximum:
            issues.append(f"{name}_above_maximum")

    @classmethod
    def validate_mission(cls, mission) -> None:
        issues = []
        start = mission.window_start
        end = mission.window_end
        if not isinstance(start, datetime) or start.tzinfo is None:
            issues.append("invalid_window_start")
        if not isinstance(end, datetime) or end.tzinfo is None:
            issues.append("invalid_window_end")
        if (
            isinstance(start, datetime)
            and start.tzinfo is not None
            and isinstance(end, datetime)
            and end.tzinfo is not None
            and end <= start
        ):
            issues.append("window_not_forward")

        window_hours = None
        if (
            isinstance(start, datetime)
            and start.tzinfo is not None
            and isinstance(end, datetime)
            and end.tzinfo is not None
            and end > start
        ):
            window_hours = (end - start).total_seconds() / 3600

        cls._finite(mission.recommended_hours, "recommended_hours", issues, minimum=0)
        cls._finite(mission.expected_gain, "expected_gain", issues, minimum=0)

        productivity = mission.productivity
        if productivity is None:
            issues.append("missing_productivity")
        else:
            cls._finite(productivity.astronomical_hours, "astronomical_hours", issues, minimum=0)
            cls._finite(productivity.productive_hours, "productive_hours", issues, minimum=0)
            cls._finite(productivity.confidence, "productive_fraction", issues, minimum=0, maximum=1)
            if (
                window_hours is not None
                and cls._is_finite(productivity.astronomical_hours)
                and abs(productivity.astronomical_hours - window_hours)
                > cls.TOLERANCE
            ):
                issues.append("astronomical_hours_mismatch_window")
            if (
                cls._is_finite(productivity.productive_hours)
                and cls._is_finite(productivity.astronomical_hours)
                and productivity.productive_hours
                > productivity.astronomical_hours + cls.TOLERANCE
            ):
                issues.append("productive_hours_exceed_astronomical_hours")
            if (
                cls._is_finite(mission.recommended_hours)
                and cls._is_finite(productivity.productive_hours)
                and mission.recommended_hours
                > productivity.productive_hours + cls.TOLERANCE
            ):
                issues.append("recommended_hours_exceed_productive_hours")
            if (
                cls._is_finite(productivity.productive_hours)
                and cls._is_finite(productivity.astronomical_hours)
                and productivity.astronomical_hours > 0
                and cls._is_finite(productivity.confidence)
                and abs(
                    productivity.confidence
                    - productivity.productive_hours
                    / productivity.astronomical_hours
                ) > 0.015
            ):
                issues.append("productive_fraction_mismatch")
            previous_end = 0.0
            for index, window in enumerate(productivity.windows):
                prefix = f"window_{index}"
                cls._finite(window.start_hour, f"{prefix}_start", issues, minimum=0)
                cls._finite(window.end_hour, f"{prefix}_end", issues, minimum=0)
                cls._finite(window.productivity, f"{prefix}_productivity", issues, minimum=0, maximum=1)
                if (
                    cls._is_finite(window.start_hour)
                    and cls._is_finite(window.end_hour)
                    and window.end_hour <= window.start_hour
                ):
                    issues.append(f"{prefix}_not_forward")
                if (
                    cls._is_finite(window.end_hour)
                    and cls._is_finite(productivity.astronomical_hours)
                    and window.end_hour
                    > productivity.astronomical_hours + cls.TOLERANCE
                ):
                    issues.append(f"{prefix}_outside_night")
                if not window.productive:
                    issues.append(f"{prefix}_not_productive")
                if cls._is_finite(window.productivity) and window.productivity < 0.7:
                    issues.append(f"{prefix}_below_productive_threshold")
                if (
                    cls._is_finite(window.start_hour)
                    and window.start_hour < previous_end - cls.TOLERANCE
                ):
                    issues.append(f"{prefix}_overlaps_previous")
                if cls._is_finite(window.end_hour):
                    previous_end = window.end_hour
            if (
                not productivity.windows
                and cls._is_finite(mission.recommended_hours)
                and mission.recommended_hours > cls.TOLERANCE
            ):
                issues.append("recommended_hours_without_productive_window")
            if (
                not productivity.windows
                and cls._is_finite(mission.expected_gain)
                and mission.expected_gain > cls.TOLERANCE
            ):
                issues.append("expected_gain_without_productive_window")

        if issues:
            raise DecisionConsistencyError(issues)

    @staticmethod
    def has_productive_window(mission) -> bool:
        productivity = getattr(mission, "productivity", None)
        return bool(productivity and productivity.windows)
