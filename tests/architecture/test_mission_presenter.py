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
        risk_report=None,
        window_start=None,
        window_end=None,
        recommended_hours=2.0,
        expected_gain=10.0,
        alternative_target=None,
        reasons=[
            MissionReason("Bonne altitude", "success"),
            MissionReason("Très bon seeing", "success"),
        ],
        season_analysis=None,
        tasks=[],
        equipment=[],
        timeline=[],
    )

    MissionPresenter.present(mission)

    assert capsys.readouterr().out.count("Gain attendu") == 1
