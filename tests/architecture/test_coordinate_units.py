from astropy.time import Time
import pytest

from astropilot.engines.sky_engine import SkyEngine
from decision.season.dynamic_season_engine import DynamicSeasonEngine


def test_dynamic_season_uses_catalog_ra_in_degrees(
    frozen_time,
    buttes_site,
    m31_target,
):
    expected = SkyEngine().target_altitude(
        m31_target["ra"],
        m31_target["dec"],
        Time(frozen_time),
        buttes_site.latitude,
        buttes_site.longitude,
    )

    actual = DynamicSeasonEngine.target_altitude_at_time(
        m31_target,
        buttes_site.latitude,
        buttes_site.longitude,
        frozen_time,
    )

    assert actual == pytest.approx(expected, abs=1e-6)

