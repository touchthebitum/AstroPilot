from dataclasses import dataclass

from decision.models.context.session_context import SessionContext
from decision.models.context.site_context import SiteContext
from decision.models.context.equipment_context import EquipmentContext
from decision.models.context.weather_context import WeatherContext
from decision.models.context.sky_context import SkyContext
from decision.models.context.portfolio_context import PortfolioContext
from decision.models.context.preferences_context import PreferencesContext


@dataclass(frozen=True)
class DecisionContext:
    """
    Complete immutable context available to AstroPilot engines
    when evaluating a decision.
    """

    session: SessionContext
    site: SiteContext
    equipment: EquipmentContext
    weather: WeatherContext
    sky: SkyContext
    portfolio: PortfolioContext
    preferences: PreferencesContext
