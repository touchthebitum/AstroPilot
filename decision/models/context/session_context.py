from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SessionContext:
    """
    Describes the observing session constraints.
    """

    start_time: datetime
    end_time: datetime
    available_duration: timedelta

    is_remote: bool = False

