from decision.models.results.engine_result import EngineResult
from decision.models.sampling_model import SamplingModel
from decision.models.resolution_model import ResolutionModel


class ImageQualityEngine:

    @staticmethod
    def evaluate(context):

        if hasattr(context, "sky"):
            target = context.sky.target
            weather = context.weather

            object_name = target.name
            object_type = target.object_type
            object_size_arcmin = target.angular_size_arcmin
            seeing = weather.seeing_arcsec
            sampling_value = None

        else:
            object_name = context.get("object_name")
            object_type = context.get("object_type")
            object_size_arcmin = context.get("object_size_arcmin")
            seeing = context.get("seeing")
            sampling_value = context.get("sampling")


            sampling = SamplingModel.evaluate(
                object_name=object_name,
                object_type=object_type,
                object_size_arcmin=object_size_arcmin,
                seeing_arcsec=seeing,
                sampling_arcsec_pixel=sampling_value,
            )

            resolution = ResolutionModel.evaluate(
                object_type=object_type,
                object_size_arcmin=object_size_arcmin,
                pixel_size=sampling_value,
            )

            score = (sampling.score + resolution.score) / 2
            adequacy = (sampling.adequacy + resolution.adequacy) / 2

        return EngineResult(
            score=score,
            confidence=1.0,
            explanation="Image quality evaluated from sampling and resolution.",
            recommendation="À calculer",
            limiting_factor="À calculer",
            metrics={
                "sampling_score": sampling.score,
                "resolution_score": resolution.score,
                "adequacy": adequacy,
                "pixels": resolution.pixels,
                "size_factor": resolution.size_factor,
                "ratio": 0,
                "detail_level": "À calculer",
            },
        )
