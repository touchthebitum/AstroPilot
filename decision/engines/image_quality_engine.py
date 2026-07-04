from decision.models.results.engine_result import EngineResult
from decision.models.sampling_model import SamplingModel
from decision.models.resolution_model import ResolutionModel
from decision.calculators.setup_calculator import SetupCalculator


class ImageQualityEngine:

    @staticmethod
    def evaluate(context):

        if hasattr(context, "sky"):
            target = context.sky.target
            weather = context.weather
            setup = context.equipment.setup
            sampling_value = SetupCalculator.compute_sampling(setup)

            object_name = target.name
            object_type = target.object_type
            object_size_arcmin = target.angular_size_arcmin
            seeing = weather.seeing_arcsec

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

        sampling_score = sampling.score
        resolution_score = resolution.score

        seeing_match = 10 if abs(sampling.score - resolution.score) <= 2 else 7

        score = (
            sampling_score * 0.40 +
            resolution_score * 0.40 +
            seeing_match * 0.20
        )
        adequacy = (sampling.adequacy + resolution.adequacy) / 2

        return EngineResult(
            score=score,
            confidence=1.0,

            explanation=f"Qualité d'image globale : {score:.1f}/10.",

            recommendation=(
                "Excellente qualité d'image."
                if score >= 8 else
                "Bonne qualité d'image."
                if score >= 6 else
                "Qualité d'image moyenne."
                if score >= 4 else
                "Qualité d'image insuffisante."
            ),

            limiting_factor=(
                "Sampling"
                if sampling.score < resolution.score
                else "Résolution"
            ),

            metrics={
                "sampling_score": sampling.score,
                "resolution_score": resolution.score,
                "adequacy": adequacy,
                "pixels": resolution.pixels,
                "size_factor": resolution.size_factor,
                "ratio": adequacy,
                "seeing_match" : seeing_match,
                "detail_level": (
                    "Excellent"
                    if adequacy >= 0.9 else
                    "Bon"
                    if adequacy >= 0.7 else
                    "Moyen"
                    if adequacy >= 0.5 else
                    "Faible"
                ),
            },
        )
