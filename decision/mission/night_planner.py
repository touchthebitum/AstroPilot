from dataclasses import dataclass
from datetime import timedelta, timezone

from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode

PREPARATION_TIME = timedelta(minutes=30)
FLATS_TIME = timedelta(minutes=10)


def acquisition_availability(availability):
    """Reserve operational time inside explicit total session bounds.

    Use elapsed UTC arithmetic across clock changes. No physical threshold or
    original availability is changed. Call once at mission assembly.
    """
    if availability is None or availability.mode is SessionAvailabilityMode.ALL_NIGHT:
        return availability

    def shift(instant, delta):
        return (instant.astimezone(timezone.utc) + delta).astimezone(instant.tzinfo)

    mode = availability.mode
    if mode is SessionAvailabilityMode.UNTIL:
        return SessionAvailability(mode, end=shift(availability.end, -FLATS_TIME))
    if mode is SessionAvailabilityMode.DURATION:
        duration = availability.duration - PREPARATION_TIME - FLATS_TIME
        if duration <= timedelta(0):
            raise ValueError("session_too_short_for_operational_tasks")
        return SessionAvailability(mode, duration=duration)
    end = availability.end if mode is SessionAvailabilityMode.FIXED_WINDOW else shift(availability.start, availability.duration)
    start, end = shift(availability.start, PREPARATION_TIME), shift(end, -FLATS_TIME)
    if end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
        raise ValueError("session_too_short_for_operational_tasks")
    return SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW, start=start, end=end)


@dataclass(frozen=True)
class NightTask:
    start: str
    end: str

    title: str
    description: str = ""

    priority: int = 0

    productivity: float = 0.0


class NightPlanner:

    @staticmethod
    def build(night_productivity):
        tasks = [
            NightTask("T-30 min", "T-20 min", "Installer le matériel"),
            NightTask("T-20 min", "T-10 min", "Mise en station"),
            NightTask("T-10 min", "T", "Autofocus"),
        ]

        tasks.append(
            NightTask(
                "Fin",
                "Fin +10 min",
                "Flats",
            )
        )

        return tasks

