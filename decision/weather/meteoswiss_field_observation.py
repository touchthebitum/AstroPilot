from __future__ import annotations

import re
from dataclasses import dataclass

from decision.weather.meteoswiss_assets import MeteoSwissObservationAsset
from decision.weather.meteoswiss_observation import (
    MeteoSwissStationMetadata,
    map_meteoswiss_observation,
)
from decision.weather.meteoswiss_parsing import parse_meteoswiss_observation_csv
from decision.weather.meteoswiss_quality import (
    MeteoSwissObservationQuality,
    determine_meteoswiss_observation_quality,
)
from decision.weather.provider_reliability import WeatherObservationPoint


class MeteoSwissFieldObservationError(ValueError):
    pass


@dataclass(frozen=True)
class MeteoSwissFieldObservationBatch:
    observations: tuple[WeatherObservationPoint, ...]
    quality: MeteoSwissObservationQuality


def build_meteoswiss_field_observations(
    *,
    asset: MeteoSwissObservationAsset,
    csv_text: str,
    station: MeteoSwissStationMetadata,
) -> MeteoSwissFieldObservationBatch:
    if not isinstance(asset.station_id, str) or re.fullmatch(
        r"[a-z]{3}", asset.station_id
    ) is None:
        raise MeteoSwissFieldObservationError("invalid_asset_station_id")

    expected_station_id = asset.station_id.upper()
    if station.station_id != expected_station_id:
        raise MeteoSwissFieldObservationError("station_identity_mismatch")

    records = parse_meteoswiss_observation_csv(
        csv_text,
        expected_station_id=expected_station_id,
    )
    quality = determine_meteoswiss_observation_quality(asset)
    observations = tuple(
        map_meteoswiss_observation(
            record,
            station,
            quality_status=quality.status,
        )
        for record in records
    )

    return MeteoSwissFieldObservationBatch(
        observations=observations,
        quality=quality,
    )
