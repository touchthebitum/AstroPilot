from types import SimpleNamespace

import pytest

import decision.rules.image_quality_rule as image_module
import decision.rules.resolution_rule as resolution_module
import decision.rules.sampling_rule as sampling_module
from decision.rules.image_quality_rule import ImageQualityRule
from decision.rules.resolution_rule import ResolutionRule
from decision.rules.sampling_rule import SamplingRule


def _context():
    return SimpleNamespace(
        equipment=SimpleNamespace(setup=object()),
        sky=SimpleNamespace(
            target=SimpleNamespace(
                name="M31",
                object_type="galaxy",
                angular_size_arcmin=190.0,
            ),
        ),
        weather=SimpleNamespace(seeing_arcsec=1.7),
    )


def test_image_quality_rule_preserves_engine_result(monkeypatch):
    context = _context()
    calls = []
    result = SimpleNamespace(
        score=7.25,
        recommendation="Use shorter exposures",
    )

    def evaluate(received_context):
        calls.append(received_context)
        return result

    monkeypatch.setattr(
        image_module.ImageQualityEngine,
        "evaluate",
        evaluate,
    )

    contribution = ImageQualityRule().evaluate(context, profile=object())

    assert calls == [context]
    assert contribution.rule == "ImageQuality"
    assert contribution.score == 7.25
    assert contribution.confidence == 1.0
    assert contribution.reason == "Qualité image : 7.2"
    assert contribution.details == "Use shorter exposures"


@pytest.mark.parametrize(
    ("score", "expected_reason"),
    [
        (8.0, "Résolution excellente (Objet projeté sur 320 px)"),
        (7.99, "Bonne résolution (Objet projeté sur 320 px)"),
        (5.0, "Bonne résolution (Objet projeté sur 320 px)"),
        (4.99, "Résolution correcte (Objet projeté sur 320 px)"),
        (0.01, "Résolution correcte (Objet projeté sur 320 px)"),
        (0.0, "Résolution insuffisante (Objet projeté sur 320 px)"),
        (-1.0, "Résolution insuffisante (Objet projeté sur 320 px)"),
    ],
)
def test_resolution_rule_score_categories(monkeypatch, score, expected_reason):
    context = _context()
    capabilities = SimpleNamespace(sampling_arcsec_per_pixel=1.23)
    setup_calls = []
    model_calls = []

    monkeypatch.setattr(
        resolution_module.SetupCalculator,
        "compute",
        lambda setup: setup_calls.append(setup) or capabilities,
    )

    def evaluate_resolution(**kwargs):
        model_calls.append(kwargs)
        return SimpleNamespace(score=score, pixels=320.0)

    monkeypatch.setattr(
        resolution_module.ResolutionModel,
        "evaluate",
        evaluate_resolution,
    )

    contribution = ResolutionRule().evaluate(context, profile=object())

    assert setup_calls == [context.equipment.setup]
    assert model_calls == [
        {
            "object_type": "galaxy",
            "object_size_arcmin": 190.0,
            "pixel_size": 1.23,
        }
    ]
    assert contribution.rule == "Resolution"
    assert contribution.score == score
    assert contribution.confidence == 1.0
    assert contribution.reason == expected_reason
    assert contribution.details == ""


def test_sampling_rule_returns_low_confidence_when_sampling_is_missing(
    monkeypatch,
):
    context = _context()
    monkeypatch.setattr(
        sampling_module.SetupCalculator,
        "compute",
        lambda setup: SimpleNamespace(sampling_arcsec_per_pixel=None),
    )
    monkeypatch.setattr(
        sampling_module.ResolutionModel,
        "evaluate",
        lambda **kwargs: pytest.fail("resolution must not run"),
    )
    monkeypatch.setattr(
        sampling_module.SamplingModel,
        "evaluate",
        lambda **kwargs: pytest.fail("sampling model must not run"),
    )

    contribution = SamplingRule().evaluate(context, profile=object())

    assert contribution.rule == "Sampling"
    assert contribution.score == 0
    assert contribution.confidence == 0.5
    assert contribution.reason == "Sampling indisponible"
    assert contribution.details == ""


def test_sampling_rule_delegates_setup_target_and_weather_values(monkeypatch):
    context = _context()
    calls = {}
    capabilities = SimpleNamespace(sampling_arcsec_per_pixel=1.234)
    evaluation = SimpleNamespace(
        score=9.0,
        diagnostic="Sampling adapté",
    )

    monkeypatch.setattr(
        sampling_module.SetupCalculator,
        "compute",
        lambda setup: capabilities,
    )

    def evaluate_resolution(**kwargs):
        calls["resolution"] = kwargs
        return SimpleNamespace()

    def evaluate_sampling(**kwargs):
        calls["sampling"] = kwargs
        return evaluation

    monkeypatch.setattr(
        sampling_module.ResolutionModel,
        "evaluate",
        evaluate_resolution,
    )
    monkeypatch.setattr(
        sampling_module.SamplingModel,
        "evaluate",
        evaluate_sampling,
    )

    contribution = SamplingRule().evaluate(context, profile=object())

    assert calls["resolution"] == {
        "object_type": "galaxy",
        "object_size_arcmin": 190.0,
        "pixel_size": 1.234,
    }
    assert calls["sampling"] == {
        "object_type": "galaxy",
        "object_size_arcmin": 190.0,
        "seeing_arcsec": 1.7,
        "sampling_arcsec_pixel": 1.234,
        "object_name": "M31",
    }
    assert contribution.rule == "Sampling"
    assert contribution.score == 9.0
    assert contribution.confidence == 1.0
    assert contribution.reason == 'Sampling adapté (1.23"/px)'
    assert contribution.details == ""
