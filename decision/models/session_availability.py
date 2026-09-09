from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class SessionAvailabilityMode(str, Enum):
    ALL_NIGHT = "all_night"
    DURATION = "duration"
    START_AND_DURATION = "start_and_duration"
    UNTIL = "until"
    FIXED_WINDOW = "fixed_window"


@dataclass(frozen=True, slots=True)
class SessionAvailability:
    mode: SessionAvailabilityMode
    start: datetime | None = None
    end: datetime | None = None
    duration: timedelta | None = None

    def __post_init__(self):
        if not isinstance(self.mode, SessionAvailabilityMode):
            raise TypeError("Expected SessionAvailabilityMode")

        supplied_fields = {
            name
            for name, value in (
                ("start", self.start),
                ("end", self.end),
                ("duration", self.duration),
            )
            if value is not None
        }
        required_fields = {
            SessionAvailabilityMode.ALL_NIGHT: set(),
            SessionAvailabilityMode.DURATION: {"duration"},
            SessionAvailabilityMode.START_AND_DURATION: {"start", "duration"},
            SessionAvailabilityMode.UNTIL: {"end"},
            SessionAvailabilityMode.FIXED_WINDOW: {"start", "end"},
        }[self.mode]
        if supplied_fields != required_fields:
            raise ValueError("invalid_session_availability_fields")

        for value in (self.start, self.end):
            if value is None:
                continue
            if not isinstance(value, datetime):
                raise TypeError("Session availability times must be datetimes")
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("session_availability_timezone_required")

        if self.duration is not None:
            if not isinstance(self.duration, timedelta):
                raise TypeError("Session availability duration must be a timedelta")
            if self.duration <= timedelta(0):
                raise ValueError("session_availability_duration_must_be_positive")

        if (
            self.mode is SessionAvailabilityMode.FIXED_WINDOW
            and self.end <= self.start
        ):
            raise ValueError("session_availability_end_must_follow_start")
