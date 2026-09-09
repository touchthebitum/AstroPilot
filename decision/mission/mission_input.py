from dataclasses import dataclass
from datetime import datetime
from decision.filtering.selected_filter import SelectedFilter
from decision.models.session_availability import SessionAvailability
from decision.weather.weather_forecast import WeatherForecast


@dataclass(frozen=True)
class MissionInput:
    window_start: datetime | None
    window_end: datetime | None
    astronomical_hours: float | None
    weather: WeatherForecast | None
    moon_penalty: float | None
    recommended_hours: float
    expected_gain: float
    selected_filter: SelectedFilter | None = None
    availability: SessionAvailability | None = None
    mission_id: str | None = None
    decision_id: str | None = None
    selection_id: str | None = None

    def __post_init__(self):
        provenance = (self.mission_id, self.decision_id, self.selection_id)
        if any(value is not None for value in provenance) and any(
            not isinstance(value, str) or not value.strip()
            for value in provenance
        ):
            raise ValueError("mission_provenance_required")
