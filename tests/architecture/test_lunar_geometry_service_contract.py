from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timezone
from pathlib import Path
import warnings

from astropy.coordinates import NonRotationTransformationWarning
import pytest

from decision.models.context.site_context import SiteContext
from decision.models.imaging_field_geometry import (
    ImagingFieldGeometryDefinition,
)
from decision.models.lunar_geometry import LunarGeometry
from decision.services.lunar_geometry_service import LunarGeometryService


FIXED_SITE = SiteContext(
    name="Buttes",
    latitude=46.7508,
    longitude=6.5495,
    elevation=770.0,
    bortle=4,
)
FIXED_FIELD = ImagingFieldGeometryDefinition(
    imaging_field_id="sh2-129_ou4",
    reference_ra_deg=317.95,
    reference_dec_deg=59.97,
)
FIXED_TIME = datetime(2024, 10, 15, 20, 0, tzinfo=timezone.utc)


def _calculate(
    *,
    reference_time: datetime = FIXED_TIME,
    site: SiteContext = FIXED_SITE,
    field_geometry: ImagingFieldGeometryDefinition = FIXED_FIELD,
) -> LunarGeometry:
    return LunarGeometryService.calculate(
        reference_time=reference_time,
        site=site,
        field_geometry=field_geometry,
    )


def test_result_model_is_minimal_immutable_and_non_optional():
    result = _calculate()

    assert tuple(field.name for field in fields(result)) == (
        "moon_illumination",
        "moon_altitude_deg",
        "moon_separation_deg",
    )
    assert all(isinstance(value, float) for value in (
        result.moon_illumination,
        result.moon_altitude_deg,
        result.moon_separation_deg,
    ))
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.moon_illumination = None


def test_zero_values_are_valid_physical_results_not_sentinels():
    result = LunarGeometry(
        moon_illumination=0.0,
        moon_altitude_deg=0.0,
        moon_separation_deg=0.0,
    )

    assert result == LunarGeometry(0.0, 0.0, 0.0)


def test_rejects_naive_reference_time_and_accepts_aware_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        _calculate(reference_time=datetime(2024, 10, 15, 20, 0))

    assert isinstance(_calculate(), LunarGeometry)


def test_rejects_wrong_reference_time_and_site_types():
    with pytest.raises(TypeError, match="reference_time"):
        _calculate(reference_time="2024-10-15T20:00:00Z")
    with pytest.raises(TypeError, match="SiteContext"):
        _calculate(site=object())


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("latitude", "46.7508"),
        ("latitude", True),
        ("latitude", float("nan")),
        ("latitude", float("inf")),
        ("latitude", -90.01),
        ("latitude", 90.01),
        ("longitude", "6.5495"),
        ("longitude", False),
        ("longitude", float("nan")),
        ("longitude", float("-inf")),
        ("longitude", -180.01),
        ("longitude", 180.01),
        ("elevation", "770"),
        ("elevation", True),
        ("elevation", float("nan")),
        ("elevation", float("inf")),
    ],
)
def test_rejects_invalid_site_values(field_name, invalid_value):
    with pytest.raises(ValueError, match=field_name):
        _calculate(site=replace(FIXED_SITE, **{field_name: invalid_value}))


@pytest.mark.parametrize(
    ("latitude", "longitude", "elevation"),
    [(-90.0, -180.0, 0.0), (90.0, 180.0, -430.0)],
)
def test_accepts_site_boundaries_and_zero_or_negative_elevation(
    latitude,
    longitude,
    elevation,
):
    result = _calculate(
        site=replace(
            FIXED_SITE,
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
        )
    )

    assert isinstance(result, LunarGeometry)


@pytest.mark.parametrize("field_geometry", [None, object(), "sh2-129_ou4"])
def test_rejects_wrong_field_geometry_type(field_geometry):
    with pytest.raises(TypeError, match="ImagingFieldGeometryDefinition"):
        _calculate(field_geometry=field_geometry)


def test_outputs_stay_within_canonical_bounds():
    result = _calculate()

    assert 0.0 <= result.moon_illumination <= 1.0
    assert -90.0 <= result.moon_altitude_deg <= 90.0
    assert 0.0 <= result.moon_separation_deg <= 180.0


def test_fixed_inputs_produce_deterministic_geometry():
    first = _calculate()
    second = _calculate()

    assert second == first
    assert first.moon_illumination == pytest.approx(
        0.9592463857867323,
        abs=1e-9,
    )
    assert first.moon_altitude_deg == pytest.approx(
        35.51214003412875,
        abs=1e-8,
    )
    assert first.moon_separation_deg == pytest.approx(
        69.68509418670513,
        abs=1e-8,
    )


def test_moon_below_horizon_is_a_valid_negative_altitude():
    result = _calculate(
        reference_time=datetime(
            2024,
            1,
            1,
            12,
            0,
            tzinfo=timezone.utc,
        )
    )

    assert result.moon_altitude_deg < 0.0


def test_new_moon_is_darker_than_full_moon():
    near_new_moon = _calculate(
        reference_time=datetime(
            2024,
            4,
            8,
            18,
            0,
            tzinfo=timezone.utc,
        )
    )
    near_full_moon = _calculate(
        reference_time=datetime(
            2024,
            4,
            23,
            23,
            0,
            tzinfo=timezone.utc,
        )
    )

    assert near_new_moon.moon_illumination < 0.01
    assert near_full_moon.moon_illumination > 0.99
    assert (
        near_full_moon.moon_illumination
        > near_new_moon.moon_illumination
    )


def test_common_apparent_frame_avoids_icrs_gcrs_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _calculate()

    assert not any(
        isinstance(item.message, NonRotationTransformationWarning)
        for item in caught
    )


def test_service_source_has_no_legacy_or_scoring_dependencies():
    service_source = Path(
        "decision/services/lunar_geometry_service.py"
    ).read_text(encoding="utf-8")

    for forbidden_dependency in (
        "SkyEngine",
        "CATALOG",
        "moon_penalty",
        "astral",
    ):
        assert forbidden_dependency not in service_source
