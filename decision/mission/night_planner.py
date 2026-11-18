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

    preparation = timedelta(minutes=availability.preparation_minutes)
    flats = timedelta(minutes=availability.flats_minutes)
    mode = availability.mode
    if mode is SessionAvailabilityMode.UNTIL:
        return SessionAvailability(mode, end=shift(availability.end, -flats))
    if mode is SessionAvailabilityMode.DURATION:
        duration = availability.duration - preparation - flats
        if duration <= timedelta(0):
            raise ValueError("session_too_short_for_operational_tasks")
        return SessionAvailability(mode, duration=duration)
    end = availability.end if mode is SessionAvailabilityMode.FIXED_WINDOW else shift(availability.start, availability.duration)
    start, end = shift(availability.start, preparation), shift(end, -flats)
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
    def build(night_productivity, *, preparation_minutes=30, flats_minutes=10):
        tasks = [
            NightTask("T-30 min", "T-20 min", "Installer le matériel"),
            NightTask("T-20 min", "T-10 min", "Mise en station"),
            NightTask("T-10 min", "T", "Autofocus"),
        ]

        if preparation_minutes != 30:
            tasks = [NightTask(
                f"T-{preparation_minutes} min" if preparation_minutes else "T", "T",
                "Préparer le matériel et régler la mise au point" if preparation_minutes else "Matériel déjà prêt",
            )]
        tasks.append(NightTask(
            "Fin", f"Fin +{flats_minutes} min" if flats_minutes else "Fin",
            "Flats" if flats_minutes else "Flats non prévus dans ce plan",
        ))
        return tasks
