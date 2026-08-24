from datetime import timedelta
from types import SimpleNamespace

import pytest

from decision.mission.mission_assembler import MissionAssembler


class ContextCaptured(Exception):
    pass


def test_mission_assembler_uses_selected_night_conditions(
    monkeypatch,
    frozen_time,
    buttes_site,
    frozen_weather,
    frozen_equipment,
    frozen_portfolio,
):
    context = SimpleNamespace(
        site=buttes_site,
        session=SimpleNamespace(
            start_time=frozen_time,
            end_time=frozen_time + timedelta(hours=2),
        ),
        equipment=frozen_equipment,
        portfolio=frozen_portfolio,
    )
    summary = SimpleNamespace(
        positives=[],
        negatives=[],
        confidence=1.0,
    )

    def capture(productivity_context):
        assert productivity_context.astronomical_hours == 2.0
        assert productivity_context.cloud_cover == 73.0
        assert productivity_context.humidity == 91.0
        assert productivity_context.wind == 27.0
        assert productivity_context.seeing == 3.2
        assert productivity_context.moon_penalty == 0.85
        raise ContextCaptured

    monkeypatch.setattr(
        "decision.mission.mission_assembler."
        "NightProductivityEngine.evaluate",
        capture,
    )

    with pytest.raises(ContextCaptured):
        MissionAssembler.build(
            target="M31",
            summary=summary,
            context=context,
            equipment=["frozen setup"],
            alternatives=["M42"],
            weather=frozen_weather,
        )

