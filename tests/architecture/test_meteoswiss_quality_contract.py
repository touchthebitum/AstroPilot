from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from inspect import signature

import pytest

from decision.weather.meteoswiss_assets import (
    MeteoSwissGranularity,
    MeteoSwissObservationAsset,
    MeteoSwissProductFamily,
)
from decision.weather.meteoswiss_quality import (
    MeteoSwissObservationQuality,
    determine_meteoswiss_observation_quality,
)
from decision.weather.provider_reliability import ObservationQualityStatus


def asset(
    product_family=MeteoSwissProductFamily.RECENT,
    *,
    granularity=MeteoSwissGranularity.TEN_MINUTES,
    checksum="1220checksum",
    updated_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
):
    return MeteoSwissObservationAsset(
        station_id="abo",
        granularity=granularity,
        product_family=product_family,
        href="https://data.geo.admin.ch/observation.csv",
        asset_key="ogd-smn_abo_t_recent.csv",
        checksum=checksum,
        asset_updated_at_utc=updated_at,
    )


@pytest.mark.parametrize(
    ("product_family", "reason"),
    (
        (
            MeteoSwissProductFamily.NOW,
            "meteoswiss_realtime_quality_unverified",
        ),
        (
            MeteoSwissProductFamily.RECENT,
            "meteoswiss_quality_not_explicitly_established",
        ),
        (
            MeteoSwissProductFamily.HISTORICAL,
            "meteoswiss_quality_not_explicitly_established",
        ),
    ),
)
def test_product_families_are_conservatively_unverified(product_family, reason):
    quality = determine_meteoswiss_observation_quality(asset(product_family))

    assert quality == MeteoSwissObservationQuality(
        status=ObservationQualityStatus.UNVERIFIED,
        reason=reason,
    )
    assert quality.status is not ObservationQualityStatus.VALIDATED
    assert quality.status is not ObservationQualityStatus.REJECTED


def test_checksum_does_not_influence_quality():
    first = determine_meteoswiss_observation_quality(asset(checksum="first"))
    second = determine_meteoswiss_observation_quality(asset(checksum="second"))

    assert first == second


def test_asset_updated_timestamp_does_not_influence_quality():
    first = determine_meteoswiss_observation_quality(
        asset(updated_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    )
    second = determine_meteoswiss_observation_quality(
        asset(updated_at=datetime(2030, 1, 1, tzinfo=timezone.utc))
    )

    assert first == second


@pytest.mark.parametrize("granularity", tuple(MeteoSwissGranularity))
def test_granularity_does_not_promote_quality(granularity):
    quality = determine_meteoswiss_observation_quality(
        asset(granularity=granularity)
    )

    assert quality.status is ObservationQualityStatus.UNVERIFIED


def test_result_is_immutable_and_deterministic():
    source_asset = asset()

    first = determine_meteoswiss_observation_quality(source_asset)
    second = determine_meteoswiss_observation_quality(source_asset)

    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.status = ObservationQualityStatus.VALIDATED


def test_policy_has_no_clock_or_other_context_input():
    assert tuple(signature(determine_meteoswiss_observation_quality).parameters) == (
        "asset",
    )


def test_input_and_product_family_are_runtime_strict():
    with pytest.raises(ValueError, match="invalid_meteoswiss_observation_asset"):
        determine_meteoswiss_observation_quality({})

    invalid_asset = asset(product_family="recent")
    with pytest.raises(ValueError, match="invalid_meteoswiss_product_family"):
        determine_meteoswiss_observation_quality(invalid_asset)
