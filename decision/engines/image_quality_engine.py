from decision.models.image_quality_result import ImageQualityResult
from decision.models.sampling_model import SamplingModel
from decision.models.resolution_model import ResolutionModel


class ImageQualityEngine:

    @staticmethod
    def evaluate(context):

        sampling = SamplingModel.evaluate(
            object_name=context.get("object_name"),
            object_type=context.get("object_type"),
            object_size_arcmin=context.get("object_size_arcmin"),
            seeing_arcsec=context.get("seeing"),
            sampling_arcsec_pixel=context.get("sampling"),
        )

        resolution = ResolutionModel.evaluate(
            object_type=context.get("object_type"),
            object_size_arcmin=context.get("object_size_arcmin"),
            pixel_size=context.get("sampling"),
        )

        score = (sampling.score + resolution.score) / 2
        adequacy = (sampling.adequacy + resolution.adequacy) / 2

        return ImageQualityResult(
            score=score,
            sampling_score=sampling.score,
            resolution_score=resolution.score,
            adequacy=adequacy,
            pixels=resolution.pixels,
            size_factor=resolution.size_factor,
            ratio=0,
            detail_level="À calculer",
            limiting_factor="À calculer",
            recommendation="À calculer",
        )
