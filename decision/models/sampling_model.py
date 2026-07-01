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
        
        if sampling_arcsec_pixel is None or seeing_arcsec is None:
            return SamplingEvaluation(
                adequacy=0,
                score=0,
                diagnostic="Sampling inconnu",
                suggestion="Impossible d'évaluer le sampling."
            )

        ratio = seeing_arcsec / sampling_arcsec_pixel

        # Score de base
        score = 0
        diagnostic = ""
        suggestion = ""

        # Taille de l'objet
        if object_size_arcmin >= 90:
            size_factor = "large"
        elif object_size_arcmin >= 20:
            size_factor = "medium"
        else:
            size_factor = "small"

        print(f"DEBUG Sampling ratio : {ratio:.2f}")

        if ratio < 0.5:
            adequacy = 20
            score = -6
            diagnostic = "Sous-échantillonnage important"
            suggestion = "Le seeing est nettement meilleur que la résolution de votre setup."

        elif ratio < 1.0:
            adequacy = 50
            score = -2
            diagnostic = "Sous-échantillonnage modéré"
            suggestion = "Le setup perd une partie des détails."

        elif ratio < 2.0:
            adequacy = 100
            score = 8
            diagnostic = "Sampling optimal"
            suggestion = "Excellent compromis entre résolution et sensibilité."

        elif ratio < 3.0:
            adequacy = 85
            score = 4
            diagnostic = "Léger sur-échantillonnage"
            suggestion = "Résolution élevée, mais au prix d'une baisse de SNR."

        else:
            adequacy = 60
            score = -4
            diagnostic = "Sur-échantillonnage important"
            suggestion = "Le seeing ne permet pas d'exploiter cette résolution."

        return SamplingEvaluation(
            adequacy=adequacy,
            score=score,
            diagnostic=diagnostic,
            suggestion=suggestion,
        )
