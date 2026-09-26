from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def timeline_value(value: datetime) -> datetime:
    """Return the value used to order instants on an elapsed-time timeline."""
    return value.astimezone(timezone.utc) if _is_aware(value) else value


def elapsed_time(start: datetime, end: datetime) -> timedelta:
    return timeline_value(end) - timeline_value(start)


def elapsed_hours(start: datetime, end: datetime) -> float:
    return elapsed_time(start, end).total_seconds() / 3600


def add_elapsed_time(value: datetime, delta: timedelta) -> datetime:
    if not _is_aware(value):
        return value + delta
    return (value.astimezone(timezone.utc) + delta).astimezone(value.tzinfo)
