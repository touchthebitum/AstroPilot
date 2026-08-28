import pytest

from decision.engines.image_quality_engine import ImageQualityEngine
from decision.models.resolution_model import ResolutionEvaluation, ResolutionModel
from decision.models.sampling_model import SamplingEvaluation, SamplingModel


@pytest.mark.parametrize(
    ("seeing", "sampling"),
    [(None, 1.0), (1.0, None)],
)
def test_sampling_model_returns_unknown_when_inputs_are_missing(seeing, sampling):
    assert SamplingModel.evaluate(
        object_name="M31",
        object_type="galaxy",
        object_size_arcmin=190.0,
        seeing_arcsec=seeing,
        sampling_arcsec_pixel=sampling,
    ) == SamplingEvaluation(
        adequacy=0,
        score=0,
        diagnostic="Sampling inconnu",
        suggestion="Impossible d'évaluer le sampling.",
    )


def test_sampling_model_preserves_large_object_behavior():
    assert SamplingModel.evaluate(
        object_name="M31",
        object_type="galaxy",
        object_size_arcmin=90.0,
        seeing_arcsec=0.6,
        sampling_arcsec_pixel=1.0,
    ) == SamplingEvaluation(
        adequacy=70,
        score=2,
        diagnostic="Sampling acceptable pour grande cible",
        suggestion="Le sampling est grossier mais adapté à une grande nébuleuse.",
    )


@pytest.mark.parametrize("object_size_arcmin", [20.0, 19.9])
def test_sampling_model_preserves_medium_and_small_fallback_behavior(
    object_size_arcmin,
):
    assert SamplingModel.evaluate(
        object_name="target",
        object_type="nebula",
        object_size_arcmin=object_size_arcmin,
        seeing_arcsec=1.5,
        sampling_arcsec_pixel=1.0,
    ) == SamplingEvaluation(
        adequacy=100,
        score=8,
        diagnostic="Sampling optimal",
        suggestion="Excellent compromis entre résolution et sensibilité.",
    )


@pytest.mark.parametrize(
    ("object_size_arcmin", "pixel_size"),
    [(None, 1.0), (10.0, None)],
)
def test_resolution_model_returns_unknown_when_inputs_are_missing(
    object_size_arcmin,
    pixel_size,
):
    assert ResolutionModel.evaluate(
        object_type="galaxy",
        object_size_arcmin=object_size_arcmin,
        pixel_size=pixel_size,
    ) == ResolutionEvaluation(
        adequacy=0,
        score=0,
        diagnostic="Résolution inconnue",
        suggestion="Impossible d'évaluer.",
        pixels=0,
        size_factor="unknown",
    )


@pytest.mark.parametrize(
    ("pixels", "adequacy", "score", "diagnostic", "size_factor"),
    [
        (39.0, 10, -10, "Objet trop petit pour ce setup", "small"),
        (40.0, 40, -5, "Résolution limitée", "small"),
        (120.0, 70, 2, "Résolution correcte", "small"),
        (300.0, 90, 6, "Très bonne résolution", "small"),
        (700.0, 100, 8, "Résolution excellente", "medium"),
        (2000.0, 100, 8, "Résolution excellente", "large"),
    ],
)
def test_resolution_model_projects_pixels_and_preserves_boundaries(
    pixels,
    adequacy,
    score,
    diagnostic,
    size_factor,
):
    result = ResolutionModel.evaluate(
        object_type="galaxy",
        object_size_arcmin=pixels / 60,
        pixel_size=1.0,
    )

    assert result.pixels == pytest.approx(pixels)
    assert result.adequacy == adequacy
    assert result.score == score
    assert result.diagnostic == diagnostic
    assert result.size_factor == size_factor


@pytest.mark.parametrize(
    ("object_size_arcmin", "seeing", "expected_adequacy", "detail_level"),
    [
        (5.0, 1.5, 95.0, "Excellent"),
        (5.0, 0.75, 70.0, "Bon"),
        (1.0, 3.0, 50.0, "Moyen"),
        (1.0, 0.4, 30.0, "Faible"),
    ],
)
def test_image_quality_detail_level_uses_percentage_adequacy_scale(
    object_size_arcmin,
    seeing,
    expected_adequacy,
    detail_level,
):
    result = ImageQualityEngine.evaluate(
        {
            "object_name": "target",
            "object_type": "galaxy",
            "object_size_arcmin": object_size_arcmin,
            "seeing": seeing,
            "sampling": 1.0,
        }
    )

    assert result.metrics["adequacy"] == expected_adequacy
    assert result.metrics["detail_level"] == detail_level
