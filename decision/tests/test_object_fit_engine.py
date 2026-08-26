from types import SimpleNamespace

import pytest

from decision.engines.object_fit_engine import ObjectFitEngine


def evaluate_target(monkeypatch, *, name, angular_size_arcmin):
    capabilities = SimpleNamespace(
        field_width_deg=3.0,
        field_height_deg=2.0,
    )
    monkeypatch.setattr(
        "decision.engines.object_fit_engine.SetupCalculator.compute",
        lambda setup: capabilities,
    )
    context = SimpleNamespace(
        sky=SimpleNamespace(
            target=SimpleNamespace(
                name=name,
                angular_size_arcmin=angular_size_arcmin,
            )
        ),
        equipment=SimpleNamespace(setup=object()),
    )

    return ObjectFitEngine.evaluate(context)


def test_ic1396_samyang135_has_excellent_framing(monkeypatch):
    result = evaluate_target(
        monkeypatch,
        name="IC1396",
        angular_size_arcmin=60,
    )

    assert result.score == 100
    assert result.explanation == "Excellent framing for this setup."
    assert result.metrics == {
        "target_name": "IC1396",
        "object_size_deg": 1.0,
        "field_width_deg": 3.0,
        "field_height_deg": 2.0,
        "occupation": 0.5,
        "occupation_percent": 50.0,
    }


def test_m31_samyang135_overflows_the_field(monkeypatch):
    result = evaluate_target(
        monkeypatch,
        name="M31",
        angular_size_arcmin=150,
    )

    assert result.score == 5
    assert result.explanation == (
        "Target is larger than the available field of view."
    )
    assert result.metrics["occupation"] == 1.25


def test_m57_samyang135_is_too_small_for_the_field(monkeypatch):
    result = evaluate_target(
        monkeypatch,
        name="M57",
        angular_size_arcmin=3,
    )

    assert result.score == 25
    assert result.explanation == "Target is too small for this setup."
    assert result.metrics["occupation_percent"] == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("occupation", "expected_score", "expected_summary"),
    [
        (0.10, 55, "Target is small in the field."),
        (0.20, 75, "Good but not optimal framing."),
        (0.30, 90, "Very good framing for this setup."),
        (0.45, 100, "Excellent framing for this setup."),
        (0.70, 100, "Excellent framing for this setup."),
        (0.85, 90, "Very good framing for this setup."),
        (0.95, 75, "Good but not optimal framing."),
        (1.00, 55, "Target is very tight in the field."),
    ],
)
def test_framing_boundaries_have_stable_scores_and_summaries(
    occupation,
    expected_score,
    expected_summary,
):
    assert ObjectFitEngine._compute_score(occupation) == expected_score
    assert ObjectFitEngine._build_summary(occupation) == expected_summary
