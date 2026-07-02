class SetupCalculator:
    """
    Computes physical properties derived from an imaging setup.
    """

    @staticmethod
    def compute_sampling(setup) -> float:
        """
        Computes image scale in arcsec/pixel.

        Formula:
        sampling = 206.265 * pixel_size_um / focal_length_mm
        """

        return 206.265 * setup.camera.pixel_size_um / setup.optics.focal_length_mm