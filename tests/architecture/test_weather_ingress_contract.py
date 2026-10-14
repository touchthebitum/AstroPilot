from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from decision.weather.weather_ingress import (
    FUTURE_RETRIEVAL_TOLERANCE,
    MAXIMUM_SNAPSHOT_AGE,
    REQUIRED_HOURLY_UNITS,
    WeatherIngressError,
    WeatherInsufficientError,
    WeatherStaleError,
    validate_weather_payload,
    validate_weather_freshness,
)


def valid_payload(hours=48):
    start = datetime(2026, 8, 29, tzinfo=ZoneInfo("Europe/Zurich"))
    return {
        "latitude": 46.75,
        "longitude": 6.55,
        "elevation": 837.0,
        "timezone": "Europe/Zurich",
        "utc_offset_seconds": 7200,
        "hourly_units": {"time": "unixtime", **REQUIRED_HOURLY_UNITS},
        "hourly": {
            "time": [
                int((start + timedelta(hours=index)).timestamp())
                for index in range(hours)
            ],
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


def validate(payload):
    return validate_weather_payload(
        payload,
        requested_latitude=46.7508,
        requested_longitude=6.5495,
        requested_timezone="Europe/Zurich",
        retrieved_at_utc=datetime(2026, 8, 29, 18, 5, tzinfo=timezone.utc),
    )


def test_valid_payload_becomes_an_immutable_snapshot_with_auditable_metadata():
    snapshot = validate(valid_payload())

    assert snapshot.provider == "Open-Meteo"
    assert snapshot.hour_count == 48
    assert snapshot.completeness == 1.0
    assert snapshot.timezone_source == "coordinates_local"
    assert snapshot.valid_from.isoformat() == "2026-08-29T00:00:00+02:00"
    assert snapshot.valid_until.isoformat() == "2026-08-30T23:00:00+02:00"
    assert snapshot.trust_transport()["validation_status"] == "validated"


@pytest.mark.parametrize(
    ("mutate", "issue"),
    [
        (lambda data: data.update(error=True), "provider_error_response"),
        (lambda data: data.pop("hourly_units"), "missing_hourly_units"),
        (
            lambda data: data["hourly_units"].update(time="iso8601"),
            "invalid_unit_time",
        ),
        (
            lambda data: data["hourly_units"].update(wind_speed_10m="m/s"),
            "invalid_unit_wind_speed_10m",
        ),
        (
            lambda data: data["hourly"]["cloud_cover"].pop(),
            "misaligned_series_cloud_cover",
        ),
        (
            lambda data: data["hourly"]["relative_humidity_2m"].__setitem__(0, 120),
            "out_of_range_relative_humidity_2m",
        ),
        (
            lambda data: data["hourly"]["temperature_2m"].__setitem__(0, float("nan")),
            "invalid_value_temperature_2m",
        ),
        (
            lambda data: data["hourly"]["time"].__setitem__(1, data["hourly"]["time"][0] + 1800),
            "non_hourly_time_cadence",
        ),
        (lambda data: data.update(timezone="UTC"), "unexpected_timezone"),
        (lambda data: data.update(latitude=10.0), "weather_grid_too_far"),
    ],
)
def test_corrupt_provider_payloads_are_rejected(mutate, issue):
    payload = deepcopy(valid_payload())
    mutate(payload)

    with pytest.raises(WeatherIngressError) as caught:
        validate(payload)

    assert issue in caught.value.issues


def test_less_than_one_day_of_weather_is_distinctly_insufficient():
    with pytest.raises(WeatherInsufficientError) as caught:
        validate(valid_payload(hours=23))

    assert caught.value.code == "weather_insufficient"


def test_corruption_takes_precedence_over_short_coverage():
    payload = valid_payload(hours=23)
    payload["hourly_units"]["temperature_2m"] = "°F"

    with pytest.raises(WeatherIngressError) as caught:
        validate(payload)

    assert not isinstance(caught.value, WeatherInsufficientError)
    assert "invalid_unit_temperature_2m" in caught.value.issues


def test_retrieval_timestamp_must_be_timezone_aware():
    with pytest.raises(WeatherIngressError) as caught:
        validate_weather_payload(
            valid_payload(),
            requested_latitude=46.7508,
            requested_longitude=6.5495,
            requested_timezone="Europe/Zurich",
            retrieved_at_utc=datetime(2026, 8, 29, 18, 5),
        )

    assert caught.value.issues == ("retrieval_time_without_timezone",)


@pytest.mark.parametrize(
    ("age", "expected_minutes"),
    [
        (timedelta(minutes=12, seconds=30), 12.5),
        (MAXIMUM_SNAPSHOT_AGE, 90.0),
    ],
)
def test_fresh_snapshot_and_exact_age_limit_are_accepted(age, expected_minutes):
    snapshot = validate(valid_payload())

    freshness = validate_weather_freshness(
        snapshot,
        reference_time_utc=snapshot.retrieved_at_utc + age,
    )

    assert freshness.snapshot_age_minutes == expected_minutes
    assert freshness.freshness_status == "fresh"
    assert freshness.maximum_age_minutes == 90


def test_snapshot_beyond_age_limit_is_distinctly_stale():
    snapshot = validate(valid_payload())

    with pytest.raises(WeatherStaleError) as caught:
        validate_weather_freshness(
            snapshot,
            reference_time_utc=(
                snapshot.retrieved_at_utc
                + MAXIMUM_SNAPSHOT_AGE
                + timedelta(microseconds=1)
            ),
        )

    assert caught.value.code == "weather_stale"
    assert caught.value.issues == ("retrieval_time_too_old",)


def test_future_timestamp_at_tolerance_is_accepted_with_zero_display_age():
    snapshot = validate(valid_payload())

    freshness = validate_weather_freshness(
        snapshot,
        reference_time_utc=(
            snapshot.retrieved_at_utc - FUTURE_RETRIEVAL_TOLERANCE
        ),
    )

    assert freshness.snapshot_age_minutes == 0.0


def test_excessively_future_timestamp_is_invalid():
    snapshot = validate(valid_payload())

    with pytest.raises(WeatherIngressError) as caught:
        validate_weather_freshness(
            snapshot,
            reference_time_utc=(
                snapshot.retrieved_at_utc
                - FUTURE_RETRIEVAL_TOLERANCE
                - timedelta(microseconds=1)
            ),
        )

    assert not isinstance(caught.value, WeatherStaleError)
    assert caught.value.code == "weather_invalid"
    assert caught.value.issues == ("retrieval_time_in_future",)


def test_injected_reference_time_makes_freshness_deterministic():
    snapshot = validate(valid_payload())
    reference = snapshot.retrieved_at_utc + timedelta(minutes=37)

    first = validate_weather_freshness(snapshot, reference_time_utc=reference)
    second = validate_weather_freshness(snapshot, reference_time_utc=reference)

    assert first == second


def test_unix_weather_hours_cross_spring_dst_as_distinct_utc_instants():
    payload = valid_payload()
    start_utc = datetime(2026, 3, 29, tzinfo=timezone.utc)
    payload["hourly"]["time"] = [
        int((start_utc + timedelta(hours=index)).timestamp())
        for index in range(48)
    ]

    snapshot = validate(payload)

    assert snapshot.valid_from.isoformat() == "2026-03-29T01:00:00+01:00"
    assert snapshot.payload["hourly"]["time"][1] - snapshot.payload["hourly"]["time"][0] == 3600
    second = datetime.fromtimestamp(
        snapshot.payload["hourly"]["time"][1], timezone.utc
    ).astimezone(ZoneInfo(snapshot.timezone))
    assert second.isoformat() == "2026-03-29T03:00:00+02:00"


@pytest.mark.parametrize("failure,category,status", [
    ('ReadTimeout','read_timeout',None), ('ConnectTimeout','connect_timeout',None),
    ('SSLError','tls_error',None), ('ConnectionError','connection_error',None),
    ('Timeout','timeout',None), ('HTTPError','http_error',429), ('HTTPError','http_error',503),
    ('RequestException','request_error',None), ('RuntimeError','unexpected_error',None),
])
def test_fetch_weather_records_sanitized_failure_without_retry(monkeypatch, caplog, failure, category, status):
    import json
    import requests
    import astro_score
    from astropilot.weather_diagnostics import weather_diagnostic_context
    secret = 'token=SECRET https://private.invalid/path?latitude=46.7508'
    error_type = RuntimeError if failure=='RuntimeError' else getattr(requests.exceptions, failure)
    error = error_type(secret)
    if status is not None:
        error.response = requests.Response()
        error.response.status_code = status
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise error
    monkeypatch.setattr(astro_score.requests, 'get', fail)
    with weather_diagnostic_context('request-test-id'):
        assert astro_score.fetch_weather(46.7508,6.5495) is None
    records = [json.loads(r.message.removeprefix('weather_diagnostic '))
               for r in caplog.records if r.message.startswith('weather_diagnostic ')]
    assert len(records)==1
    record=records[0]
    assert record['diagnostic_id']=='request-test-id'
    assert record['event']=='weather_fetch_failed'
    assert record['category']==category
    assert record['http_status']==status
    assert record['duration_ms']>=0
    assert datetime.fromisoformat(record['occurred_at_utc']).utcoffset()==timedelta(0)
    assert 'SECRET' not in caplog.text and 'private.invalid' not in caplog.text
    assert '46.7508' not in caplog.text
    assert len(calls)==1 and calls[0]['timeout']==15


@pytest.mark.parametrize('payload,category', [(None,'response_not_json'), ({},'invalid_weather_payload')])
def test_fetch_weather_preserves_invalid_payload_refusal(monkeypatch, caplog, payload, category):
    import json
    import requests
    import astro_score
    response=requests.Response()
    response.status_code=200
    response._content=b'not JSON SECRET' if payload is None else json.dumps(payload).encode()
    monkeypatch.setattr(astro_score.requests,'get',lambda *a,**k:response)
    with pytest.raises(WeatherIngressError):
        astro_score.fetch_weather(46.7508,6.5495)
    record=json.loads(caplog.records[-1].message.removeprefix('weather_diagnostic '))
    assert record['category']==category
    assert 'SECRET' not in caplog.text


def test_fetch_weather_after_failure_still_validates_the_real_payload(monkeypatch, caplog):
    import json
    import requests
    import astro_score
    response=requests.Response()
    response.status_code=200
    response._content=json.dumps(valid_payload()).encode()
    def fail(*a,**k): raise requests.exceptions.ReadTimeout('SECRET')
    monkeypatch.setattr(astro_score.requests,'get',fail)
    assert astro_score.fetch_weather(46.7508,6.5495) is None
    monkeypatch.setattr(astro_score.requests,'get',lambda *a,**k:response)
    snapshot=astro_score.fetch_weather(46.7508,6.5495)
    assert snapshot.hour_count==48 and snapshot.completeness==1
    records=[json.loads(r.message.removeprefix('weather_diagnostic ')) for r in caplog.records]
    assert records[-1]['event']=='weather_fetch_succeeded'
    assert records[-1]['category']=='validated'
    assert records[-1]['diagnostic_id']!=records[-2]['diagnostic_id']


def test_diagnostic_context_is_nested_thread_isolated_and_resets(caplog):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import perf_counter
    from astropilot.weather_diagnostics import log_weather, weather_diagnostic_context
    barrier=Barrier(2)
    def worker(identifier):
        with weather_diagnostic_context(identifier):
            barrier.wait(timeout=5)
            log_weather('outer',category='available',started=perf_counter())
            with weather_diagnostic_context(identifier+'-nested'):
                log_weather('nested',category='available',started=perf_counter())
            log_weather('restored',category='available',started=perf_counter())
        log_weather('outside',category='available',started=perf_counter())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[pool.submit(worker, identifier) for identifier in ('one','two')]
        for result in results: result.result(timeout=10)
    records=[json.loads(r.message.removeprefix('weather_diagnostic ')) for r in caplog.records]
    assert sorted(r['diagnostic_id'] for r in records if r['event']=='outer')==['one','two']
    assert sorted(r['diagnostic_id'] for r in records if r['event']=='restored')==['one','two']
    assert sorted(r['diagnostic_id'] for r in records if r['event']=='nested')==['one-nested','two-nested']
    assert all(r['diagnostic_id'] not in ('one','two') for r in records if r['event']=='outside')
