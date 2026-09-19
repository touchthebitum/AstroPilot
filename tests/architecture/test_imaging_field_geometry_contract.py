from dataclasses import FrozenInstanceError, fields
from math import nextafter

import pytest

from decision.models.imaging_field_geometry import (
    ImagingFieldGeometryDefinition,
)
from decision.services.imaging_field_geometry_resolver import (
    ImagingFieldGeometryResolutionError,
    ImagingFieldGeometryResolver,
)


def _geometry(
    imaging_field_id: str = "sh2-129_ou4",
) -> ImagingFieldGeometryDefinition:
    return ImagingFieldGeometryDefinition(
        imaging_field_id=imaging_field_id,
        reference_ra_deg=317.95,
        reference_dec_deg=59.97,
    )


def test_valid_composite_field_geometry_is_immutable_icrs_j2000_reference():
    geometry = _geometry()

    assert geometry.imaging_field_id == "sh2-129_ou4"
    assert geometry.reference_ra_deg == 317.95
    assert geometry.reference_dec_deg == 59.97
    assert "ICRS/J2000" in ImagingFieldGeometryDefinition.__doc__
    with pytest.raises((FrozenInstanceError, AttributeError)):
        geometry.reference_ra_deg = 0.0


def test_model_stays_minimal_and_preserves_exact_field_identity():
    geometry = _geometry(" sh2-129_ou4 ")

    assert tuple(field.name for field in fields(geometry)) == (
        "imaging_field_id",
        "reference_ra_deg",
        "reference_dec_deg",
    )
    assert geometry.imaging_field_id == " sh2-129_ou4 "


@pytest.mark.parametrize("imaging_field_id", ["", "   ", 42, None])
def test_rejects_empty_or_non_string_imaging_field_id(imaging_field_id):
    with pytest.raises(ValueError, match="imaging_field_id"):
        ImagingFieldGeometryDefinition(imaging_field_id, 0.0, 0.0)


@pytest.mark.parametrize(
    "reference_ra_deg",
    [True, False, "317.95", None, float("nan"), float("inf"), -0.01, 360.0],
)
def test_rejects_invalid_reference_ra(reference_ra_deg):
    with pytest.raises(ValueError, match="reference_ra_deg"):
        ImagingFieldGeometryDefinition(
            "sh2-129_ou4",
            reference_ra_deg,
            0.0,
        )


@pytest.mark.parametrize(
    "reference_dec_deg",
    [
        True,
        False,
        "59.97",
        None,
        float("nan"),
        float("-inf"),
        -90.01,
        90.01,
    ],
)
def test_rejects_invalid_reference_dec(reference_dec_deg):
    with pytest.raises(ValueError, match="reference_dec_deg"):
        ImagingFieldGeometryDefinition(
            "sh2-129_ou4",
            0.0,
            reference_dec_deg,
        )


@pytest.mark.parametrize(
    ("reference_ra_deg", "reference_dec_deg"),
    [
        (0.0, -90.0),
        (nextafter(360.0, 0.0), 90.0),
    ],
)
def test_accepts_exact_coordinate_boundaries(
    reference_ra_deg,
    reference_dec_deg,
):
    geometry = ImagingFieldGeometryDefinition(
        "boundary-field",
        reference_ra_deg,
        reference_dec_deg,
    )

    assert geometry.reference_ra_deg == reference_ra_deg
    assert geometry.reference_dec_deg == reference_dec_deg


def test_resolver_uses_exact_key_without_normalization():
    geometry = _geometry()
    resolver = ImagingFieldGeometryResolver([geometry])

    assert resolver.resolve("sh2-129_ou4") is geometry
    for field_id in ("SH2-129_OU4", " sh2-129_ou4 "):
        with pytest.raises(ImagingFieldGeometryResolutionError):
            resolver.resolve(field_id)


@pytest.mark.parametrize("field_id", ["unknown", "", "   ", 42, None])
def test_resolver_rejects_unknown_empty_or_non_string_ids(field_id):
    resolver = ImagingFieldGeometryResolver([])

    with pytest.raises(ImagingFieldGeometryResolutionError):
        resolver.resolve(field_id)


def test_resolver_rejects_duplicate_imaging_field_ids():
    with pytest.raises(
        ImagingFieldGeometryResolutionError,
        match="duplicate imaging_field_id",
    ):
        ImagingFieldGeometryResolver([_geometry(), _geometry()])


@pytest.mark.parametrize("definitions", [[object()], iter(())])
def test_resolver_rejects_wrong_collection_types(definitions):
    with pytest.raises(TypeError):
        ImagingFieldGeometryResolver(definitions)


def test_resolver_snapshots_source_collection():
    original = _geometry()
    definitions = [original]
    resolver = ImagingFieldGeometryResolver(definitions)

    definitions.clear()
    definitions.append(_geometry("replacement"))

    assert resolver.resolve("sh2-129_ou4") is original
    with pytest.raises(ImagingFieldGeometryResolutionError):
        resolver.resolve("replacement")
