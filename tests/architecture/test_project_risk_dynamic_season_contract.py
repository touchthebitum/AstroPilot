from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from decision.models.context.decision_context import DecisionContext
from decision.models.context.equipment_context import EquipmentContext
from decision.models.context.portfolio_context import PortfolioContext
from decision.models.context.preferences_context import PreferencesContext
from decision.models.context.session_context import SessionContext
from decision.models.context.site_context import SiteContext
from decision.models.context.sky_context import SkyContext
from decision.models.context.weather_context import WeatherContext
from decision.risk.project_risk_context_builder import (
    ProjectRiskContextBuilder,
)


def test_project_risk_uses_dynamic_season():
    start = datetime(
        2026,
        8,
        21,
        23,
        0,
        tzinfo=ZoneInfo("Europe/Zurich"),
    )

    context = DecisionContext(
        session=SessionContext(
            start_time=start,
            end_time=start + timedelta(hours=2),
            available_duration=timedelta(hours=2),
        ),
        site=SiteContext(
            name="Buttes",
            latitude=46.7508,
            longitude=6.5495,
            elevation=700,
            bortle=3,
        ),
        equipment=EquipmentContext(
            setup=None,
        ),
        weather=WeatherContext(
            cloud_cover=0,
            humidity=50,
            wind_speed_kmh=0,
            seeing_arcsec=1.5,
        ),
        sky=SkyContext(
            target="IC1396",
            moon_illumination=0,
            moon_separation_deg=180,
            target_altitude_deg=60,
            astronomical_darkness=True,
        ),
        portfolio=PortfolioContext(
            active_projects=1,
            total_remaining_hours=15,
            highest_priority=80,
            average_progress=0,
        ),
        preferences=PreferencesContext(
            astro_weight=0.7,
            project_weight=0.3,
            minimum_altitude_deg=30,
            minimum_sqm=20,
        ),
    )
    result = ProjectRiskContextBuilder.build(
        target="IC1396",
        context=context,
    )

    assert result.season_remaining_days is not None
    assert result.favorable_nights is not None
    assert result.favorable_nights > 0
    assert result.pressure > 0
