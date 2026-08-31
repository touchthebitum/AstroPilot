from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import urlparse


METEOSWISS_OBSERVATION_COLLECTION = "ch.meteoschweiz.ogd-smn"


class MeteoSwissGranularity(str, Enum):
    TEN_MINUTES = "t"
    HOURLY = "h"
    DAILY = "d"
    MONTHLY = "m"
    YEARLY = "y"


class MeteoSwissProductFamily(str, Enum):
    NOW = "now"
    RECENT = "recent"
    HISTORICAL = "historical"


class MeteoSwissAssetMetadataError(ValueError):
    pass


@dataclass(frozen=True)
class MeteoSwissObservationAsset:
    station_id: str
    granularity: MeteoSwissGranularity
    product_family: MeteoSwissProductFamily
    href: str
    asset_key: str
    checksum: str
    asset_updated_at_utc: datetime


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MeteoSwissAssetMetadataError(f"invalid_{field}")
    return value


def _https_href(value: object) -> str:
    href = _required_string(value, "asset_href")
    parsed = urlparse(href)
    if parsed.scheme != "https" or not parsed.hostname:
        raise MeteoSwissAssetMetadataError("invalid_asset_href")
    return href


def _updated_at_utc(value: object) -> datetime:
    updated = _required_string(value, "asset_updated")
    try:
        parsed = datetime.fromisoformat(updated)
    except ValueError as error:
        raise MeteoSwissAssetMetadataError("invalid_asset_updated") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MeteoSwissAssetMetadataError("invalid_asset_updated")
    return parsed.astimezone(timezone.utc)


def select_meteoswiss_observation_asset(
    stac_item: Mapping[str, object],
    *,
    granularity: MeteoSwissGranularity,
    product_family: MeteoSwissProductFamily,
) -> MeteoSwissObservationAsset:
    if not isinstance(stac_item, Mapping):
        raise MeteoSwissAssetMetadataError("invalid_stac_item")
    if not isinstance(granularity, MeteoSwissGranularity):
        raise MeteoSwissAssetMetadataError("invalid_granularity")
    if not isinstance(product_family, MeteoSwissProductFamily):
        raise MeteoSwissAssetMetadataError("invalid_product_family")
    if (
        granularity is not MeteoSwissGranularity.TEN_MINUTES
        or product_family
        not in (MeteoSwissProductFamily.NOW, MeteoSwissProductFamily.RECENT)
    ):
        raise MeteoSwissAssetMetadataError("unsupported_product_selection")
    if stac_item.get("collection") != METEOSWISS_OBSERVATION_COLLECTION:
        raise MeteoSwissAssetMetadataError("invalid_collection")

    station_id = _required_string(stac_item.get("id"), "station_id")
    assets = stac_item.get("assets")
    if not isinstance(assets, Mapping):
        raise MeteoSwissAssetMetadataError("invalid_assets")

    asset_key = (
        f"ogd-smn_{station_id}_{granularity.value}_{product_family.value}.csv"
    )
    asset = assets.get(asset_key)
    if asset is None:
        raise MeteoSwissAssetMetadataError("asset_not_found")
    if not isinstance(asset, Mapping):
        raise MeteoSwissAssetMetadataError("invalid_asset")

    href = _https_href(asset.get("href"))
    if asset.get("type") != "text/csv":
        raise MeteoSwissAssetMetadataError("invalid_asset_media_type")
    checksum = _required_string(asset.get("file:checksum"), "asset_checksum")
    updated_at_utc = _updated_at_utc(asset.get("updated"))

    return MeteoSwissObservationAsset(
        station_id=station_id,
        granularity=granularity,
        product_family=product_family,
        href=href,
        asset_key=asset_key,
        checksum=checksum,
        asset_updated_at_utc=updated_at_utc,
    )
