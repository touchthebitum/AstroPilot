from dataclasses import dataclass


@dataclass
class ResolutionEvaluation:
    adequacy: int
    score: float
    diagnostic: str
    suggestion: str
    pixels: float
    size_factor : str


class ResolutionModel:

    @staticmethod
    def evaluate(
        object_type,
        object_size_arcmin,
        pixel_size,
    ):

        # Protection
        if object_size_arcmin is None or pixel_size is None:
            return ResolutionEvaluation(
                adequacy=0,
                score=0,
                diagnostic="Résolution inconnue",
                suggestion="Impossible d'évaluer.",
                pixels=0,
                size_factor="unknown",
            )

        pixels = object_size_arcmin * 60 / pixel_size

        if pixels < 500:
            size_factor = "small"
        elif pixels < 2000:
            size_factor = "medium"
        else:
            size_factor = "large"

        if pixels < 40:
            adequacy = 10
            score = -10
            diagnostic = "Objet trop petit pour ce setup"
            suggestion = "La cible couvrira trop peu de pixels pour révéler des détails."

        elif pixels < 120:
            adequacy = 40
            score = -5
            diagnostic = "Résolution limitée"
            suggestion = "La cible sera exploitable, mais avec peu de détails."

        elif pixels < 300:
            adequacy = 70
            score = 2
            diagnostic = "Résolution correcte"
            suggestion = "Le setup permet une résolution acceptable de cette cible."

        elif pixels < 700:
            adequacy = 90
            score = 6
            diagnostic = "Très bonne résolution"
            suggestion = "Le setup permet de bien détailler cette cible."

        else:
            adequacy = 100
            score = 8
            diagnostic = "Résolution excellente"
            suggestion = "La cible est très bien adaptée à ce setup."


        return ResolutionEvaluation(
            adequacy=adequacy,
            score=score,
            diagnostic=diagnostic,
            suggestion=suggestion,
            pixels=pixels,
            size_factor=size_factor,
        )
