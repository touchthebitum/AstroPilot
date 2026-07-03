from decision.models.equipment.setup_capabilities import SetupCapabilities


class SetupCalculator:
    """
    Computes physical properties derived from an imaging setup.
    """

    @staticmethod
    def compute_sampling(setup) -> float:
        return 206.265 * setup.camera.pixel_size_um / setup.optics.focal_length_mm

    @staticmethod
    def compute(setup) -> SetupCapabilities:
        sampling = SetupCalculator.compute_sampling(setup)

        field_width_deg = (
            setup.camera.sensor_width_px
            * setup.camera.pixel_size_um
            / 1000
            / setup.optics.focal_length_mm
        ) * 57.2958

        field_height_deg = (
            setup.camera.sensor_height_px
            * setup.camera.pixel_size_um
            / 1000
            / setup.optics.focal_length_mm
        ) * 57.2958

        field_diagonal_deg = (field_width_deg ** 2 + field_height_deg ** 2) ** 0.5

        focal_ratio = setup.optics.focal_ratio

        collecting_area_mm2 = 3.141592653589793 * (setup.optics.aperture_mm / 2) ** 2

        relative_speed = 1 / (focal_ratio ** 2)

        return SetupCapabilities(
            sampling_arcsec_per_pixel=sampling,
            field_width_deg=field_width_deg,
            field_height_deg=field_height_deg,
            field_diagonal_deg=field_diagonal_deg,
            focal_ratio=focal_ratio,
            collecting_area_mm2=collecting_area_mm2,
            relative_speed=relative_speed
        )