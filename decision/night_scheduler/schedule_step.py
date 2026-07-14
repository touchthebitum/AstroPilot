from dataclasses import dataclass

@dataclass(frozen=True)
class ScheduleStep:
    start: str
    end: str

    title: str
    description: str = ""

    priority: int = 0

    productive: bool = False
    target: str | None = None
    filter_name: str | None = None