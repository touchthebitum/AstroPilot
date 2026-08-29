from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from decision.location.location_time import LocationTimeError, LocationTimeResolver
from decision.engines.future_opportunity_engine import FutureOpportunityEngine
from decision.weather.weather_ingress import (
    REQUIRED_HOURLY_UNITS,
    validate_weather_payload,
)


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (46.7508, 6.5495, "Europe/Zurich"),
        (51.5074, -0.1278, "Europe/London"),
        (40.7128, -74.0060, "America/New_York"),
        (35.6762, 139.6503, "Asia/Tokyo"),
        (-33.8688, 151.2093, "Australia/Sydney"),
        (27.7172, 85.3240, "Asia/Kathmandu"),
    ],
)
def test_coordinates_resolve_to_an_independent_iana_timezone(
    latitude, longitude, expected
):
    resolved = LocationTimeResolver.resolve(latitude, longitude)

    assert resolved.timezone_name == expected
    assert resolved.zone.key == expected


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (0, 181), (float("nan"), 0), (True, 0)],
)
def test_invalid_coordinates_fail_closed(latitude, longitude):
    with pytest.raises(LocationTimeError):
        LocationTimeResolver.resolve(latitude, longitude)


def test_unresolved_valid_coordinates_fail_closed(monkeypatch):
    class NoTimezoneFinder:
        def timezone_at(self, **kwargs):
            return None

    monkeypatch.setattr(LocationTimeResolver, "_finder", NoTimezoneFinder())

    with pytest.raises(LocationTimeError, match="timezone_not_found"):
        LocationTimeResolver.resolve(0.0, 0.0)


def test_utc_instants_convert_across_spring_dst_without_ambiguity():
    zone = ZoneInfo("Europe/Zurich")
    before = datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc).astimezone(zone)
    after = datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc).astimezone(zone)

    assert before.isoformat() == "2026-03-29T01:00:00+01:00"
    assert after.isoformat() == "2026-03-29T03:00:00+02:00"
    assert after.timestamp() - before.timestamp() == 3600


def test_utc_instants_preserve_both_fall_dst_hours():
    zone = ZoneInfo("Europe/Zurich")
    first = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc).astimezone(zone)
    second = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc).astimezone(zone)

    assert first.hour == second.hour == 2
    assert first.fold == 0
    assert second.fold == 1
    assert first.timestamp() != second.timestamp()


def test_future_opportunity_reads_validated_unix_hours_in_snapshot_timezone():
    hours = 24
    start = datetime(2026, 8, 29, tzinfo=timezone.utc)
    payload = {
        "latitude": 46.75,
        "longitude": 6.55,
        "timezone": "Europe/Zurich",
        "utc_offset_seconds": 7200,
        "hourly_units": {"time": "unixtime", **REQUIRED_HOURLY_UNITS},
        "hourly": {
            "time": [int(start.timestamp()) + index * 3600 for index in range(hours)],
            **{
                name: [0.0 if name == "precipitation" else 20.0] * hours
                for name in REQUIRED_HOURLY_UNITS
            },
        },
    }
    snapshot = validate_weather_payload(
        payload,
        requested_latitude=46.7508,
        requested_longitude=6.5495,
        requested_timezone="Europe/Zurich",
    )

    ratio = FutureOpportunityEngine._estimate_weather_good_night_ratio(snapshot)

    assert 0.0 <= ratio <= 1.0
