from dataclasses import dataclass

@dataclass
class SamplingEvaluation:
    adequacy: float
    score: float
    diagnostic: str
    suggestion: str

class SamplingModel:

    @staticmethod
    def evaluate_large_object(ratio):
        if ratio < 0.3:
            return SamplingEvaluation(
                adequacy=30,
                score=-4,
                diagnostic="Sous-échantillonnage marqué",
                suggestion="Objet très large : le setup reste exploitable malgré une résolution limitée.",
            )

        elif ratio < 0.7:
            return SamplingEvaluation(
                adequacy=70,
                score=2,
                diagnostic="Sampling acceptable pour grande cible",
                suggestion="Le sampling est grossier mais adapté à une grande nébuleuse.",
            )

        else:
            return SamplingEvaluation(
                adequacy=90,
                score=5,
                diagnostic="Sampling adapté aux grandes cibles",
                suggestion="Bon choix pour les grandes nébuleuses.",
            )


    @staticmethod
    def evaluate_medium_object(ratio):
        pass

    @staticmethod
    def evaluate_small_object(ratio):
        pass

    @staticmethod
    def evaluate(
        object_name: str | None,
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

        object_size_pixels = (object_size_arcmin * 60) / sampling_arcsec_pixel

        if object_size_arcmin >= 90:
            return SamplingModel.evaluate_large_object(ratio)

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

        if size_factor == "large":

            if ratio < 0.3:
                adequacy = 30
                score = -4
                diagnostic = "Sous-échantillonnage marqué"
                suggestion = "Objet très large : le setup reste exploitable malgré une résolution limitée."

            elif ratio < 0.7:
                adequacy = 70
                score = 2
                diagnostic = "Sampling acceptable pour grande cible"
                suggestion = "Le sampling est grossier mais adapté à une grande nébuleuse."

            else:
                adequacy = 90
                score = 5
                diagnostic = "Sampling adapté aux grandes cibles"
                suggestion = "Bon choix pour les grandes nébuleuses."

        else:
            # ancienne logique provisoire
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
