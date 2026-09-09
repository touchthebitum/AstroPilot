from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.recommendation_reason import (
    RecommendationReason,
    RecommendationReasonScope,
)
from decision.models.recommendation_reason_presentation import (
    RecommendationReasonPresentation,
)
from decision.services.recommendation_reason_presentation import (
    recommendation_reason_presentation,
)


EXPECTED_RENDERINGS = {
    "selected_window_uncovered": {
        "classic": "La fenêtre prévue n’est pas couverte par les données météo.",
        "pro": (
            "La fenêtre sélectionnée dépasse la couverture temporelle des données "
            "météo disponibles."
        ),
    },
    "selected_window_coverage_unknown": {
        "classic": "La couverture météo de la fenêtre prévue est inconnue.",
        "pro": (
            "La couverture temporelle des données météo pour la fenêtre "
            "sélectionnée n’a pas pu être établie."
        ),
    },
    "weather_not_fresh": {
        "classic": "Les données météo ne sont pas assez récentes.",
        "pro": (
            "La fraîcheur des données météo ne respecte pas le seuil requis pour "
            "la décision."
        ),
    },
    "provider_reliability_unavailable": {
        "classic": (
            "La fiabilité historique du fournisseur météo n’est pas disponible."
        ),
        "pro": (
            "Aucune évaluation historique de fiabilité du fournisseur météo n’est "
            "disponible pour ce contexte."
        ),
    },
}


def test_rendering_contract_and_depth_have_exact_immutable_shape():
    from decision.models.recommendation_reason_rendering import (
        PresentationDepth,
        RecommendationReasonRendering,
    )

    assert {depth.value for depth in PresentationDepth} == {"classic", "pro"}
    rendering = RecommendationReasonRendering(
        presentation_key="weather_not_fresh",
        depth=PresentationDepth.CLASSIC,
        text="Les données météo ne sont pas assez récentes.",
    )
    assert [field.name for field in fields(rendering)] == [
        "presentation_key",
        "depth",
        "text",
    ]
    with pytest.raises(FrozenInstanceError):
        rendering.text = "changed"


@pytest.mark.parametrize("presentation_key", EXPECTED_RENDERINGS)
@pytest.mark.parametrize("depth_value", ["classic", "pro"])
def test_verified_keys_render_in_french_at_the_requested_depth(
    presentation_key,
    depth_value,
):
    from decision.models.recommendation_reason_rendering import PresentationDepth
    from decision.services.recommendation_reason_renderer import (
        render_recommendation_reason,
    )

    depth = PresentationDepth(depth_value)
    presentation = RecommendationReasonPresentation(
        basis=presentation_key,
        presentation_key=presentation_key,
    )
    rendering = render_recommendation_reason(presentation, depth=depth)

    assert rendering.presentation_key == presentation_key
    assert rendering.depth is depth
    assert rendering.text == EXPECTED_RENDERINGS[presentation_key][depth_value]
    assert presentation.presentation_key == presentation_key


@pytest.mark.parametrize("presentation_key", EXPECTED_RENDERINGS)
def test_classic_and_pro_share_one_presentation_key(presentation_key):
    from decision.models.recommendation_reason_rendering import PresentationDepth
    from decision.services.recommendation_reason_renderer import (
        render_recommendation_reason,
    )

    presentation = RecommendationReasonPresentation(
        basis=presentation_key,
        presentation_key=presentation_key,
    )
    classic = render_recommendation_reason(
        presentation,
        depth=PresentationDepth.CLASSIC,
    )
    pro = render_recommendation_reason(
        presentation,
        depth=PresentationDepth.PRO,
    )

    assert classic.presentation_key == pro.presentation_key == presentation_key
    assert classic.text != pro.text


@pytest.mark.parametrize(
    "presentation_key",
    [
        "unknown_key",
        "weather_not_fresh.classic",
        "weather_not_fresh.pro",
        "Weather_Not_Fresh",
        " weather_not_fresh ",
        "",
    ],
)
def test_unknown_or_depth_specific_keys_fail_explicitly(presentation_key):
    from decision.models.recommendation_reason_rendering import PresentationDepth
    from decision.services.recommendation_reason_renderer import (
        render_recommendation_reason,
    )

    presentation = RecommendationReasonPresentation(
        basis=presentation_key,
        presentation_key=presentation_key,
    )
    with pytest.raises(ValueError, match="unknown_recommendation_presentation_key"):
        render_recommendation_reason(
            presentation,
            depth=PresentationDepth.CLASSIC,
        )


def test_legacy_reason_is_not_mapped_or_rendered_automatically():
    from decision.models.recommendation_reason_rendering import PresentationDepth
    from decision.services.recommendation_reason_renderer import (
        render_recommendation_reason,
    )

    legacy = RecommendationReason(
        scope=RecommendationReasonScope.TARGET,
        basis=None,
        message="weather_not_fresh",
    )
    presentation = recommendation_reason_presentation(legacy)

    assert presentation is None
    with pytest.raises(TypeError):
        render_recommendation_reason(
            presentation,
            depth=PresentationDepth.CLASSIC,
        )


def test_renderer_requires_the_existing_presentation_contract_and_depth():
    from decision.models.recommendation_reason_rendering import PresentationDepth
    from decision.services.recommendation_reason_renderer import (
        render_recommendation_reason,
    )

    presentation = RecommendationReasonPresentation(
        basis="weather_not_fresh",
        presentation_key="weather_not_fresh",
    )
    with pytest.raises(TypeError):
        render_recommendation_reason("weather_not_fresh", depth=PresentationDepth.PRO)
    with pytest.raises(TypeError):
        render_recommendation_reason(presentation, depth="pro")
