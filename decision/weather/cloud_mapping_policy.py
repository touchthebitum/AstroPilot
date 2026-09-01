from math import isfinite

from decision.field_observation import CloudCondition


def map_cloud_cover_to_condition(
    cloud_cover_percent: int | float,
) -> CloudCondition:
    if (
        isinstance(cloud_cover_percent, bool)
        or not isinstance(cloud_cover_percent, (int, float))
        or not isfinite(cloud_cover_percent)
        or not 0 <= cloud_cover_percent <= 100
    ):
        raise ValueError("invalid_cloud_cover_percent")

    if cloud_cover_percent < 10:
        return CloudCondition.CLEAR
    if cloud_cover_percent < 25:
        return CloudCondition.FEW
    if cloud_cover_percent < 50:
        return CloudCondition.PARTLY_CLOUDY
    if cloud_cover_percent < 80:
        return CloudCondition.MOSTLY_CLOUDY
    return CloudCondition.OVERCAST
