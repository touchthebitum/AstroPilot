from datetime import datetime, timezone

import pytest

from decision.weather.meteoswiss_parsing import (
    MeteoSwissParsingError,
    parse_meteoswiss_observation_csv,
    parse_meteoswiss_station_metadata_csv,
)


OBSERVATION_HEADER = (
    "station_abbr;reference_timestamp;tre200s0;ure200s0;tde200s0;"
    "fu3010z0;fu3010z1;rre150z0;dkl010z0;gre000z0"
)


def observation_csv(*rows: str) -> str:
    return "\n".join((OBSERVATION_HEADER, *rows))


def test_parses_realistic_recent_observation_with_six_supported_measurements():
    text = observation_csv(
        "ABO;01.01.2026 00:10;-5.8;82.0;-8.1;12.5;20.0;0.4;180;15.2"
    )

    records = parse_meteoswiss_observation_csv(text, expected_station_id="ABO")

    assert len(records) == 1
    assert records[0].observed_at_utc == datetime(
        2026, 1, 1, 0, 10, tzinfo=timezone.utc
    )
    assert records[0].measurements == {
        "tre200s0": -5.8,
        "ure200s0": 82.0,
        "tde200s0": -8.1,
        "fu3010z0": 12.5,
        "fu3010z1": 20.0,
        "rre150z0": 0.4,
    }
    assert tuple(records[0].measurements) == (
        "tre200s0",
        "ure200s0",
        "tde200s0",
        "fu3010z0",
        "fu3010z1",
        "rre150z0",
    )


def test_empty_measurements_become_none_while_explicit_zero_is_preserved():
    text = observation_csv("ABO;01.01.2026 00:10; ;0;\t;0.0;;;180;15.2")

    record = parse_meteoswiss_observation_csv(
        text, expected_station_id=" ABO "
    )[0]

    assert record.measurements == {
        "tre200s0": None,
        "ure200s0": 0.0,
        "tde200s0": None,
        "fu3010z0": 0.0,
        "fu3010z1": None,
        "rre150z0": None,
    }


def test_malformed_supported_measurement_is_rejected():
    text = observation_csv(
        "ABO;01.01.2026 00:10;-5.8;not-a-number;-8.1;12.5;20.0;0.4;180;15.2"
    )

    with pytest.raises(MeteoSwissParsingError, match="ure200s0"):
        parse_meteoswiss_observation_csv(text, expected_station_id="ABO")


def test_missing_supported_observation_header_is_rejected():
    text = OBSERVATION_HEADER.replace(";rre150z0", "") + "\n"

    with pytest.raises(MeteoSwissParsingError, match="rre150z0"):
        parse_meteoswiss_observation_csv(text, expected_station_id="ABO")


def test_multiple_unsorted_and_duplicate_rows_preserve_file_order():
    text = observation_csv(
        "ABO;01.01.2026 00:20;2;3;4;5;6;7;180;15.2",
        "ABO;01.01.2026 00:10;8;9;10;11;12;13;180;15.2",
        "ABO;01.01.2026 00:20;14;15;16;17;18;19;180;15.2",
    )

    first = parse_meteoswiss_observation_csv(text, expected_station_id="ABO")
    second = parse_meteoswiss_observation_csv(text, expected_station_id="ABO")

    assert first == second
    assert [record.observed_at_utc.minute for record in first] == [20, 10, 20]
    assert [record.measurements["tre200s0"] for record in first] == [2.0, 8.0, 14.0]


def test_observation_station_mismatch_is_rejected_without_case_normalization():
    text = observation_csv(
        "ABO;01.01.2026 00:10;-5.8;82.0;-8.1;12.5;20.0;0.4;180;15.2"
    )

    with pytest.raises(MeteoSwissParsingError, match="unexpected_station_id"):
        parse_meteoswiss_observation_csv(text, expected_station_id="abo")


def test_invalid_or_empty_observation_identity_and_timestamp_are_rejected():
    invalid_rows = (
        ";01.01.2026 00:10;-5.8;82;-8.1;12.5;20;0.4;180;15.2",
        "ABO;;-5.8;82;-8.1;12.5;20;0.4;180;15.2",
        "ABO;2026-01-01T00:10;-5.8;82;-8.1;12.5;20;0.4;180;15.2",
    )

    for row in invalid_rows:
        with pytest.raises(MeteoSwissParsingError):
            parse_meteoswiss_observation_csv(
                observation_csv(row), expected_station_id="ABO"
            )


def test_valid_observation_header_without_data_returns_empty_tuple():
    assert (
        parse_meteoswiss_observation_csv(
            OBSERVATION_HEADER, expected_station_id="ABO"
        )
        == ()
    )


METADATA_HEADER = (
    "station_abbr;station_name;station_canton;station_wigos_id;"
    "station_height_masl;station_height_barometer_masl;"
    "station_coordinates_wgs84_lat;station_coordinates_wgs84_lon;station_url_en"
)


def test_parses_station_metadata_and_preserves_missing_altitude():
    text = "\n".join(
        (
            METADATA_HEADER,
            "ABO;Adelboden;BE;0-20000-0-06631-0;1321.0;1327.0;46.491703;7.560703;url",
            "AEG;Aegeri;ZG;0-20000-0-06632-0;;;47.114;8.612;url",
        )
    )

    stations = parse_meteoswiss_station_metadata_csv(text)

    assert stations[0].station_id == "ABO"
    assert stations[0].latitude == 46.491703
    assert stations[0].longitude == 7.560703
    assert stations[0].altitude_m == 1321.0
    assert stations[1].station_id == "AEG"
    assert stations[1].altitude_m is None


@pytest.mark.parametrize(
    "row",
    (
        ";Adelboden;BE;wigos;1321;1327;46.49;7.56;url",
        "ABO;Adelboden;BE;wigos;1321;1327;;7.56;url",
        "ABO;Adelboden;BE;wigos;1321;1327;invalid;7.56;url",
        "ABO;Adelboden;BE;wigos;invalid;1327;46.49;7.56;url",
    ),
)
def test_invalid_station_metadata_values_are_rejected(row):
    with pytest.raises(MeteoSwissParsingError):
        parse_meteoswiss_station_metadata_csv("\n".join((METADATA_HEADER, row)))


def test_missing_required_station_metadata_header_is_rejected():
    text = METADATA_HEADER.replace(";station_coordinates_wgs84_lon", "")

    with pytest.raises(
        MeteoSwissParsingError, match="station_coordinates_wgs84_lon"
    ):
        parse_meteoswiss_station_metadata_csv(text)
