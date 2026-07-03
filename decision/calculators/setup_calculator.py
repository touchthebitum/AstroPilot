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
       
        return SetupCapabilities(
            sampling_arcsec_per_pixel=sampling,
            field_width_deg=field_width_deg,
            field_height_deg=field_height_deg,
        )