from types import SimpleNamespace
from decision.mission.mission_presenter import MissionPresenter
from decision.mission.night_mission import MissionReason


def test_expected_gain_is_printed_once(monkeypatch, capsys):
    monkeypatch.setattr(
        "decision.mission.mission_presenter.NightAdvisor.build",
        lambda mission: [],
    )
    mission = SimpleNamespace(
        target="M31",
        confidence=1.0,
        productivity=SimpleNamespace(
            astronomical_hours=2.0,
            productive_hours=1.5,
            confidence=0.75,
            windows=[],
        ),
        astro_quality=SimpleNamespace(
        score=84.5,
        confidence=1.0,
        limiting_factor="moon",
        metrics={},
        ),
        risk_report=SimpleNamespace(
            level="MEDIUM",
            score=40,
            context=SimpleNamespace(
                required_nights=4,
                productive_hours_per_night=4.0,
                night_capacity_source="profile",
            ),
            explanation=[],
            ),
        window_start=None,
        window_end=None,
        recommended_hours=2.0,
        expected_gain=10.0,
        reasons=[
            MissionReason("Bonne altitude", "success"),
            MissionReason("Très bon seeing", "success"),
        ],
        season_analysis=None,
        tasks=[],
        equipment=[],
        dew_risk=SimpleNamespace(
        dew_point_c=4.0,
        spread_c=2.0,
        risk="HIGH",
        score=45.0,
        ),
    )

    MissionPresenter.present(mission)

    output = capsys.readouterr().out

    assert "🌌 Qualité astrophotographique" in output
    assert "AQI : 84/100 — Très bonne" in output
    assert "Facteur limitant : Lune" in output
    assert "Complétude AQI : 100%" in output
    assert output.count("Gain attendu") == 1
    assert "Capacité moyenne estimée : 4.0 h/nuit (profil)" in output
    assert "Nuits nécessaires estimées : 4" in output
    assert "💧 Risque de rosée" in output
    assert "Niveau : Élevé" in output
    assert "Point de rosée : 4.0 °C" in output
    assert "Marge thermique : 2.0 °C" in output
