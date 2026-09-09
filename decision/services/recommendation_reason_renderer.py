from decision.models.recommendation_reason_presentation import (
    RecommendationReasonPresentation,
)
from decision.models.recommendation_reason_rendering import (
    PresentationDepth,
    RecommendationReasonRendering,
)


_RENDERINGS = {
    "selected_window_uncovered": {
        PresentationDepth.CLASSIC: (
            "La fenêtre prévue n’est pas couverte par les données météo."
        ),
        PresentationDepth.PRO: (
            "La fenêtre sélectionnée dépasse la couverture temporelle des données "
            "météo disponibles."
        ),
    },
    "selected_window_coverage_unknown": {
        PresentationDepth.CLASSIC: (
            "La couverture météo de la fenêtre prévue est inconnue."
        ),
        PresentationDepth.PRO: (
            "La couverture temporelle des données météo pour la fenêtre "
            "sélectionnée n’a pas pu être établie."
        ),
    },
    "weather_not_fresh": {
        PresentationDepth.CLASSIC: (
            "Les données météo ne sont pas assez récentes."
        ),
        PresentationDepth.PRO: (
            "La fraîcheur des données météo ne respecte pas le seuil requis pour "
            "la décision."
        ),
    },
    "provider_reliability_unavailable": {
        PresentationDepth.CLASSIC: (
            "La fiabilité historique du fournisseur météo n’est pas disponible."
        ),
        PresentationDepth.PRO: (
            "Aucune évaluation historique de fiabilité du fournisseur météo n’est "
            "disponible pour ce contexte."
        ),
    },
}


def render_recommendation_reason(
    presentation: RecommendationReasonPresentation,
    *,
    depth: PresentationDepth,
) -> RecommendationReasonRendering:
    if not isinstance(presentation, RecommendationReasonPresentation):
        raise TypeError("Expected a RecommendationReasonPresentation")
    if not isinstance(depth, PresentationDepth):
        raise TypeError("Expected PresentationDepth")
    renderings = _RENDERINGS.get(presentation.presentation_key)
    if renderings is None:
        raise ValueError("unknown_recommendation_presentation_key")
    return RecommendationReasonRendering(
        presentation_key=presentation.presentation_key,
        depth=depth,
        text=renderings[depth],
    )
