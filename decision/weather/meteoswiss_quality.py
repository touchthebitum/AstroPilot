from __future__ import annotations

from dataclasses import dataclass

from decision.weather.meteoswiss_assets import (
    MeteoSwissObservationAsset,
    MeteoSwissProductFamily,
)
from decision.weather.provider_reliability import ObservationQualityStatus


@dataclass(frozen=True)
class MeteoSwissObservationQuality:
    status: ObservationQualityStatus
    reason: str


def determine_meteoswiss_observation_quality(
    asset: MeteoSwissObservationAsset,
) -> MeteoSwissObservationQuality:
    if not isinstance(asset, MeteoSwissObservationAsset):
        raise ValueError("invalid_meteoswiss_observation_asset")
    if not isinstance(asset.product_family, MeteoSwissProductFamily):
        raise ValueError("invalid_meteoswiss_product_family")

    if asset.product_family is MeteoSwissProductFamily.NOW:
        reason = "meteoswiss_realtime_quality_unverified"
    elif asset.product_family in (
        MeteoSwissProductFamily.RECENT,
        MeteoSwissProductFamily.HISTORICAL,
    ):
        reason = "meteoswiss_quality_not_explicitly_established"
    else:
        raise ValueError("invalid_meteoswiss_product_family")

    return MeteoSwissObservationQuality(
        status=ObservationQualityStatus.UNVERIFIED,
        reason=reason,
    )
