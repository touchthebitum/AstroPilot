from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from astropilot.user_profile import (
    UserProfileError,
    is_finite_number,
    resolve_equipment_definition,
)
from decision.forecast.forecast_run import ForecastRun
from decision.mission.night_mission import NightMission
from decision.models.candidate_rejection import (
    CandidateBuildResult,
    CandidateRejection,
)
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
        or resolve_equipment_definition(profile, selected_equipment) is None
        or not isinstance(available_equipment, list)
        or selected_equipment not in available_equipment
    ):
        raise TonightEquipmentSelectionError("invalid_tonight_equipment")

    return selected_equipment


@dataclass(frozen=True)
class TonightInputs:
    location: dict
    bortle: int
    equipment: str


def resolve_tonight_inputs(
    profile,
    *,
    location=None,
    bortle=None,
    equipment=None,
) -> TonightInputs:
    """Resolve only Tonight's critical local inputs, without I/O or mutation."""
    selected_equipment = resolve_tonight_equipment(profile, equipment)
    selected_location = location if location is not None else profile.get("location")
    if not isinstance(selected_location, dict):
        raise UserProfileError("Configuration Tonight : location requise et valide.")
    name = selected_location.get("name")
    if not isinstance(name, str) or not name.strip():
        raise UserProfileError("Configuration Tonight : location.name invalide.")
    for field, limit in (("latitude", 90), ("longitude", 180)):
        value = selected_location.get(field)
        if not is_finite_number(value) or not -limit <= value <= limit:
            raise UserProfileError(f"Configuration Tonight : location.{field} invalide.")

    preferences = profile.get("preferences", {})
    selected_bortle = (
        bortle
        if bortle is not None
        else preferences.get("bortle") if isinstance(preferences, dict) else None
    )
    if (
        not isinstance(selected_bortle, int)
        or isinstance(selected_bortle, bool)
        or not 1 <= selected_bortle <= 9
    ):
        raise UserProfileError("Configuration Tonight : Bortle requis, entier de 1 à 9.")

    return TonightInputs(dict(selected_location), selected_bortle, selected_equipment)


@dataclass(frozen=True)
class TonightResult:
    night: dict | None
    recommendation: Recommendation | None
    mission: NightMission | None
    status: TonightStatus = TonightStatus.AVAILABLE
    forecast_evidence: DecisionForecastEvidence | None = None
    decision_id: str | None = None
    candidate_rejections: tuple[CandidateRejection, ...] = ()

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
        inputs = resolve_tonight_inputs(profile, equipment=equipment, bortle=bortle)
        selected_equipment = inputs.equipment
        effective_profile = {
            **profile,
            "location": inputs.location,
            "active_equipment": selected_equipment,
            "available_equipment": [selected_equipment],
        }
        location = inputs.location
        forecast_run: ForecastRun | None = self.forecast_nights(
            location["latitude"],
            location["longitude"],
            location["name"],
            inputs.bortle,
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
        candidate_build = self.build_candidates(
            top_objects,
            available_hours=night.get("duration"),
            profile=effective_profile,
        )
        if isinstance(candidate_build, CandidateBuildResult):
            candidates = list(candidate_build.candidates)
            candidate_rejections = candidate_build.rejections
        else:
            candidates = candidate_build
            candidate_rejections = ()

        if not candidates:
            return TonightResult(
                night,
                None,
                None,
                status=TonightStatus.NO_CANDIDATE,
                forecast_evidence=forecast_evidence,
                candidate_rejections=candidate_rejections,
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
                candidate_rejections=candidate_rejections,
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
                candidate_rejections=candidate_rejections,
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
            candidate_rejections=candidate_rejections,
        )
