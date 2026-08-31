from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

from decision.weather.meteoswiss_observation import (
    MeteoSwissObservationRecord,
    MeteoSwissStationMetadata,
)


class MeteoSwissParsingError(ValueError):
    pass


_MEASUREMENT_IDS = (
    "tre200s0",
    "ure200s0",
    "tde200s0",
    "fu3010z0",
    "fu3010z1",
    "rre150z0",
)
_OBSERVATION_COLUMNS = ("station_abbr", "reference_timestamp", *_MEASUREMENT_IDS)
_STATION_METADATA_COLUMNS = (
    "station_abbr",
    "station_coordinates_wgs84_lat",
    "station_coordinates_wgs84_lon",
    "station_height_masl",
)


def _reader(text: str, required_columns: tuple[str, ...]) -> csv.DictReader:
    reader = csv.DictReader(StringIO(text), delimiter=";")
    available_columns = set(reader.fieldnames or ())
    missing_columns = tuple(
        column for column in required_columns if column not in available_columns
    )
    if missing_columns:
        raise MeteoSwissParsingError(
            f"missing_required_columns: {', '.join(missing_columns)}"
        )
    return reader


def _required_text(value: str | None, field: str) -> str:
    normalized = value.strip() if value is not None else ""
    if not normalized:
        raise MeteoSwissParsingError(f"missing_required_value: {field}")
    return normalized


def _optional_float(value: str | None, field: str) -> float | None:
    normalized = value.strip() if value is not None else ""
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError as error:
        raise MeteoSwissParsingError(f"invalid_numeric_value: {field}") from error


def _required_float(value: str | None, field: str) -> float:
    parsed = _optional_float(value, field)
    if parsed is None:
        raise MeteoSwissParsingError(f"missing_required_value: {field}")
    return parsed


def _reference_timestamp(value: str | None) -> datetime:
    normalized = _required_text(value, "reference_timestamp")
    try:
        return datetime.strptime(normalized, "%d.%m.%Y %H:%M").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise MeteoSwissParsingError("invalid_reference_timestamp") from error


def parse_meteoswiss_observation_csv(
    text: str,
    *,
    expected_station_id: str,
) -> tuple[MeteoSwissObservationRecord, ...]:
    expected_station = _required_text(expected_station_id, "expected_station_id")
    reader = _reader(text, _OBSERVATION_COLUMNS)
    records = []

    for row in reader:
        station_id = _required_text(row.get("station_abbr"), "station_abbr")
        if station_id != expected_station:
            raise MeteoSwissParsingError(f"unexpected_station_id: {station_id}")
        records.append(
            MeteoSwissObservationRecord(
                observed_at_utc=_reference_timestamp(row.get("reference_timestamp")),
                measurements={
                    measurement_id: _optional_float(
                        row.get(measurement_id), measurement_id
                    )
                    for measurement_id in _MEASUREMENT_IDS
                },
            )
        )

    return tuple(records)


def parse_meteoswiss_station_metadata_csv(
    text: str,
) -> tuple[MeteoSwissStationMetadata, ...]:
    reader = _reader(text, _STATION_METADATA_COLUMNS)
    stations = []

    for row in reader:
        stations.append(
            MeteoSwissStationMetadata(
                station_id=_required_text(row.get("station_abbr"), "station_abbr"),
                latitude=_required_float(
                    row.get("station_coordinates_wgs84_lat"),
                    "station_coordinates_wgs84_lat",
                ),
                longitude=_required_float(
                    row.get("station_coordinates_wgs84_lon"),
                    "station_coordinates_wgs84_lon",
                ),
                altitude_m=_optional_float(
                    row.get("station_height_masl"), "station_height_masl"
                ),
            )
        )

    return tuple(stations)
