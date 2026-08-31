from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from decision.weather.meteoswiss_assets import (
    METEOSWISS_OBSERVATION_COLLECTION,
    MeteoSwissAssetMetadataError,
    MeteoSwissGranularity,
    MeteoSwissObservationAsset,
    MeteoSwissProductFamily,
    select_meteoswiss_observation_asset,
)


RECENT_KEY = "ogd-smn_abo_t_recent.csv"
RECENT_HREF = (
    "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/abo/"
    "ogd-smn_abo_t_recent.csv"
)
CHECKSUM = "1220ff8aa7694e190a4aeb5d6fe537d0110247f2d56fe185d"


def stac_item():
    return {
        "type": "Feature",
        "collection": METEOSWISS_OBSERVATION_COLLECTION,
        "id": "abo",
        "properties": {
            "title": "Adelboden (ABO)",
            "updated": "2026-08-31T10:51:42.566349Z",
        },
        "assets": {
            "ogd-smn_abo_t_now.csv": {
                "type": "text/csv",
                "href": (
                    "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/abo/"
                    "ogd-smn_abo_t_now.csv"
                ),
                "updated": "2026-08-31T10:51:42.566349Z",
                "file:checksum": "now-checksum",
            },
            RECENT_KEY: {
                "type": "text/csv",
                "href": RECENT_HREF,
                "created": "2025-04-04T10:22:53.659234Z",
                "updated": "2026-08-31T04:27:41.501431+02:00",
                "file:checksum": CHECKSUM,
            },
            "ogd-smn_abo_h_recent.csv": {
                "type": "text/csv",
                "href": "https://example.invalid/ignored.csv",
            },
            "ogd-smn_abo_t_historical_2020-2029.csv": {
                "type": "application/octet-stream",
                "href": "not-a-url",
            },
        },
    }


def select_recent(item=None):
    return select_meteoswiss_observation_asset(
        stac_item() if item is None else item,
        granularity=MeteoSwissGranularity.TEN_MINUTES,
        product_family=MeteoSwissProductFamily.RECENT,
    )


def test_selects_exact_recent_asset_and_preserves_provenance():
    selected = select_recent()

    assert selected == MeteoSwissObservationAsset(
        station_id="abo",
        granularity=MeteoSwissGranularity.TEN_MINUTES,
        product_family=MeteoSwissProductFamily.RECENT,
        href=RECENT_HREF,
        asset_key=RECENT_KEY,
        checksum=CHECKSUM,
        asset_updated_at_utc=datetime(
            2026, 8, 31, 2, 27, 41, 501431, tzinfo=timezone.utc
        ),
    )


def test_selects_now_with_the_same_exact_key_contract():
    selected = select_meteoswiss_observation_asset(
        stac_item(),
        granularity=MeteoSwissGranularity.TEN_MINUTES,
        product_family=MeteoSwissProductFamily.NOW,
    )

    assert selected.asset_key == "ogd-smn_abo_t_now.csv"
    assert selected.product_family is MeteoSwissProductFamily.NOW


def test_unknown_assets_are_ignored_and_selection_is_deterministic():
    item = stac_item()
    original = deepcopy(item)

    assert select_recent(item) == select_recent(item)
    assert item == original


def test_descriptor_is_immutable():
    selected = select_recent()

    with pytest.raises(FrozenInstanceError):
        selected.station_id = "aeg"


@pytest.mark.parametrize("collection", (None, "", "other.collection"))
def test_rejects_wrong_collection(collection):
    item = stac_item()
    item["collection"] = collection

    with pytest.raises(MeteoSwissAssetMetadataError, match="invalid_collection"):
        select_recent(item)


@pytest.mark.parametrize("station_id", (None, "", "   "))
def test_rejects_missing_or_empty_station_id(station_id):
    item = stac_item()
    item["id"] = station_id

    with pytest.raises(MeteoSwissAssetMetadataError, match="invalid_station_id"):
        select_recent(item)


def test_rejects_invalid_stac_or_assets_shape():
    with pytest.raises(MeteoSwissAssetMetadataError, match="invalid_stac_item"):
        select_recent([])

    item = stac_item()
    item["assets"] = []
    with pytest.raises(MeteoSwissAssetMetadataError, match="invalid_assets"):
        select_recent(item)


def test_rejects_missing_or_invalid_exact_asset():
    item = stac_item()
    item["assets"].pop(RECENT_KEY)
    with pytest.raises(MeteoSwissAssetMetadataError, match="asset_not_found"):
        select_recent(item)

    item = stac_item()
    item["assets"][RECENT_KEY] = "not-an-asset"
    with pytest.raises(MeteoSwissAssetMetadataError, match="invalid_asset"):
        select_recent(item)


@pytest.mark.parametrize(
    "href",
    (None, "", "/relative.csv", "http://example.test/file.csv", "https:///file.csv"),
)
def test_rejects_missing_or_invalid_https_href(href):
    item = stac_item()
    item["assets"][RECENT_KEY]["href"] = href

    with pytest.raises(MeteoSwissAssetMetadataError, match="invalid_asset_href"):
        select_recent(item)


def test_rejects_wrong_media_type():
    item = stac_item()
    item["assets"][RECENT_KEY]["type"] = "application/octet-stream"

    with pytest.raises(
        MeteoSwissAssetMetadataError, match="invalid_asset_media_type"
    ):
        select_recent(item)


@pytest.mark.parametrize("checksum", (None, "", "   "))
def test_rejects_missing_or_empty_checksum(checksum):
    item = stac_item()
    item["assets"][RECENT_KEY]["file:checksum"] = checksum

    with pytest.raises(
        MeteoSwissAssetMetadataError, match="invalid_asset_checksum"
    ):
        select_recent(item)


@pytest.mark.parametrize(
    "updated",
    (None, "", "not-a-timestamp", "2026-08-31T02:27:41.501431"),
)
def test_rejects_missing_invalid_or_naive_updated_timestamp(updated):
    item = stac_item()
    item["assets"][RECENT_KEY]["updated"] = updated

    with pytest.raises(
        MeteoSwissAssetMetadataError, match="invalid_asset_updated"
    ):
        select_recent(item)


@pytest.mark.parametrize(
    ("granularity", "product_family"),
    (
        (MeteoSwissGranularity.TEN_MINUTES, MeteoSwissProductFamily.HISTORICAL),
        (MeteoSwissGranularity.HOURLY, MeteoSwissProductFamily.RECENT),
        (MeteoSwissGranularity.DAILY, MeteoSwissProductFamily.RECENT),
        (MeteoSwissGranularity.MONTHLY, MeteoSwissProductFamily.RECENT),
        (MeteoSwissGranularity.YEARLY, MeteoSwissProductFamily.RECENT),
    ),
)
def test_rejects_combinations_outside_v1(granularity, product_family):
    with pytest.raises(
        MeteoSwissAssetMetadataError, match="unsupported_product_selection"
    ):
        select_meteoswiss_observation_asset(
            stac_item(),
            granularity=granularity,
            product_family=product_family,
        )


def test_rejects_raw_strings_instead_of_enums():
    with pytest.raises(MeteoSwissAssetMetadataError, match="invalid_granularity"):
        select_meteoswiss_observation_asset(
            stac_item(), granularity="t", product_family=MeteoSwissProductFamily.RECENT
        )

    with pytest.raises(
        MeteoSwissAssetMetadataError, match="invalid_product_family"
    ):
        select_meteoswiss_observation_asset(
            stac_item(),
            granularity=MeteoSwissGranularity.TEN_MINUTES,
            product_family="recent",
        )
