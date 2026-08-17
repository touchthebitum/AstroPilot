from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
import pytest

from astropilot.catalog import CATALOG
from astropilot.engines.sky_engine import SkyEngine
from decision.season.dynamic_season_engine import DynamicSeasonEngine


@pytest.mark.parametrize("target_key", sorted(CATALOG))
def test_all_active_altitude_consumers_agree(
    target_key,
    frozen_time,
    buttes_site,
):
    target = CATALOG[target_key]
    expected = SkyEngine().target_altitude(
        target["ra"],
        target["dec"],
        Time(frozen_time),
        buttes_site.latitude,
        buttes_site.longitude,
    )

    actual = DynamicSeasonEngine.target_altitude_at_time(
        target,
        buttes_site.latitude,
        buttes_site.longitude,
        frozen_time,
    )

    assert actual == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(
    ("alias_key", "canonical_key"),
    [
        ("Heart", "IC1805"),
        ("Soul", "IC1848"),
    ],
)
def test_alias_coordinates_match_canonical_ic_region(
    alias_key,
    canonical_key,
):
    alias = CATALOG[alias_key]
    canonical = CATALOG[canonical_key]

    alias_coord = SkyCoord(
        ra=alias["ra"] * u.deg,
        dec=alias["dec"] * u.deg,
    )
    canonical_coord = SkyCoord(
        ra=canonical["ra"] * u.deg,
        dec=canonical["dec"] * u.deg,
    )

    assert alias_coord.separation(canonical_coord).deg < 0.2


def test_ic1848_matches_reviewed_siril_reference():
    assert CATALOG["IC1848"]["ra"] == pytest.approx(42.825)
    assert CATALOG["IC1848"]["dec"] == pytest.approx(60.408333)


@pytest.mark.parametrize(
    ("target_key", "expected_altitude_deg"),
    [
        ("M31", 61.00118446621394),
        ("IC1396", 78.5391236932682),
        ("Rosette", -20.34365712923036),
        ("Heart", 49.76735084982112),
        ("Soul", 47.41473213409534),
        ("Veil", 68.14691977437947),
    ],
)
def test_frozen_buttes_altitudes(
    target_key,
    expected_altitude_deg,
    frozen_time,
    buttes_site,
):
    target = CATALOG[target_key]

    altitude = SkyEngine().target_altitude(
        target["ra"],
        target["dec"],
        Time(frozen_time),
        buttes_site.latitude,
        buttes_site.longitude,
    )

    assert altitude == pytest.approx(expected_altitude_deg, abs=1e-6)
