from dataclasses import FrozenInstanceError

import pytest

from decision.calculators.setup_calculator import SetupCalculator
from decision.models.equipment.setup_capabilities import SetupCapabilities


def test_setup_calculator_computes_reference_setup_capabilities(
    frozen_equipment,
):
    capabilities = SetupCalculator.compute(frozen_equipment.setup)

    assert isinstance(capabilities, SetupCapabilities)
    assert capabilities.sampling_arcsec_per_pixel == pytest.approx(
        3.6669333333333327,
    )
    assert capabilities.field_width_deg == pytest.approx(5.598181632)
    assert capabilities.field_height_deg == pytest.approx(3.740269824)
    assert capabilities.field_diagonal_deg == pytest.approx(
        6.73270049394648,
    )
    assert capabilities.focal_ratio == 2.8
    assert capabilities.collecting_area_mm2 == pytest.approx(
        1809.5573684677208,
    )
    assert capabilities.relative_speed == pytest.approx(
        0.1275510204081633,
    )
    assert capabilities.limiting_resolution_arcsec is None


def test_compute_sampling_matches_full_capability_result(frozen_equipment):
    direct_sampling = SetupCalculator.compute_sampling(frozen_equipment.setup)
    capabilities = SetupCalculator.compute(frozen_equipment.setup)

    assert direct_sampling == capabilities.sampling_arcsec_per_pixel


def test_setup_calculation_does_not_mutate_equipment(frozen_equipment):
    setup = frozen_equipment.setup
    original = {
        "pixel_size_um": setup.camera.pixel_size_um,
        "sensor_width_px": setup.camera.sensor_width_px,
        "sensor_height_px": setup.camera.sensor_height_px,
        "focal_length_mm": setup.optics.focal_length_mm,
        "aperture_mm": setup.optics.aperture_mm,
        "focal_ratio": setup.optics.focal_ratio,
    }

    SetupCalculator.compute(setup)

    assert {
        "pixel_size_um": setup.camera.pixel_size_um,
        "sensor_width_px": setup.camera.sensor_width_px,
        "sensor_height_px": setup.camera.sensor_height_px,
        "focal_length_mm": setup.optics.focal_length_mm,
        "aperture_mm": setup.optics.aperture_mm,
        "focal_ratio": setup.optics.focal_ratio,
    } == original


def test_setup_capabilities_are_immutable(frozen_equipment):
    capabilities = SetupCalculator.compute(frozen_equipment.setup)

    with pytest.raises(FrozenInstanceError):
        capabilities.focal_ratio = 4.0


def test_setup_capabilities_optional_fields_default_to_none():
    capabilities = SetupCapabilities(sampling_arcsec_per_pixel=1.5)

    assert capabilities.field_width_deg is None
    assert capabilities.field_height_deg is None
    assert capabilities.limiting_resolution_arcsec is None
    assert capabilities.field_diagonal_deg is None
    assert capabilities.focal_ratio is None
    assert capabilities.collecting_area_mm2 is None
    assert capabilities.relative_speed is None
