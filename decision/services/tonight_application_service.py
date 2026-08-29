from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from decision.mission.night_mission import NightMission
from decision.recommendation.recommendation import Recommendation


class TonightStatus(str, Enum):
    AVAILABLE = "available"
    FORECAST_UNAVAILABLE = "forecast_unavailable"
    NO_NIGHT = "no_night"
    NO_CANDIDATE = "no_candidate"
    NO_RECOMMENDATION = "no_recommendation"
    NO_MISSION = "no_mission"


@dataclass(frozen=True)
class TonightResult:
    night: dict | None
    recommendation: Recommendation | None
    mission: NightMission | None
    status: TonightStatus = TonightStatus.AVAILABLE

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
        equipment=None,
        goal="balanced",
        target="deep_sky",
        bortle=3,
    ) -> TonightResult:
        location = profile.get(
            "location",
            {
                "name": "Buttes",
                "latitude": 46.7508,
                "longitude": 6.5495,
            },
        )
        nights = self.forecast_nights(
            location["latitude"],
            location["longitude"],
            location["name"],
            bortle,
            target=target,
            equipment=equipment,
            goal=goal,
            weather=weather,
            profile=profile,
        )

        if nights is None:
            return TonightResult(
                None,
                None,
                None,
                status=TonightStatus.FORECAST_UNAVAILABLE,
            )

        if not nights:
            return TonightResult(
                None,
                None,
                None,
                status=TonightStatus.NO_NIGHT,
            )

        night = sorted(nights, key=lambda item: item["date"])[0]
        top_objects = night.get("top_objects") or []
        candidates = self.build_candidates(
            top_objects,
            available_hours=night.get("duration", 3.0),
            profile=profile,
        )

        if not candidates:
            return TonightResult(
                night,
                None,
                None,
                status=TonightStatus.NO_CANDIDATE,
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
                profile=profile,
            ),
        )

        return TonightResult(
            night,
            recommendation,
            mission,
            status=(
                TonightStatus.AVAILABLE
                if mission is not None
                else TonightStatus.NO_MISSION
            ),
        )
