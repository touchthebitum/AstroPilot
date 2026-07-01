from dataclasses import dataclass


@dataclass
class SamplingEvaluation:
    adequacy: float
    score: float
    diagnostic: str
    suggestion: str


class SamplingModel:

    @staticmethod
    def evaluate(
        object_type: str,
        object_size_arcmin: float,
        seeing_arcsec: float | None,
        sampling_arcsec_pixel: float | None,
    ) -> SamplingEvaluation:

        return SamplingEvaluation(
            adequacy=75.0,
            score=4.0,
            diagnostic="Test OK",
            suggestion="Le modèle fonctionne.",
        )
    
if __name__ == "__main__":

    result = SamplingModel.evaluate(
        object_type="galaxy",
        object_size_arcmin=12,
        seeing_arcsec=1.5,
        sampling_arcsec_pixel=1.2,
    )

    print(result)