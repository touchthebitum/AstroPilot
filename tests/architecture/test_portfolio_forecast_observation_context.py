from datetime import datetime
from zoneinfo import ZoneInfo

from decision.models.future_opportunity import FutureOpportunity
from decision.portfolio.portfolio_forecast_engine import (
    PortfolioForecastEngine,
)


def test_portfolio_forecast_passes_night_context_to_future_engine():
    observation_time = datetime(
        2026,
        8,
        27,
        23,
        0,
        tzinfo=ZoneInfo("Europe/Zurich"),
    )

    projects = {
        "M31": {
            "hours": 0,
            "target_hours": 2,
        }
    }

    captured = {}

    class FakeFutureEngine:
        def estimate(
            self,
            project_name,
            remaining_hours=None,
            latitude=None,
                longitude=None,
                observation_time=None,
                profile=None,
        ):
            captured["project_name"] = project_name
            captured["remaining_hours"] = remaining_hours
            captured["latitude"] = latitude
            captured["longitude"] = longitude
            captured["observation_time"] = observation_time

            return FutureOpportunity(
                good_nights=10,
                risk="FAIBLE",
                weather_ratio=1.0,
                needed_nights=1,
                opportunity_ratio=10.0,
            )

    engine = PortfolioForecastEngine(
        future_engine=FakeFutureEngine(),
        score_project=lambda project, available_hours: 50,
        project_provider=lambda: projects,
    )

    engine.simulate_dynamic_portfolio_roadmap(
        night_capacities=[
            {
                "date": "2026-08-27",
                "hours": 2,
                "quality": 100,
                "latitude": 46.7508,
                "longitude": 6.5495,
                "observation_time": observation_time,
            }
        ]
    )

    assert captured["project_name"] == "M31"
    assert captured["remaining_hours"] == 2
    assert captured["latitude"] == 46.7508
    assert captured["longitude"] == 6.5495
    assert captured["observation_time"] == observation_time
