from __future__ import annotations

from dataclasses import dataclass

from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


@dataclass(frozen=True)
class ForecastRun:
    nights: tuple[dict, ...]
    evidence: DecisionForecastEvidence | None

    def __post_init__(self):
        object.__setattr__(self, "nights", tuple(self.nights))
