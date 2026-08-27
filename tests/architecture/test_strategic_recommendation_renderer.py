import pytest

from decision.models.future_opportunity import FutureOpportunity
from decision.renderer.recommendation_renderer import (
    render_opportunity_cost,
    render_strategic_summary,
)


def _future(*, good_nights, weather_ratio):
    return FutureOpportunity(
        good_nights=good_nights,
        risk="MEDIUM",
        weather_ratio=weather_ratio,
        needed_nights=2,
        opportunity_ratio=0.5,
    )


def test_opportunity_cost_stops_after_shared_best_choice(capsys):
    render_opportunity_cost(
        best_score={"name": "M31"},
        best_roi={"name": "M31"},
        session_hours=2.0,
        remaining_best=1.5,
        remaining_roi=1.5,
        gain_score=8.0,
        gain_roi=8.0,
        same_choice=True,
    )

    output = capsys.readouterr().out

    assert "===== COÛT D'OPPORTUNITÉ =====" in output
    assert output.count("Si vous photographiez M31") == 1
    assert "+8.0% portefeuille" in output
    assert "Projet terminé" in output
    assert "ROI 4.00/h" in output


def test_opportunity_cost_compares_remaining_time_and_completion(capsys):
    render_opportunity_cost(
        best_score={"name": "M31"},
        best_roi={"name": "M42"},
        session_hours=2.0,
        remaining_best=5.5,
        remaining_roi=2.0,
        gain_score=9.0,
        gain_roi=12.0,
        same_choice=False,
    )

    output = capsys.readouterr().out

    assert "Si vous photographiez M31" in output
    assert "Reste après session : 3.5 h" in output
    assert "ROI 4.50/h" in output
    assert "Si vous photographiez M42" in output
    assert output.count("Projet terminé") == 1
    assert "ROI 6.00/h" in output


def test_strategic_summary_renders_both_choices_and_closure_bonus(capsys):
    render_strategic_summary(
        best_score={"name": "M31", "closure_bonus": 12},
        best_roi={"name": "M42"},
        same_choice=False,
        chosen_future=_future(good_nights=4, weather_ratio=0.65),
        alt_future=_future(good_nights=2, weather_ratio=0.4),
        chosen_risk="LOW",
        alt_risk="HIGH",
        progress=72.5,
        remaining=3.5,
        confidence="ÉLEVÉE",
        score_gap=30.0,
    )

    output = capsys.readouterr().out

    assert "📌 M31 : risque LOW, fenêtres favorables estimées : 4" in output
    assert "📌 M42 : risque HIGH, fenêtres favorables estimées : 2" in output
    assert "✓ Progression actuelle : 72.5%" in output
    assert "✓ Temps restant : 3.5 h" in output
    assert "✓ Bonus clôture disponible : +12" in output
    assert "Taux météo utilisé : 65%" in output
    assert "Choisir M31" in output
    assert "Confiance : ÉLEVÉE" in output
    assert "Raison : avantage score de 30.0 points" in output


@pytest.mark.parametrize(
    ("score_gap", "expected_reason"),
    [
        (29.99, "Raison : avantage score modéré de 30.0 points"),
        (10.0, "Raison : avantage score modéré de 10.0 points"),
        (9.99, "Raison : décision serrée, plusieurs choix valables"),
    ],
)
def test_strategic_summary_score_gap_boundaries(
    capsys,
    score_gap,
    expected_reason,
):
    render_strategic_summary(
        best_score={"name": "M31"},
        best_roi={"name": "M31"},
        same_choice=True,
        chosen_future=_future(good_nights=3, weather_ratio=0.5),
        alt_future=_future(good_nights=1, weather_ratio=0.25),
        chosen_risk="MEDIUM",
        alt_risk="HIGH",
        progress=20.0,
        remaining=None,
        confidence="MOYENNE",
        score_gap=score_gap,
    )

    output = capsys.readouterr().out

    assert output.count("📌") == 1
    assert "✓ Temps restant : inconnu" in output
    assert "Bonus clôture" not in output
    assert expected_reason in output
