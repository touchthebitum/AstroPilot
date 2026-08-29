from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from decision.location.location_time import LocationTimeResolver
from decision.validation.weather_window_coverage import (
    validate_selected_window_weather_coverage,
)
from decision.weather.weather_ingress import (
    REQUIRED_HOURLY_UNITS,
    WeatherIngressError,
    validate_weather_payload,
)


LATITUDE = 46.7508
LONGITUDE = 6.5495


def payload(*, timezone_name, start_utc, hours=48):
    timestamps = [
        int((start_utc + timedelta(hours=index)).timestamp())
        for index in range(hours)
    ]
    return {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "elevation": 837.0,
        "timezone": timezone_name,
        "utc_offset_seconds": int(
            start_utc.astimezone(ZoneInfo(timezone_name))
            .utcoffset()
            .total_seconds()
        ),
        "hourly_units": {"time": "unixtime", **REQUIRED_HOURLY_UNITS},
        "hourly": {
            "time": timestamps,
            "cloud_cover": [20.0] * hours,
            "cloud_cover_low": [10.0] * hours,
            "cloud_cover_mid": [5.0] * hours,
            "cloud_cover_high": [5.0] * hours,
            "precipitation": [0.0] * hours,
            "relative_humidity_2m": [65.0] * hours,
            "visibility": [24000.0] * hours,
            "wind_speed_10m": [8.0] * hours,
            "temperature_2m": [12.0] * hours,
        },
    }


def validate(data):
    return validate_weather_payload(
        data,
        requested_latitude=LATITUDE,
        requested_longitude=LONGITUDE,
        requested_timezone=data["timezone"],
        retrieved_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def mission(start, end):
    return SimpleNamespace(window_start=start, window_end=end)


def test_spring_dst_keeps_an_uninterrupted_utc_cadence():
    snapshot = validate(
        payload(
            timezone_name="Europe/Zurich",
            start_utc=datetime(2026, 3, 29, 0, tzinfo=timezone.utc),
        )
    )

    assert snapshot.valid_from.isoformat() == "2026-03-29T01:00:00+01:00"
    second = datetime.fromtimestamp(
        snapshot.payload["hourly"]["time"][1], timezone.utc
    ).astimezone(ZoneInfo(snapshot.timezone))
    assert second.isoformat() == "2026-03-29T03:00:00+02:00"


def test_fall_dst_accepts_both_repeated_local_hours_as_distinct_instants():
    snapshot = validate(
        payload(
            timezone_name="Europe/Zurich",
            start_utc=datetime(2026, 10, 25, 0, tzinfo=timezone.utc),
        )
    )
    zone = ZoneInfo(snapshot.timezone)
    first, second = [
        datetime.fromtimestamp(value, timezone.utc).astimezone(zone)
        for value in snapshot.payload["hourly"]["time"][:2]
    ]

    assert first.hour == second.hour == 2
    assert (first.fold, second.fold) == (0, 1)
    assert second.timestamp() - first.timestamp() == 3600


def test_window_between_repeated_fall_hours_is_covered_by_utc_instants():
    snapshot = validate(
        payload(
            timezone_name="Europe/Zurich",
            start_utc=datetime(2026, 10, 25, 0, tzinfo=timezone.utc),
        )
    )
    zone = ZoneInfo(snapshot.timezone)
    first = datetime.fromtimestamp(
        snapshot.payload["hourly"]["time"][0], timezone.utc
    ).astimezone(zone)
    second = datetime.fromtimestamp(
        snapshot.payload["hourly"]["time"][1], timezone.utc
    ).astimezone(zone)

    validate_selected_window_weather_coverage(
        mission(first, second),
        snapshot,
    )


@pytest.mark.parametrize(
    "timezone_name",
    ["UTC", "America/New_York", "Pacific/Kiritimati"],
)
def test_exact_snapshot_boundaries_hold_across_utc_and_extreme_offsets(
    timezone_name,
):
    snapshot = validate(
        payload(
            timezone_name=timezone_name,
            start_utc=datetime(2026, 8, 29, 0, tzinfo=timezone.utc),
        )
    )

    validate_selected_window_weather_coverage(
        mission(
            snapshot.valid_from.astimezone(timezone.utc),
            snapshot.valid_until.astimezone(timezone.utc),
        ),
        snapshot,
    )


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (1.8721, -157.4278, "Pacific/Kiritimati"),
        (-14.2756, -170.7020, "Pacific/Pago_Pago"),
    ],
)
def test_coordinates_on_both_sides_of_date_line_resolve_independently(
    latitude,
    longitude,
    expected,
):
    assert (
        LocationTimeResolver.resolve(latitude, longitude).timezone_name
        == expected
    )


def test_same_date_line_instants_are_covered_despite_opposite_local_dates():
    snapshot = validate(
        payload(
            timezone_name="Pacific/Kiritimati",
            start_utc=datetime(2026, 8, 29, 8, tzinfo=timezone.utc),
        )
    )
    pago_pago = ZoneInfo("Pacific/Pago_Pago")
    start = snapshot.valid_from.astimezone(pago_pago)
    end = snapshot.valid_until.astimezone(pago_pago)

    assert start.date() != snapshot.valid_from.date()
    validate_selected_window_weather_coverage(mission(start, end), snapshot)


def test_local_night_crossing_midnight_near_date_line_remains_covered():
    zone = ZoneInfo("Pacific/Kiritimati")
    snapshot = validate(
        payload(
            timezone_name=zone.key,
            start_utc=datetime(2026, 8, 29, 8, tzinfo=timezone.utc),
        )
    )
    start = datetime(2026, 8, 29, 23, tzinfo=zone)
    end = datetime(2026, 8, 30, 2, tzinfo=zone)

    assert start.date() != end.date()
    validate_selected_window_weather_coverage(mission(start, end), snapshot)


def test_duplicate_unix_instant_is_rejected_as_non_monotonic():
    data = payload(
        timezone_name="UTC",
        start_utc=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    data["hourly"]["time"][12] = data["hourly"]["time"][11]

    with pytest.raises(WeatherIngressError) as caught:
        validate(data)

    assert "non_monotonic_hourly_time" in caught.value.issues


@pytest.mark.parametrize(
    ("index", "tail_shift_seconds"),
    [
        (1, -1800),
        (12, 1800),
        (46, 3600),
    ],
)
def test_holes_and_irregular_cadence_are_rejected_at_any_position(
    index,
    tail_shift_seconds,
):
    data = payload(
        timezone_name="UTC",
        start_utc=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    corrupted = deepcopy(data)
    corrupted["hourly"]["time"][index:] = [
        value + tail_shift_seconds
        for value in corrupted["hourly"]["time"][index:]
    ]

    with pytest.raises(WeatherIngressError) as caught:
        validate(corrupted)

    assert "non_hourly_time_cadence" in caught.value.issues
