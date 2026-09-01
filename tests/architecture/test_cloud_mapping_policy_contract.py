import pytest

from decision.field_observation import CloudCondition
from decision.weather.cloud_mapping_policy import (
    map_cloud_cover_to_condition,
)


@pytest.mark.parametrize(
    ("cloud_cover_percent", "expected"),
    [
        (0, CloudCondition.CLEAR),
        (9.999, CloudCondition.CLEAR),
        (10, CloudCondition.FEW),
        (24.999, CloudCondition.FEW),
        (25, CloudCondition.PARTLY_CLOUDY),
        (49.999, CloudCondition.PARTLY_CLOUDY),
        (50, CloudCondition.MOSTLY_CLOUDY),
        (79.999, CloudCondition.MOSTLY_CLOUDY),
        (80, CloudCondition.OVERCAST),
        (100, CloudCondition.OVERCAST),
    ],
)
def test_maps_exact_cloud_cover_boundaries(
    cloud_cover_percent,
    expected,
):
    assert map_cloud_cover_to_condition(cloud_cover_percent) is expected


@pytest.mark.parametrize(
    "invalid",
    [
        -0.001,
        100.001,
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        False,
        "10",
    ],
)
def test_rejects_invalid_cloud_cover_values(invalid):
    with pytest.raises(
        ValueError,
        match="^invalid_cloud_cover_percent$",
    ):
        map_cloud_cover_to_condition(invalid)
