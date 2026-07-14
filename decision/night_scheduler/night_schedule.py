from dataclasses import dataclass
from .schedule_step import ScheduleStep


@dataclass(frozen=True)
class NightSchedule:
    steps: list[ScheduleStep]

    total_productive_hours: float
    efficiency: float