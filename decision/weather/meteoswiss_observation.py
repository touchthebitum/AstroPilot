from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from decision.weather.provider_reliability import (
    CANONICAL_UNITS,
    ObservationQualityStatus,
    WeatherLocation,
    WeatherObservationPoint,
    WeatherValue,
    WeatherVariable,
)


@dataclass(frozen=True)
class MeteoSwissStationMetadata:
    station_id: str
    latitude: float
    longitude: float
    altitude_m: float | None


@dataclass(frozen=True)
class MeteoSwissObservationRecord:
    observed_at_utc: datetime
    measurements: Mapping[str, float | None]


_TEN_MINUTES = timedelta(minutes=10)
_PARAMETER_MAPPING = (
    ("tre200s0", WeatherVariable.TEMPERATURE_C, None),
    ("ure200s0", WeatherVariable.RELATIVE_HUMIDITY_PERCENT, None),
    ("tde200s0", WeatherVariable.DEW_POINT_C, None),
    ("fu3010z0", WeatherVariable.WIND_SPEED_KMH, _TEN_MINUTES),
    ("fu3010z1", WeatherVariable.WIND_GUST_KMH, _TEN_MINUTES),
    ("rre150z0", WeatherVariable.PRECIPITATION_MM, _TEN_MINUTES),
)


def map_meteoswiss_observation(
    record: MeteoSwissObservationRecord,
    station: MeteoSwissStationMetadata,
    *,
    quality_status: ObservationQualityStatus,
) -> WeatherObservationPoint:
    values = []
    for parameter, variable, aggregation_period in _PARAMETER_MAPPING:
        source_value = record.measurements.get(parameter)
        if source_value is None:
            continue
        values.append(
            WeatherValue(
                variable=variable,
                value=source_value,
                unit=CANONICAL_UNITS[variable],
                aggregation_period=aggregation_period,
            )
        )

    return WeatherObservationPoint(
        source_id="swissmetnet",
        station_id=station.station_id,
        observed_at_utc=record.observed_at_utc,
        location=WeatherLocation(
            station.latitude,
            station.longitude,
            altitude_m=station.altitude_m,
        ),
        values=tuple(values),
        quality_status=quality_status,
    )
