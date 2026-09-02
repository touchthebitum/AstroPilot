from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from astropilot.equipment_catalog import EQUIPMENT_PROFILES
from decision.forecast.forecast_run import ForecastRun
from decision.mission.night_mission import NightMission
from decision.recommendation.recommendation import Recommendation
from decision.validation.decision_consistency import DecisionConsistencyGate
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


class TonightStatus(str, Enum):
    AVAILABLE = "available"
    FORECAST_UNAVAILABLE = "forecast_unavailable"
    NO_NIGHT = "no_night"
    NO_CANDIDATE = "no_candidate"
    NO_RECOMMENDATION = "no_recommendation"
    NO_MISSION = "no_mission"
    NO_PRODUCTIVE_WINDOW = "no_productive_window"


class TonightEquipmentSelectionError(ValueError):
    code = "invalid_tonight_equipment"


def resolve_tonight_equipment(profile, requested_equipment) -> str:
    selected_equipment = (
        requested_equipment
        if requested_equipment is not None
        else profile.get("active_equipment")
    )
    available_equipment = profile.get("available_equipment")

    if (
        not isinstance(selected_equipment, str)
        or selected_equipment not in EQUIPMENT_PROFILES
        or not isinstance(available_equipment, list)
        or selected_equipment not in available_equipment
    ):
        raise TonightEquipmentSelectionError("invalid_tonight_equipment")

    return selected_equipment


@dataclass(frozen=True)
class TonightResult:
    night: dict | None
    recommendation: Recommendation | None
    mission: NightMission | None
    status: TonightStatus = TonightStatus.AVAILABLE
    forecast_evidence: DecisionForecastEvidence | None = None
    decision_id: str | None = None

    @property
    def forecast_available(self) -> bool:
        return self.status is not TonightStatus.FORECAST_UNAVAILABLE


class TonightApplicationService:
    def __init__(
        self,
        *,
        forecast_nights,
        build_candidates,
        opportunity_recommendation_service,
        tonight_mission_service,
        build_mission_input,
    ):
        self.forecast_nights = forecast_nights
        self.build_candidates = build_candidates
        self.opportunity_recommendation_service = (
            opportunity_recommendation_service
        )
        self.tonight_mission_service = tonight_mission_service
        self.build_mission_input = build_mission_input

    def evaluate(
        self,
        *,
        profile,
        weather,
        reference_time_utc: datetime,
        equipment=None,
        goal="balanced",
        target="deep_sky",
        bortle,
    ) -> TonightResult:
        selected_equipment = resolve_tonight_equipment(profile, equipment)
        effective_profile = {
            **profile,
            "active_equipment": selected_equipment,
            "available_equipment": [selected_equipment],
        }
        location = effective_profile.get(
            "location",
            {
                "name": "Buttes",
                "latitude": 46.7508,
                "longitude": 6.5495,
            },
        )
        forecast_run: ForecastRun | None = self.forecast_nights(
            location["latitude"],
            location["longitude"],
            location["name"],
            bortle,
            target=target,
            goal=goal,
            weather=weather,
            profile=effective_profile,
            reference_time_utc=reference_time_utc,
        )

        if forecast_run is None:
            return TonightResult(
                None,
                None,
                None,
                status=TonightStatus.FORECAST_UNAVAILABLE,
            )

        nights = forecast_run.nights
        forecast_evidence = forecast_run.evidence
        if not nights:
            return TonightResult(
                None,
                None,
                None,
                status=TonightStatus.NO_NIGHT,
                forecast_evidence=forecast_evidence,
            )

        night = sorted(nights, key=lambda item: item["date"])[0]
        top_objects = night.get("top_objects") or []
        candidates = self.build_candidates(
            top_objects,
            available_hours=night.get("duration", 3.0),
            profile=effective_profile,
        )

        if not candidates:
            return TonightResult(
                night,
                None,
                None,
                status=TonightStatus.NO_CANDIDATE,
                forecast_evidence=forecast_evidence,
            )

        recommendation = self.opportunity_recommendation_service.build(
            candidates=candidates,
        )
        if recommendation is None:
            return TonightResult(
                night,
                None,
                None,
                status=TonightStatus.NO_RECOMMENDATION,
                forecast_evidence=forecast_evidence,
            )

        candidate = recommendation.opportunity.candidate
        recommended_key = candidate.get(
            "catalog_key",
            candidate.get("name"),
        )
        mission = self.tonight_mission_service.create(
            winner=night,
            objects=top_objects,
            recommended_key=recommended_key,
            build_mission_input=lambda evaluation: self.build_mission_input(
                evaluation,
                profile=effective_profile,
            ),
        )

        if mission is None:
            return TonightResult(
                night,
                recommendation,
                None,
                status=TonightStatus.NO_MISSION,
                forecast_evidence=forecast_evidence,
            )

        DecisionConsistencyGate.validate_mission(mission)

        return TonightResult(
            night,
            recommendation,
            mission,
            status=(
                TonightStatus.AVAILABLE
                if DecisionConsistencyGate.has_productive_window(mission)
                else TonightStatus.NO_PRODUCTIVE_WINDOW
            ),
            forecast_evidence=forecast_evidence,
        )
