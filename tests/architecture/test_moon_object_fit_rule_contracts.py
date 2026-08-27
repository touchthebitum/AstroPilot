from types import SimpleNamespace

import pytest

import decision.rules.moon_rule as moon_module
import decision.rules.object_fit_rule as object_fit_module
from decision.rules.moon_rule import MoonRule
from decision.rules.object_fit_rule import ObjectFitRule


def test_moon_rule_delegates_sky_values_and_inverts_penalty(monkeypatch):
    calls = []

    def moon_penalty(self, illumination, moon_elevation, separation):
        calls.append((illumination, moon_elevation, separation))
        return 12.5

    monkeypatch.setattr(moon_module.SkyEngine, "moon_penalty", moon_penalty)
    context = SimpleNamespace(
        sky=SimpleNamespace(
            moon_illumination=68.0,
            moon_separation_deg=42.0,
        ),
    )

    contribution = MoonRule().evaluate(context, profile=object())

    assert calls == [(68.0, 0, 42.0)]
    assert contribution.rule == "Moon"
    assert contribution.score == -12.5
    assert contribution.confidence == 1.0
    assert contribution.reason == "Impact lunaire"
    assert contribution.details == "Pénalité : 12.5"


def test_object_fit_rule_returns_none_without_sky_context(monkeypatch):
    monkeypatch.setattr(
        object_fit_module.ObjectFitEngine,
        "evaluate",
        lambda context: pytest.fail("engine must not run without sky context"),
    )

    assert ObjectFitRule().evaluate(object(), profile=object()) is None


@pytest.mark.parametrize(
    ("occupation", "expected_reason"),
    [
        (
            0.0,
            "Objet assez petit pour ce setup : seulement 0 % du champ.",
        ),
        (
            24.99,
            "Objet assez petit pour ce setup : seulement 25 % du champ.",
        ),
        (25.0, "Cadrage correct : l'objet occupe 25 % du champ."),
        (49.99, "Cadrage correct : l'objet occupe 50 % du champ."),
        (50.0, "Cadrage optimal : l'objet occupe 50 % du champ."),
        (79.99, "Cadrage optimal : l'objet occupe 80 % du champ."),
        (
            80.0,
            "Le cadrage est idéal : l'objet occupe 80 % du champ.",
        ),
        (
            100.0,
            "Le cadrage est idéal : l'objet occupe 100 % du champ.",
        ),
    ],
)
def test_object_fit_rule_reason_boundaries(
    monkeypatch,
    occupation,
    expected_reason,
):
    context = SimpleNamespace(sky=object())
    calls = []
    engine_result = SimpleNamespace(
        score=80.0,
        metrics={"occupation_percent": occupation},
    )

    def evaluate(received_context):
        calls.append(received_context)
        return engine_result

    monkeypatch.setattr(
        object_fit_module.ObjectFitEngine,
        "evaluate",
        evaluate,
    )

    contribution = ObjectFitRule().evaluate(context, profile=object())

    assert calls == [context]
    assert contribution.rule == "Object Fit"
    assert contribution.score == 12.0
    assert contribution.confidence == 1.0
    assert contribution.weight == 1.0
    assert contribution.reason == expected_reason
    assert contribution.details == f"Occupation : {occupation:.1f} %"


def test_object_fit_rule_defaults_missing_occupation_to_zero(monkeypatch):
    monkeypatch.setattr(
        object_fit_module.ObjectFitEngine,
        "evaluate",
        lambda context: SimpleNamespace(score=40.0, metrics={}),
    )

    contribution = ObjectFitRule().evaluate(
        SimpleNamespace(sky=object()),
        profile=object(),
    )

    assert contribution.score == 6.0
    assert contribution.reason == (
        "Objet assez petit pour ce setup : seulement 0 % du champ."
    )
    assert contribution.details == "Occupation : 0.0 %"
