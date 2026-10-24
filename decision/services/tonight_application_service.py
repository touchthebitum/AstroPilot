from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from astropilot.user_profile import (
    UserProfileError,
    is_finite_number,
    resolve_equipment_definition,
)
from decision.forecast.forecast_run import ForecastRun
from decision.mission.night_mission import NightMission
from decision.mission.mission_input import MissionInput
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.candidate_rejection import (
    CandidateBuildResult,
    CandidateRejection,
)
from decision.models.acquisition_intent_selection import AcquisitionIntentSelectionStatus
from decision.models.session_availability import SessionAvailability, requested_evening
from decision.recommendation.recommendation import Recommendation
from decision.services.session_availability_windowing import ActionabilityRefusal
from decision.validation.decision_consistency import DecisionConsistencyGate
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import WeatherLocation
from decision.weather.weather_ingress import (
    WeatherSnapshot,
    validate_weather_freshness,
)


class TonightStatus(str, Enum):
    AVAILABLE = "available"
    FORECAST_UNAVAILABLE = "forecast_unavailable"
    NO_NIGHT = "no_night"
    NO_CANDIDATE = "no_candidate"
    NO_RECOMMENDATION = "no_recommendation"
    NO_MISSION = "no_mission"
    USER_AVAILABILITY_REQUIRED = "user_availability_required"
    NO_PRODUCTIVE_WINDOW = "no_productive_window"


class TonightEquipmentSelectionError(ValueError):
    code = "invalid_tonight_equipment"


def _select_forecast_night(nights, availability, weather):
    """A dated availability selects its evening, including the following dawn.

    Undated modes retain Tonight's earliest-forecast behavior. Never substitute
    another evening when the requested one is missing from the forecast.
    """
    anchor = availability.start or availability.end if availability is not None else None
    zone = ZoneInfo(weather.timezone) if isinstance(weather, WeatherSnapshot) else getattr(anchor, 'tzinfo', None)
    evening = requested_evening(availability, zone)
    if evening is None:
        return min(nights, key=lambda item: item["date"])
    return next(
        (
            night for night in nights
            if (
                date.fromisoformat(night["date"])
                if isinstance(night["date"], str)
                else night["date"]
            ) == evening
        ),
        None,
    )


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
    availability: SessionAvailability | None = None


def resolve_tonight_inputs(
    profile,
    *,
    location=None,
    bortle=None,
    equipment=None,
    availability: SessionAvailability | None = None,
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

    if availability is not None and not isinstance(availability, SessionAvailability):
        raise TypeError("Expected SessionAvailability or None")

    return TonightInputs(
        dict(selected_location),
        selected_bortle,
        selected_equipment,
        availability,
    )


@dataclass(frozen=True)
class TonightResult:
    night: dict | None
    recommendation: Recommendation | None
    mission: NightMission | None
    status: TonightStatus = TonightStatus.AVAILABLE
    forecast_evidence: DecisionForecastEvidence | None = None
    decision_id: str | None = None
    candidate_rejections: tuple[CandidateRejection, ...] = ()
    actionability_refusal: ActionabilityRefusal | None = None
    timeline_start: datetime | None = None
    creation_refusal: str | None = None
    # Internal live evidence, deliberately absent from TonightResponse/API.
    alert_mission_input: MissionInput | None = field(default=None, repr=False, compare=False)
    alert_assessment: ProductiveWindowAssessment | None = field(default=None, repr=False, compare=False)
    alert_live_marker: object | None = field(default=None, repr=False, compare=False)

    @property
    def forecast_available(self) -> bool:
        return self.status is not TonightStatus.FORECAST_UNAVAILABLE


_ALERT_LIVE_MARKER = object()


def _live_alert_result(result):
    return replace(result, alert_live_marker=_ALERT_LIVE_MARKER)


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
        availability: SessionAvailability | None = None,
        selected_project_id: str | None = None,
    ) -> TonightResult:
        if (selected_project_id is not None
                and selected_project_id not in profile.get("projects", {})):
            raise ValueError("selected_project_unavailable")
        inputs = resolve_tonight_inputs(
            profile,
            equipment=equipment,
            bortle=bortle,
            availability=availability,
        )
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
            availability=inputs.availability,
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

        night = _select_forecast_night(nights, inputs.availability, weather)
        if night is None:
            return TonightResult(
                None,
                None,
                None,
                status=TonightStatus.NO_NIGHT,
                forecast_evidence=forecast_evidence,
            )
        top_objects = night.get("top_objects") or []
        if selected_project_id is not None:
            # Scope candidates and durable acceptance evidence, never the saved
            # portfolio or its credits. An unsuitable choice cannot fall back
            # to another project or to a discovery candidate.
            top_objects = [obj for obj in top_objects
                           if obj.get("catalog_key", obj.get("name")) == selected_project_id]
            night = {
                **night, "top_objects": top_objects,
                "object_evaluations": {
                    key: value for key, value in night.get("object_evaluations", {}).items()
                    if key == selected_project_id
                },
            }
        weather_snapshot = (
            weather if isinstance(weather, WeatherSnapshot) else None
        )
        weather_freshness = (
            validate_weather_freshness(
                weather_snapshot,
                reference_time_utc=reference_time_utc,
            )
            if weather_snapshot is not None
            else None
        )
        candidate_build = self.build_candidates(
            top_objects,
            available_hours=night.get("duration"),
            profile=effective_profile,
            object_evaluations=night.get("object_evaluations", {}),
            session_availability=inputs.availability,
            weather_snapshot=weather_snapshot,
            weather_freshness=weather_freshness,
            decision_location=(
                WeatherLocation(
                    latitude=location["latitude"],
                    longitude=location["longitude"],
                )
                if weather_snapshot is not None
                else None
            ),
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

        if inputs.availability is None:
            return TonightResult(
                night,
                recommendation,
                None,
                status=TonightStatus.USER_AVAILABILITY_REQUIRED,
                forecast_evidence=forecast_evidence,
                candidate_rejections=candidate_rejections,
            )

        candidate = recommendation.opportunity.candidate
        recommended_key = candidate.get(
            "catalog_key",
            candidate.get("name"),
        )

        # Preserve the eligibility diagnostic before reaching the creation gate.
        # A valid saved project can have no actionable intent for this night;
        # missing creation authority in that case is a consequence, not a
        # configuration error. Never select an intent or bypass the refusal.
        if (getattr(candidate, "acquisition_intent_selection_status", None)
                is AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT):
            return TonightResult(
                night, recommendation, None,
                status=TonightStatus.NO_MISSION,
                forecast_evidence=forecast_evidence,
                candidate_rejections=candidate_rejections,
                creation_refusal="no_eligible_acquisition_intent",
            )

        # Comparative lunar evidence belongs to the candidate until an intent
        # is selected. It cannot be attached to an unidentified mission input.
        if (candidate.lunar_evidence_snapshot is not None
                and candidate.selected_acquisition_intent_id is None):
            return TonightResult(
                night,
                recommendation,
                None,
                status=TonightStatus.NO_MISSION,
                forecast_evidence=forecast_evidence,
                candidate_rejections=candidate_rejections,
                creation_refusal="preselection_evidence_cannot_authorize_mission",
            )

        timeline_start = None
        alert_mission_input = None
        alert_assessment = None

        def build_actionability_mission_input(evaluation):
            nonlocal timeline_start, alert_mission_input
            if isinstance(evaluation, Mapping):
                evaluation = {
                    **evaluation,
                    "lunar_evidence_snapshot": candidate.lunar_evidence_snapshot,
                    "imaging_field_id": candidate.imaging_field_id,
                    "selected_acquisition_intent_id": (
                        candidate.selected_acquisition_intent_id
                    ),
                }
            mission_input = self.build_mission_input(
                evaluation,
                profile=effective_profile,
            )
            timeline_start = getattr(mission_input, "window_start", None)
            alert_mission_input = replace(
                mission_input,
                availability=inputs.availability,
            )
            return alert_mission_input

        create_with_diagnostic = getattr(
            self.tonight_mission_service,
            "create_with_actionability_diagnostic",
            None,
        )
        actionability_refusal = None
        creation_refusal = None
        if create_with_diagnostic is not None:
            assembly = create_with_diagnostic(
                winner=night,
                objects=top_objects,
                recommended_key=recommended_key,
                build_mission_input=build_actionability_mission_input,
            )
            mission = assembly.mission
            alert_assessment = assembly.assessment
            actionability_refusal = assembly.actionability_refusal
            creation_refusal = assembly.creation_refusal
        else:
            mission = self.tonight_mission_service.create(
                winner=night,
                objects=top_objects,
                recommended_key=recommended_key,
                build_mission_input=build_actionability_mission_input,
            )
        if mission is None:
            return TonightResult(
                night,
                recommendation,
                None,
                status=(
                    TonightStatus.NO_PRODUCTIVE_WINDOW
                    if actionability_refusal is not None
                    else TonightStatus.NO_MISSION
                ),
                forecast_evidence=forecast_evidence,
                candidate_rejections=candidate_rejections,
                actionability_refusal=actionability_refusal,
                timeline_start=timeline_start,
                creation_refusal=creation_refusal,
            )

        DecisionConsistencyGate.validate_mission(mission)

        if not DecisionConsistencyGate.has_productive_window(mission):
            if actionability_refusal is None:
                return TonightResult(
                    night,
                    recommendation,
                    None,
                    status=TonightStatus.NO_MISSION,
                    forecast_evidence=forecast_evidence,
                    candidate_rejections=candidate_rejections,
                )
            return TonightResult(
                night,
                recommendation,
                mission,
                status=TonightStatus.NO_PRODUCTIVE_WINDOW,
                forecast_evidence=forecast_evidence,
                candidate_rejections=candidate_rejections,
                actionability_refusal=actionability_refusal,
                timeline_start=timeline_start,
            )

        return _live_alert_result(TonightResult(
            night,
            recommendation,
            mission,
            status=TonightStatus.AVAILABLE,
            forecast_evidence=forecast_evidence,
            candidate_rejections=candidate_rejections,
            timeline_start=timeline_start,
            alert_mission_input=alert_mission_input,
            alert_assessment=alert_assessment,
        ))
