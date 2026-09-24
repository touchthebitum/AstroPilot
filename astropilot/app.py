from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import importlib.metadata
import math
import os
from pathlib import Path
import platform
import re
import tomllib
from typing import Annotated, Any, Callable, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

from astropilot.equipment_catalog import EQUIPMENT_PROFILES
from decision.definitions.production_imaging_fields import (
    IMAGING_FIELD_DEFINITIONS,
    build_production_imaging_field_resolver,
)
from astropilot.user_profile import (
    PersistedProfileCorruptError,
    ProfileRecoveryConflictError,
    ProfileRevisionConflictError,
    UserProfileError,
    create_or_replace_user_configuration,
    get_user_data_dir,
    load_user_profile,
    quarantine_corrupt_user_profile,
    resolve_equipment_definition,
    save_user_profile,
)
from decision.models.candidate import CandidateProvenance
from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelectionStatus,
)
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityReason,
    AcquisitionIntentEligibilityStatus,
    AcquisitionIntentEvidenceGap,
)
from decision.models.candidate_rejection import CandidateRejectionBasis
from decision.services.acquisition_intent_remaining_progress import (
    derive_acquisition_intent_remaining_progress, remaining_progress_projection,
)
from decision.services.intent_progress_credit import (
    IntentProgressCreditError, base_seconds, credit_totals, duration_us, load_credits,
)
from decision.models.project_acquisition_intent_target import ProjectAcquisitionIntentTarget
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.mission.night_mission import NightMission
from decision.models.execution import Execution, ExecutionStatus
from decision.night_productivity.productivity_diagnostics import (
    PRODUCTIVE_SLICE_THRESHOLD,
)
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    FieldOutcomeEvidence,
    ImageOutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)
from decision.models.portfolio_credit import PortfolioCredit
from decision.models.portfolio_credit_application import (
    PortfolioCreditApplication,
    PortfolioCreditApplicationOutcome,
    PortfolioCreditDestinationKind,
)
from decision.models.recommendation_reason import (
    RecommendationReasonCategory,
    RecommendationReasonScope,
)
from decision.services.recommendation_reason_builder import (
    candidate_assessment_reasons,
    candidate_reasons,
    primary_window_reasons,
)
from decision.services.tonight_comparisons import build_alternative_comparisons
from decision.services.tonight_alternative_reasons import alternative_reason_responses
from decision.services.tonight_primary_reasons import primary_reason_responses
from decision.services.target_explanation import (
    build_target_explanations,
    target_explanation_responses,
)
from decision.services.tonight_application_service import (
    TonightEquipmentSelectionError,
    TonightStatus,
    resolve_tonight_inputs,
)
from decision.services.tonight_rejected_targets import map_rejected_targets
from decision.services.tonight_target_evidence import (
    map_target_evidence_insufficiencies,
    qualify_candidate_evidence_insufficiency,
    qualify_primary_evidence_insufficiency,
)
from decision.services.tonight_response import (
    TargetDecisionStatus,
    TonightResponse,
)
from decision.services.candidate_assessment import (
    CandidateAssessment,
    CandidateViabilityEvaluator,
    select_actionable_alternatives,
)
from decision.services.decision_acceptance_application import DecisionAcceptanceError
from decision.services.execution_outcome_application import (
    ExecutionOutcomeApplicationError,
)
from decision.services.execution_transition import ExecutionTransitionError
from decision.services.user_selection_validator import UserSelectionValidationError
from decision.weather.provider_reliability import WeatherLocation
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherDecisionContext,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
    WeatherTrustDecisionEvaluator,
    WeatherTrustEvidence,
)
from decision.weather.weather_ingress import (
    WeatherFreshness,
    WeatherIngressError,
    WeatherSnapshot,
    validate_weather_freshness,
)
from decision.validation.decision_consistency import DecisionConsistencyError
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
)
from decision.validation.weather_window_coverage import (
    WeatherWindowCoverageError,
    validate_selected_window_weather_coverage,
)
from decision.location.location_time import (
    LocalWallTimeError,
    LocationTimeError,
    LocationTimeResolver,
    normalize_local_wall_time,
)


_BUILD_COMMIT_ENV = "ASTROPILOT_BUILD_COMMIT"
_SHORT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{7}")


def canonical_version() -> str:
    """Return the project version in source and installed/frozen runtimes."""

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if pyproject.is_file():
        with pyproject.open("rb") as handle:
            version = tomllib.load(handle)["project"]["version"]
        if version:
            return str(version)
    try:
        return importlib.metadata.version("astropilot")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("AstroPilot version metadata is unavailable.") from exc


def build_identifier() -> str:
    """Return the injected immutable build commit or a development marker."""

    value = os.environ.get(_BUILD_COMMIT_ENV)
    if value and _SHORT_COMMIT_PATTERN.fullmatch(value):
        return value
    return "development"


def normalize_runtime_architecture(architecture: str) -> str:
    if architecture.lower() in {"amd64", "x86_64"}:
        return "x86_64"
    return architecture


def runtime_architecture() -> str:
    return normalize_runtime_architecture(platform.machine())


def runtime_identity_payload() -> dict[str, str]:
    return {
        "application": "astropilot",
        "version": canonical_version(),
        "build": build_identifier(),
        "architecture": runtime_architecture(),
    }


class LocationRequest(BaseModel):
    name: str
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class ConfigurationSiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    bortle: int = Field(ge=1, le=9)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("site_name_required")
        return normalized


class CustomEquipmentConfigurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    optics_manufacturer: str
    optics_model: str
    focal_length_mm: float = Field(gt=0)
    aperture_mm: float = Field(gt=0)
    f_ratio: float = Field(gt=0)
    camera_manufacturer: str
    camera_model: str
    pixel_size_um: float = Field(gt=0)
    sensor_width_px: float = Field(gt=0)
    sensor_height_px: float = Field(gt=0)
    monochrome: bool

    @field_validator(
        "optics_manufacturer",
        "optics_model",
        "camera_manufacturer",
        "camera_model",
    )
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("equipment_label_required")
        return normalized


class EquipmentConfigurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    preset_id: str | None = None
    custom: CustomEquipmentConfigurationRequest | None = None

    @model_validator(mode="after")
    def require_exactly_one_kind(self):
        if (self.preset_id is None) == (self.custom is None):
            raise ValueError("exactly_one_equipment_kind_required")
        return self


class ProjectAcquisitionIntentTargetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    acquisition_intent_id: str
    target_hours: float = Field(gt=0, allow_inf_nan=False)

    @field_validator("acquisition_intent_id")
    @classmethod
    def validate_acquisition_intent_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("acquisition_intent_id_required")
        return value

    @field_validator("target_hours", mode="before")
    @classmethod
    def validate_target_hours(cls, value):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError("target_hours_must_be_finite_and_positive")
        return value


class ProjectConfigurationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_hours: float = Field(ge=0)
    hours: float = Field(ge=0)
    importance: float | None = Field(default=None, ge=0, le=10)
    imaging_field_id: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    acquisition_intent_targets: (
        tuple[ProjectAcquisitionIntentTargetModel, ...] | None
    ) = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    acquisition_intent_progress: tuple[dict[str, Any], ...] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="after")
    def validate_progress(self):
        if (
            "imaging_field_id" in self.model_fields_set
            and self.imaging_field_id is None
        ):
            raise ValueError("project_imaging_field_id_invalid")
        if (
            "acquisition_intent_targets" in self.model_fields_set
            and self.acquisition_intent_targets is None
        ):
            raise ValueError("project_acquisition_intent_targets_invalid")
        if (
            "acquisition_intent_progress" in self.model_fields_set
            and self.acquisition_intent_progress is None
        ):
            raise ValueError("project_acquisition_intent_progress_invalid")
        if self.hours > self.target_hours:
            raise ValueError("project_hours_exceed_target")
        return self


class ConfigurationWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    site: ConfigurationSiteRequest
    equipment: EquipmentConfigurationRequest
    projects: dict[str, ProjectConfigurationModel]
    expected_revision: int | None = Field(default=None, ge=0)


class ProjectProgressWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0, strict=True)
    imaging_field_id: str | None = None
    acquisition_intent_progress: tuple[dict[str, Any], ...] | None = None
    acquisition_intent_targets: tuple[ProjectAcquisitionIntentTargetModel, ...] | None = None

    @model_validator(mode="after")
    def reject_null_replacements(self):
        for name in (
            "imaging_field_id", "acquisition_intent_progress",
            "acquisition_intent_targets",
        ):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class IntentProgressCreditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int = Field(ge=0, strict=True)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    confirm_historical_baseline: bool = False

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, ids):
        if any(not value.strip() for value in ids) or len(set(ids)) != len(ids):
            raise ValueError("evidence_ids_invalid")
        return ids


class ConfigurationRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EquipmentConfigurationModel(BaseModel):
    id: str
    name: str
    kind: Literal["preset", "custom"]
    optics_manufacturer: str
    optics_model: str
    focal_length_mm: float
    aperture_mm: float
    f_ratio: float
    camera_manufacturer: str
    camera_model: str
    pixel_size_um: float
    sensor_width_px: float
    sensor_height_px: float
    monochrome: bool


class ConfigurationSiteModel(BaseModel):
    name: str
    latitude: float
    longitude: float
    bortle: int | None
    timezone: str


class ConfigurationResponse(BaseModel):
    configured: bool
    needs_configuration_confirmation: bool | None = None
    profile_revision: int | None
    site: ConfigurationSiteModel | None
    active_equipment_id: str | None
    available_equipment: list[EquipmentConfigurationModel]
    projects: dict[str, ProjectConfigurationModel]
    preset_equipment: list[EquipmentConfigurationModel]


class SessionAvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: SessionAvailabilityMode
    start: datetime | None = None
    end: datetime | None = None
    start_local: str | None = None
    end_local: str | None = None
    duration: timedelta | None = None

    @property
    def has_local_wall_time(self) -> bool:
        return self.start_local is not None or self.end_local is not None

    def to_domain(self, *, site_zone=None) -> SessionAvailability:
        if self.has_local_wall_time:
            if self.start is not None or self.end is not None:
                raise LocalWallTimeError(
                    "session_availability_mixed_time_contract"
                )
            supplied_fields = {
                name
                for name, value in (
                    ("start_local", self.start_local),
                    ("end_local", self.end_local),
                    ("duration", self.duration),
                )
                if value is not None
            }
            required_fields = {
                SessionAvailabilityMode.ALL_NIGHT: set(),
                SessionAvailabilityMode.DURATION: {"duration"},
                SessionAvailabilityMode.START_AND_DURATION: {
                    "start_local",
                    "duration",
                },
                SessionAvailabilityMode.UNTIL: {"end_local"},
                SessionAvailabilityMode.FIXED_WINDOW: {
                    "start_local",
                    "end_local",
                },
            }[self.mode]
            if supplied_fields != required_fields:
                raise LocalWallTimeError(
                    "invalid_session_availability_fields"
                )
            if site_zone is None:
                raise LocationTimeError("timezone_not_found")
            start = (
                normalize_local_wall_time(self.start_local, site_zone)
                if self.start_local is not None
                else None
            )
            end = (
                normalize_local_wall_time(self.end_local, site_zone)
                if self.end_local is not None
                else None
            )
        else:
            # Transitional compatibility for the aware start/end transport;
            # Beta-2a2 moves the web UI to start_local/end_local.
            start = self.start
            end = self.end
        return SessionAvailability(
            mode=self.mode,
            start=start,
            end=end,
            duration=self.duration,
        )

    @model_validator(mode="after")
    def validate_domain_contract(self):
        if self.has_local_wall_time:
            return self
        try:
            self.to_domain()
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self


class TonightRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "location": {
                        "name": "Buttes",
                        "latitude": 46.7508,
                        "longitude": 6.5495,
                    },
                    "equipment": "samyang_183",
                    "goal": "balanced",
                    "target": "deep_sky",
                    "bortle": 3,
                }
            ]
        }
    )

    location: LocationRequest | None = None
    availability: SessionAvailabilityRequest | None = None
    equipment: str | None = None
    goal: Literal[
        "balanced",
        "galaxies",
        "nebulae",
        "widefield",
        "small_targets",
        "highest_score",
        "best_setup",
    ] = "balanced"
    target: Literal[
        "milky_way",
        "deep_sky",
        "planetary",
        "moon",
        "nightscape",
    ] = "deep_sky"
    bortle: int | None = Field(default=None, ge=1, le=9)


class UserSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    acceptance_request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    )
    decision_id: str
    source: UserSelectionSource
    selected_catalog_key: str | None = None
    acquisition_intent_id: str | None = None
    selected_at: datetime

    def to_domain(self, *, selection_id: str) -> UserSelection:
        return UserSelection(
            selection_id=selection_id,
            decision_id=self.decision_id,
            selected_catalog_key=self.selected_catalog_key,
            source=self.source,
            selected_at=self.selected_at,
            selected_acquisition_intent_id=self.acquisition_intent_id,
        )

    @model_validator(mode="after")
    def validate_domain_contract(self):
        try:
            self.to_domain(selection_id="validation-selection-id")
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self


class AcceptedMissionFilterResponse(BaseModel):
    name: str
    filter_type: str
    bandwidth_nm: float | None = None


class AcceptedMissionTaskResponse(BaseModel):
    start: str
    end: str
    title: str
    description: str = ""
    priority: int = 0


class AcceptedMissionResponse(BaseModel):
    mission_id: str
    decision_id: str
    selection_id: str
    imaging_field_id: str | None = None
    target: str
    confidence: float | str | None = None
    equipment: list[str] = Field(default_factory=list)
    site_name: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    recommended_hours: float = 0.0
    expected_gain: float = 0.0
    selected_filter: AcceptedMissionFilterResponse | None = None
    tasks: list[AcceptedMissionTaskResponse] = Field(default_factory=list)


class UserSelectionResponse(BaseModel):
    status: Literal["accepted", "declined"]
    mission_id: str | None = None
    decision_id: str
    selection_id: str
    catalog_key: str | None = None
    selected_imaging_field_id: str | None = None
    selected_acquisition_intent_id: str | None = None
    mission: AcceptedMissionResponse | None = None


class ExecutionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_id: str
    mission_id: str

    @model_validator(mode="after")
    def validate_domain_contract(self):
        try:
            Execution(
                execution_id=self.execution_id,
                mission_id=self.mission_id,
                status=ExecutionStatus.NOT_STARTED,
                actual_start=None,
                actual_end=None,
                actual_duration=None,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self


class ExecutionTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_id: str
    mission_id: str
    status: ExecutionStatus
    actual_start: datetime | None
    actual_end: datetime | None
    actual_duration: timedelta | None

    def to_domain(self) -> Execution:
        return Execution(
            execution_id=self.execution_id,
            mission_id=self.mission_id,
            status=self.status,
            actual_start=self.actual_start,
            actual_end=self.actual_end,
            actual_duration=self.actual_duration,
        )

    @model_validator(mode="after")
    def validate_domain_contract(self):
        try:
            self.to_domain()
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self


class ExecutionResponse(BaseModel):
    execution_id: str
    mission_id: str
    status: ExecutionStatus
    actual_start: datetime | None
    actual_end: datetime | None
    actual_duration: timedelta | None


class OutcomeEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    execution_id: str
    category: OutcomeEvidenceCategory
    observed_at: datetime
    source: OutcomeEvidenceSource
    actual_capture_duration: timedelta | None = None
    usable_integration_duration: timedelta | None = None

    def to_domain(self):
        common = {
            "evidence_id": self.evidence_id,
            "execution_id": self.execution_id,
            "category": self.category,
            "observed_at": self.observed_at,
            "source": self.source,
        }
        kinds = {
            OutcomeEvidenceCategory.FIELD: FieldOutcomeEvidence,
            OutcomeEvidenceCategory.TECHNICAL: TechnicalOutcomeEvidence,
            OutcomeEvidenceCategory.ACQUISITION: AcquisitionOutcomeEvidence,
            OutcomeEvidenceCategory.IMAGE: ImageOutcomeEvidence,
        }
        kind = kinds[self.category]
        if kind is AcquisitionOutcomeEvidence:
            common.update(
                actual_capture_duration=self.actual_capture_duration,
                usable_integration_duration=self.usable_integration_duration,
            )
        elif (
            self.actual_capture_duration is not None
            or self.usable_integration_duration is not None
        ):
            raise ValueError("acquisition_duration_category_mismatch")
        return kind(**common)

    @model_validator(mode="after")
    def validate_domain_contract(self):
        try:
            self.to_domain()
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self


class OutcomeEvidenceResponse(BaseModel):
    evidence_id: str
    execution_id: str
    category: OutcomeEvidenceCategory
    observed_at: datetime
    source: OutcomeEvidenceSource
    actual_capture_duration: timedelta | None = None
    usable_integration_duration: timedelta | None = None


class PortfolioCreditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    credit_id: str
    execution_id: str
    evidence_ids: tuple[str, ...]
    usable_integration_duration: timedelta
    credited_at: datetime

    def to_domain(self) -> PortfolioCredit:
        return PortfolioCredit(
            credit_id=self.credit_id,
            execution_id=self.execution_id,
            evidence_ids=self.evidence_ids,
            usable_integration_duration=self.usable_integration_duration,
            credited_at=self.credited_at,
        )

    @model_validator(mode="after")
    def validate_domain_contract(self):
        try:
            self.to_domain()
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self


class PortfolioCreditApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str
    credit_id: str
    object_name: str
    destination_kind: PortfolioCreditDestinationKind
    applied_duration: timedelta
    applied_at: datetime

    def to_domain(self) -> PortfolioCreditApplication:
        return PortfolioCreditApplication(
            application_id=self.application_id,
            credit_id=self.credit_id,
            object_name=self.object_name,
            destination_kind=self.destination_kind,
            applied_duration=self.applied_duration,
            applied_at=self.applied_at,
        )

    @model_validator(mode="after")
    def validate_domain_contract(self):
        try:
            self.to_domain()
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        return self


class PortfolioCreditApplicationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    credit: PortfolioCreditRequest
    application: PortfolioCreditApplicationRequest


class PortfolioCreditApplicationResponse(BaseModel):
    outcome: PortfolioCreditApplicationOutcome
    application_id: str
    credit_id: str
    object_name: str
    destination_kind: PortfolioCreditDestinationKind
    applied_duration: timedelta
    applied_at: datetime


class TonightReasonModel(BaseModel):
    title: str
    severity: str
    value: str | None = None


class TonightFilterModel(BaseModel):
    name: str
    filter_type: str
    bandwidth_nm: float | None = None


class TonightAstroQualityModel(BaseModel):
    score: float
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Completeness of AQI inputs; not weather forecast reliability."
        ),
    )
    label: str
    limiting_factor: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class TonightProductivityWindowModel(BaseModel):
    start_offset_hours: float
    end_offset_hours: float
    start_time: str
    end_time: str
    productivity: float
    productive: bool
    reason: str
    altitude: float
    cloud_cover: float
    moon_penalty: float
    seeing: float


class TonightProductivityModel(BaseModel):
    astronomical_hours: float
    productive_hours: float
    productive_fraction: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Deprecated compatibility alias for productive_fraction; "
            "this is not forecast confidence."
        ),
    )
    cloud_loss: float
    moon_loss: float
    altitude_loss: float
    weather_loss: float
    display_start_hour: int
    windows: list[TonightProductivityWindowModel] = Field(default_factory=list)


class TonightDewRiskModel(BaseModel):
    level: str
    score: float
    dew_point_c: float
    spread_c: float


class TonightPostponementRiskModel(BaseModel):
    level: str
    score: int
    explanations: list[str] = Field(default_factory=list)
    required_nights: int | None = None
    productive_hours_per_night: float | None = None
    capacity_source: str | None = None
    historical_nights: int | None = None
    remaining_hours: float | None = None
    favorable_nights: int | None = None
    season_remaining_days: int | None = None


class TonightSeasonModel(BaseModel):
    analysis_name: str
    conclusion: str
    confidence: float
    data: dict = Field(default_factory=dict)


class TonightExplanationModel(BaseModel):
    positives: list[TonightReasonModel] = Field(default_factory=list)
    warnings: list[TonightReasonModel] = Field(default_factory=list)
    information: list[TonightReasonModel] = Field(default_factory=list)
    limiting_factors: list[str] = Field(default_factory=list)


class TonightTaskModel(BaseModel):
    start: str
    end: str
    title: str
    description: str = ""
    priority: int = 0


class TonightAdviceModel(BaseModel):
    time: str
    priority: str
    category: str
    message: str


class TonightWeatherTrustModel(BaseModel):
    provider: str
    retrieved_at_utc: str
    requested_latitude: float
    requested_longitude: float
    grid_latitude: float
    grid_longitude: float
    grid_distance_km: float
    elevation_m: float | None = None
    timezone: str
    timezone_source: Literal["coordinates_local"]
    utc_offset_seconds: int
    valid_from: str
    valid_until: str
    hour_count: int = Field(ge=24)
    completeness: float = Field(ge=0.0, le=1.0)
    validation_status: Literal["validated"]
    snapshot_age_minutes: float = Field(ge=0.0)
    freshness_status: Literal["fresh"]
    maximum_age_minutes: int = Field(gt=0)


class TonightWeatherDecisionPresentationModel(BaseModel):
    label: str
    summary: str


class TonightWeatherDecisionModel(BaseModel):
    evidence_quality: WeatherEvidenceQuality
    admissibility: WeatherDecisionAdmissibility
    reasons: list[str]
    presentation: TonightWeatherDecisionPresentationModel


class TonightShortlistEntryModel(BaseModel):
    target: str
    catalog_key: str
    provenance: Literal["project", "discovery"]
    decision_score: float
    final_score: float
    target_decision_status: TargetDecisionStatus | None = None


class AlternativeReasonResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: RecommendationReasonScope
    category: RecommendationReasonCategory | None = None
    direction: str | None = None
    importance: str | None = None
    basis: str | None = None
    message: str | None = None
    rendered: RecommendationReasonRenderingResponseModel | None = None


class TonightAcquisitionIntentOptionModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    acquisition_intent_id: str
    filter_type: str
    label: str


class TonightAcquisitionIntentAssessmentModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    acquisition_intent_id: str
    filter_type: str
    label: str
    status: AcquisitionIntentEligibilityStatus
    reason_codes: tuple[
        AcquisitionIntentEligibilityReason | AcquisitionIntentEvidenceGap,
        ...,
    ]

    @model_validator(mode="after")
    def validate_status_reasons(self):
        if self.status is AcquisitionIntentEligibilityStatus.ELIGIBLE:
            if self.reason_codes:
                raise ValueError("eligible_must_not_have_reason_codes")
        elif self.status is AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE:
            if not self.reason_codes or not all(
                isinstance(code, AcquisitionIntentEligibilityReason)
                for code in self.reason_codes
            ):
                raise ValueError("not_eligible_requires_blocking_reasons")
        elif not self.reason_codes or not all(
            isinstance(code, AcquisitionIntentEvidenceGap)
            for code in self.reason_codes
        ):
            raise ValueError("insufficient_evidence_requires_evidence_gaps")
        return self


class TonightAlternativeModel(BaseModel):
    target: str
    catalog_key: str
    provenance: Literal["project", "discovery"]
    decision_score: float
    final_score: float
    target_decision_status: TargetDecisionStatus | None = None
    reasons: tuple[AlternativeReasonResponseModel, ...] = ()
    imaging_field_id: str | None = None
    selected_acquisition_intent_id: str | None = None
    viable_acquisition_intent_ids: tuple[str, ...] = ()
    acquisition_intent_selection_status: AcquisitionIntentSelectionStatus | None = None
    acquisition_intent_options: list[TonightAcquisitionIntentOptionModel] = Field(default_factory=list)
    acquisition_intent_assessments: list[
        TonightAcquisitionIntentAssessmentModel
    ] = Field(default_factory=list)


class TonightRejectedTargetModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    catalog_key: str
    provenance: CandidateProvenance
    basis: CandidateRejectionBasis
    evaluation_score: float
    target_decision_status: Literal[TargetDecisionStatus.NOT_RECOMMENDED] = (
        TargetDecisionStatus.NOT_RECOMMENDED
    )


class TonightInsufficientEvidenceTargetModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    catalog_key: str
    provenance: CandidateProvenance
    weather_decision: WeatherTrustDecision
    target_decision_status: Literal[TargetDecisionStatus.INSUFFICIENT_EVIDENCE] = (
        TargetDecisionStatus.INSUFFICIENT_EVIDENCE
    )


class RecommendationReasonRenderingResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    presentation_key: str
    classic_text: str
    pro_text: str


class PrimaryRecommendationReasonResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: RecommendationReasonScope
    category: RecommendationReasonCategory | None = None
    direction: str | None = None
    importance: str | None = None
    basis: str | None = None
    message: str | None = None
    rendered: RecommendationReasonRenderingResponseModel | None = None


class TargetExplanationResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    catalog_key: str
    target_decision_status: TargetDecisionStatus
    reasons: tuple[PrimaryRecommendationReasonResponseModel, ...] = ()


class RecommendationReasonResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: RecommendationReasonCategory | None = None
    scope: RecommendationReasonScope
    direction: str | None = None
    importance: str | None = None
    basis: str | None = None
    message: str | None = None
    evidence_ref: Any | None = None
    rendered_reasons: tuple[RecommendationReasonRenderingResponseModel, ...] = ()


class RecommendationComparisonResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    primary_catalog_key: str
    alternative_catalog_key: str
    primary_only_reasons: tuple[RecommendationReasonResponseModel, ...] = ()
    alternative_only_reasons: tuple[RecommendationReasonResponseModel, ...] = ()
    shared_reasons: tuple[RecommendationReasonResponseModel, ...] = ()


class ActionabilityRefusalBaseModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    conclusion: Literal["no_productive_window"]
    cause_code: str | None = None
    required_continuous_minutes: int = Field(gt=0, strict=True)
    limiting_factors: list[dict[str, str]] = Field(default_factory=list)


class ProductivityLossesModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    cloud: float = Field(ge=0, strict=True)
    moon: float = Field(ge=0, strict=True)
    altitude: float = Field(ge=0, strict=True)
    humidity: float = Field(ge=0, strict=True)
    wind: float = Field(ge=0, strict=True)


class ProductivityBreakdownModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluated_slice_count: int = Field(ge=0, strict=True)
    productive_slice_count: int = Field(ge=0, strict=True)
    best_slice_start: AwareDatetime | None = None
    best_slice_end: AwareDatetime | None = None
    best_slice_score: float | None = Field(default=None, ge=0, le=1, strict=True)
    best_slice_tie_count: int | None = Field(default=None, ge=1, strict=True)
    productive_slice_threshold: Literal[PRODUCTIVE_SLICE_THRESHOLD]
    losses: ProductivityLossesModel | None = None

    @model_validator(mode="after")
    def validate_breakdown(self):
        if self.productive_slice_count > self.evaluated_slice_count:
            raise ValueError("productive_slice_count_exceeds_evaluated")
        best_slice_fields = (
            self.best_slice_start,
            self.best_slice_end,
            self.best_slice_score,
            self.best_slice_tie_count,
            self.losses,
        )
        if self.evaluated_slice_count == 0:
            if any(value is not None for value in best_slice_fields):
                raise ValueError("empty_breakdown_forbids_best_slice")
            return self
        if any(value is None for value in best_slice_fields):
            raise ValueError("evaluated_breakdown_requires_best_slice")
        if self.best_slice_tie_count > self.evaluated_slice_count:
            raise ValueError("best_slice_tie_count_exceeds_evaluated")
        if self.best_slice_end.astimezone(
            timezone.utc
        ) <= self.best_slice_start.astimezone(timezone.utc):
            raise ValueError("best_slice_end_must_follow_start")
        return self


class ConstraintsActionabilityRefusalModel(ActionabilityRefusalBaseModel):
    status: Literal["constraints_refusal"]
    best_productive_window_minutes: float = Field(ge=0)
    refusal_stage: Literal[
        "no_productive_slice",
        "continuous_window_too_short",
    ] | None = None
    productivity_breakdown: ProductivityBreakdownModel | None = None

    @model_validator(mode="after")
    def validate_breakdown_stage(self):
        if self.productivity_breakdown is None:
            return self
        breakdown = self.productivity_breakdown
        if self.refusal_stage == "no_productive_slice":
            if breakdown.productive_slice_count != 0:
                raise ValueError("no_productive_slice_requires_zero_productive")
            if (
                breakdown.best_slice_score is not None
                and breakdown.best_slice_score
                >= breakdown.productive_slice_threshold
            ):
                raise ValueError("no_productive_slice_score_reaches_threshold")
        elif self.refusal_stage == "continuous_window_too_short":
            if breakdown.productive_slice_count < 1:
                raise ValueError("continuous_window_requires_productive_slice")
        else:
            raise ValueError("productivity_breakdown_stage_mismatch")
        return self


class InsufficientEvidenceActionabilityRefusalModel(
    ActionabilityRefusalBaseModel
):
    status: Literal["insufficient_evidence"]
    best_productive_window_minutes: None
    refusal_stage: None = None
    productivity_breakdown: None = None


class ActionabilityRefusalModel(
    RootModel[
        Annotated[
            ConstraintsActionabilityRefusalModel
            | InsufficientEvidenceActionabilityRefusalModel,
            Field(discriminator="status"),
        ]
    ]
):
    model_config = ConfigDict(frozen=True)


class TonightResponseModel(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "available",
                    "night_date": "2026-08-29",
                    "target": "NGC 7000",
                    "catalog_key": "ngc7000",
                    "target_common_name": "North America Nebula",
                    "action": "continue_project",
                    "recommendation_confidence": 0.91,
                    "mission_confidence": 0.88,
                    "scores": {"astronomy": 84.0, "mission": 89.0},
                    "window_start": "22:30",
                    "window_end": "02:30",
                    "recommended_hours": 4.0,
                    "expected_gain": 3.4,
                    "equipment": ["widefield", "dual_narrowband"],
                    "selected_filter": {
                        "name": "L-eXtreme",
                        "filter_type": "dual_narrowband",
                        "bandwidth_nm": 7.0,
                    },
                    "astro_quality": {
                        "score": 86.0,
                        "confidence": 0.9,
                        "label": "very_good",
                        "limiting_factor": "moon",
                        "metrics": {"altitude": 92.0, "moon": 71.0},
                    },
                    "productivity": {
                        "astronomical_hours": 6.2,
                        "productive_hours": 4.0,
                        "productive_fraction": 0.65,
                        "confidence": 0.65,
                        "cloud_loss": 0.8,
                        "moon_loss": 0.7,
                        "altitude_loss": 0.4,
                        "weather_loss": 0.3,
                        "display_start_hour": 20,
                        "windows": [
                            {
                                "start_offset_hours": 2.5,
                                "end_offset_hours": 6.5,
                                "start_time": "22:30",
                                "end_time": "02:30",
                                "productivity": 0.85,
                                "productive": True,
                                "reason": "Strong altitude and clear sky",
                                "altitude": 62.0,
                                "cloud_cover": 12.0,
                                "moon_penalty": 0.18,
                                "seeing": 1.7,
                            }
                        ],
                    },
                    "dew_risk": {
                        "level": "low",
                        "score": 18.0,
                        "dew_point_c": 7.0,
                        "spread_c": 5.0,
                    },
                    "postponement_risk": {
                        "level": "medium",
                        "score": 44,
                        "explanations": ["Five favorable nights remain."],
                        "required_nights": 2,
                        "productive_hours_per_night": 3.5,
                        "capacity_source": "forecast",
                        "historical_nights": 8,
                        "remaining_hours": 6.0,
                        "favorable_nights": 5,
                        "season_remaining_days": 24,
                    },
                    "season": {
                        "analysis_name": "season_window",
                        "conclusion": "The target remains well placed.",
                        "confidence": 0.82,
                        "data": {"remaining_days": 24},
                    },
                    "explanation": {
                        "positives": [
                            {
                                "title": "High altitude",
                                "severity": "positive",
                                "value": "62 deg",
                            }
                        ],
                        "warnings": [],
                        "information": [],
                        "limiting_factors": ["moon"],
                    },
                    "reasons": [
                        {
                            "title": "Portfolio priority",
                            "severity": "positive",
                            "value": "high",
                        }
                    ],
                    "tasks": [
                        {
                            "start": "T-30 min",
                            "end": "T-20 min",
                            "title": "Installer le matériel",
                            "description": "",
                            "priority": 0,
                        }
                    ],
                    "advices": [
                        {
                            "time": "Avant installation",
                            "priority": "MEDIUM",
                            "category": "weather",
                            "message": "Check the latest weather forecast.",
                        }
                    ],
                    "weather_trust": {
                        "provider": "Open-Meteo",
                        "retrieved_at_utc": "2026-08-29T18:00:00+00:00",
                        "requested_latitude": 46.7508,
                        "requested_longitude": 6.5495,
                        "grid_latitude": 46.75,
                        "grid_longitude": 6.55,
                        "grid_distance_km": 0.1,
                        "elevation_m": 837.0,
                        "timezone": "Europe/Zurich",
                        "timezone_source": "coordinates_local",
                        "utc_offset_seconds": 7200,
                        "valid_from": "2026-08-29T00:00:00+02:00",
                        "valid_until": "2026-09-04T23:00:00+02:00",
                        "hour_count": 168,
                        "completeness": 1.0,
                        "validation_status": "validated",
                        "snapshot_age_minutes": 4.5,
                        "freshness_status": "fresh",
                        "maximum_age_minutes": 90,
                    },
                    "weather_decision": {
                        "evidence_quality": "insufficient",
                        "admissibility": "caution",
                        "reasons": ["provider_reliability_unavailable"],
                        "presentation": {
                            "label": "Validation météo partielle",
                            "summary": (
                                "Certaines preuves historiques de fiabilité ne sont "
                                "pas encore disponibles ; cela ne signifie pas que "
                                "la météo est mauvaise."
                            ),
                        },
                    },
                },
                {
                    "status": "weather_refused",
                    "night_date": "2026-08-29",
                    "weather_decision": {
                        "evidence_quality": "insufficient",
                        "admissibility": "refused",
                        "reasons": ["selected_window_uncovered"],
                        "presentation": {
                            "label": "Mission non confirmée",
                            "summary": (
                                "La fenêtre calculée dépasse la période couverte par "
                                "les données météo disponibles."
                            ),
                        },
                    },
                },
            ]
        }
    )

    status: str
    night_date: str | None = None
    target: str | None = None
    catalog_key: str | None = None
    target_common_name: str | None = None
    action: str | None = None
    provenance: Literal["project", "discovery"] | None = None
    imaging_field_id: str | None = None
    selected_acquisition_intent_id: str | None = None
    viable_acquisition_intent_ids: tuple[str, ...] = ()
    acquisition_intent_options: list[TonightAcquisitionIntentOptionModel] = Field(default_factory=list)
    acquisition_intent_assessments: list[
        TonightAcquisitionIntentAssessmentModel
    ] = Field(default_factory=list)
    acquisition_intent_selection_status: (
        AcquisitionIntentSelectionStatus | None
    ) = None
    target_decision_status: TargetDecisionStatus | None = None
    actionability_refusal: ActionabilityRefusalModel | None = None
    shortlist_entries: list[TonightShortlistEntryModel] = Field(
        default_factory=list
    )
    alternatives: list[TonightAlternativeModel] = Field(
        default_factory=list
    )
    recommendation_confidence: float | None = None
    mission_confidence: float | str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    window_start: str | None = None
    window_end: str | None = None
    decision_id: str | None = None
    recommended_hours: float = 0.0
    expected_gain: float = 0.0
    equipment: list[str] = Field(default_factory=list)
    selected_filter: TonightFilterModel | None = None
    astro_quality: TonightAstroQualityModel | None = None
    productivity: TonightProductivityModel | None = None
    dew_risk: TonightDewRiskModel | None = None
    postponement_risk: TonightPostponementRiskModel | None = None
    season: TonightSeasonModel | None = None
    explanation: TonightExplanationModel | None = None
    reasons: list[TonightReasonModel] = Field(default_factory=list)
    tasks: list[TonightTaskModel] = Field(default_factory=list)
    advices: list[TonightAdviceModel] = Field(default_factory=list)
    weather_trust: TonightWeatherTrustModel | None = None
    weather_decision: TonightWeatherDecisionModel | None = None
    rejected_targets: list[TonightRejectedTargetModel] = Field(default_factory=list)
    insufficient_evidence_targets: list[TonightInsufficientEvidenceTargetModel] = Field(
        default_factory=list
    )
    alternative_comparisons: list[RecommendationComparisonResponseModel] = Field(
        default_factory=list
    )
    primary_reasons: list[PrimaryRecommendationReasonResponseModel] = Field(
        default_factory=list
    )
    target_explanations: list[TargetExplanationResponseModel] = Field(
        default_factory=list
    )


def _intent_options(candidate) -> list[dict[str, str]]:
    """Present only viable intents from their first-class field definitions."""
    field_id = getattr(candidate, "imaging_field_id", None)
    viable_ids = getattr(candidate, "viable_acquisition_intent_ids", ())
    if not field_id or not viable_ids:
        return []
    try:
        resolver = build_production_imaging_field_resolver()
        field = resolver.resolve(field_id)
    except ValueError:
        return []
    definitions = {
        intent.acquisition_intent_id: intent
        for intent in field.acquisition_intents
    }
    if any(intent_id not in definitions for intent_id in viable_ids):
        return []
    filter_labels = {"Ha": "Hα", "OIII": "OIII", "SII": "SII"}
    options = []
    for intent_id in viable_ids:
        intent = definitions[intent_id]
        objects = " + ".join(
            resolver.resolve_object(component_id).canonical_name
            for component_id in intent.primary_component_ids
        )
        filter_label = filter_labels.get(intent.filter_type, intent.filter_type)
        options.append({
            "acquisition_intent_id": intent_id,
            "filter_type": intent.filter_type,
            "label": f"{filter_label} · {objects}",
        })
    return options


def _production_service_factory():
    from astro_score import build_durable_tonight_application_service

    return build_durable_tonight_application_service()


def _production_build_mission_input(evaluation, *, profile):
    from astro_score import build_mission_input

    return build_mission_input(evaluation, profile=profile)


def _generate_selection_id() -> str:
    return str(uuid4())


def _accepted_mission_response(mission: NightMission) -> AcceptedMissionResponse:
    if not isinstance(mission, NightMission):
        raise TypeError("Expected NightMission")
    return AcceptedMissionResponse(
        mission_id=mission.mission_id,
        decision_id=mission.decision_id,
        selection_id=mission.selection_id,
        imaging_field_id=mission.imaging_field_id,
        target=mission.target,
        confidence=mission.confidence,
        equipment=list(mission.equipment),
        site_name=mission.site_name,
        window_start=mission.window_start,
        window_end=mission.window_end,
        recommended_hours=float(mission.recommended_hours),
        expected_gain=float(mission.expected_gain),
        selected_filter=(
            AcceptedMissionFilterResponse(
                name=mission.selected_filter.name,
                filter_type=mission.selected_filter.filter_type,
                bandwidth_nm=mission.selected_filter.bandwidth_nm,
            )
            if mission.selected_filter is not None
            else None
        ),
        tasks=[
            AcceptedMissionTaskResponse(
                start=task.start,
                end=task.end,
                title=task.title,
                description=task.description,
                priority=task.priority,
            )
            for task in mission.tasks
        ],
    )


def _assess_shortlist_candidates(
    result,
    *,
    profile,
    weather_snapshot,
    weather_freshness,
    decision_location,
    build_mission_input,
):
    recommendation = getattr(result, "recommendation", None)
    night = getattr(result, "night", None) or {}
    object_evaluations = night.get("object_evaluations", {})
    if recommendation is None or not object_evaluations:
        return {}

    assessments = {}
    for candidate in recommendation.opportunity.shortlist_entries:
        if candidate.catalog_key not in object_evaluations:
            continue
        assessments[candidate.catalog_key] = CandidateAssessment.build(
            candidate=candidate,
            object_evaluations=object_evaluations,
            profile=profile,
            weather_snapshot=weather_snapshot,
            weather_freshness=weather_freshness,
            decision_location=decision_location,
            build_mission_input=build_mission_input,
        )
    return assessments


def _production_weather_provider(latitude: float, longitude: float):
    from astro_score import fetch_weather

    return fetch_weather(latitude, longitude)


def _production_profile_provider():
    from astro_score import load_user_profile

    return load_user_profile()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_CUSTOM_EQUIPMENT_ID = "custom"
_EQUIPMENT_PROJECTION_FIELDS = (
    "optics_manufacturer",
    "optics_model",
    "focal_length_mm",
    "aperture_mm",
    "f_ratio",
    "camera_manufacturer",
    "camera_model",
    "pixel_size_um",
    "sensor_width_px",
    "sensor_height_px",
    "monochrome",
)


def _equipment_configuration_projection(
    profile: dict,
    equipment_id: str,
) -> EquipmentConfigurationModel:
    definition = resolve_equipment_definition(profile, equipment_id)
    if definition is None:
        raise UserProfileError("configuration equipment is unresolved")
    kind = "preset" if equipment_id in EQUIPMENT_PROFILES else "custom"
    name = definition.get("name")
    if not isinstance(name, str) or not name.strip():
        name = " + ".join(
            (
                f"{definition['optics_manufacturer']} {definition['optics_model']}",
                f"{definition['camera_manufacturer']} {definition['camera_model']}",
            )
        )
    return EquipmentConfigurationModel(
        id=equipment_id,
        name=name,
        kind=kind,
        **{field: definition[field] for field in _EQUIPMENT_PROJECTION_FIELDS},
    )


def _preset_equipment_projection() -> list[EquipmentConfigurationModel]:
    return [
        _equipment_configuration_projection({}, equipment_id)
        for equipment_id in sorted(EQUIPMENT_PROFILES)
    ]


def _configuration_projection(profile: dict | None) -> ConfigurationResponse:
    presets = _preset_equipment_projection()
    if profile is None:
        return ConfigurationResponse(
            configured=False,
            profile_revision=None,
            site=None,
            active_equipment_id=None,
            available_equipment=[],
            projects={},
            preset_equipment=presets,
        )

    location = profile.get("location")
    preferences = profile.get("preferences")
    if not isinstance(location, dict) or not isinstance(preferences, dict):
        raise UserProfileError("configuration site is incomplete")
    bortle = preferences.get("bortle")
    # Historical profiles may predate Bortle. Never infer sky quality from
    # coordinates: expose the site for explicit confirmation instead.

    projects = {
        project_id: ProjectConfigurationModel(
            target_hours=project["target_hours"],
            hours=project["hours"],
            importance=project.get("importance"),
            **(
                {"imaging_field_id": project["imaging_field_id"]}
                if "imaging_field_id" in project
                else {}
            ),
            **(
                {
                    "acquisition_intent_targets": project[
                        "acquisition_intent_targets"
                    ]
                }
                if "acquisition_intent_targets" in project
                else {}
            ),
            **(
                {"acquisition_intent_progress": project["acquisition_intent_progress"]}
                if "acquisition_intent_progress" in project else {}
            ),
        )
        for project_id, project in profile.get("projects", {}).items()
    }
    available_ids = profile.get("available_equipment", [])
    site_timezone = LocationTimeResolver.resolve(
        location["latitude"],
        location["longitude"],
    ).timezone_name
    return ConfigurationResponse(
        configured=True,
        **({"needs_configuration_confirmation": True} if bortle is None else {}),
        profile_revision=profile.get("profile_revision", 0),
        site=ConfigurationSiteModel(
            name=location["name"],
            latitude=location["latitude"],
            longitude=location["longitude"],
            bortle=bortle,
            timezone=site_timezone,
        ),
        active_equipment_id=profile.get("active_equipment"),
        available_equipment=[
            _equipment_configuration_projection(profile, equipment_id)
            for equipment_id in available_ids
        ],
        projects=projects,
        preset_equipment=presets,
    )


def _configuration_candidate(
    request: ConfigurationWriteRequest,
    *,
    existing_profile: dict | None = None,
) -> dict:
    candidate = copy.deepcopy(existing_profile) if existing_profile else {}
    equipment = request.equipment
    if equipment.preset_id is not None:
        equipment_id = equipment.preset_id
        if equipment_id not in EQUIPMENT_PROFILES:
            raise UserProfileError("configuration invalid preset equipment")
    else:
        equipment_id = _CUSTOM_EQUIPMENT_ID
        definitions = dict(candidate.get("equipment_definitions", {}))
        definitions[equipment_id] = equipment.custom.model_dump()
        candidate["equipment_definitions"] = definitions

    preferences = dict(candidate.get("preferences", {}))
    preferences["bortle"] = request.site.bortle
    existing_projects = candidate.get("projects", {})
    projects = {}
    for project_id, project in request.projects.items():
        persisted_project = project.model_dump(
            mode="json",
            exclude_none=True,
        )
        previous = existing_projects.get(project_id, {})
        # Keep fields that the configuration UI cannot edit (including
        # historical project metadata), while applying the explicit UI fields.
        persisted_project = {**copy.deepcopy(previous), **persisted_project}
        projects[project_id] = persisted_project

    candidate.update(
        {
            "location": {
                "name": request.site.name,
                "latitude": request.site.latitude,
                "longitude": request.site.longitude,
            },
            "preferences": preferences,
            "available_equipment": (
                list(dict.fromkeys(
                    [equipment_id, *candidate.get("available_equipment", [])]
                ))
                if existing_profile and "setups" in existing_profile
                else [equipment_id]
            ),
            "active_equipment": equipment_id,
            "projects": projects,
        }
    )
    return candidate


def _configuration_validation_code(exc: UserProfileError) -> str:
    message = str(exc).lower()
    if message.startswith("intent_progress_"):
        return message
    if "project" in message or "projet" in message:
        return "configuration_invalid_project"
    if "custom" in message or "equipment_definitions" in message:
        return "configuration_invalid_custom_equipment"
    if "equipment" in message or "matériel" in message:
        return "configuration_invalid_equipment"
    if "bortle" in message:
        return "configuration_invalid_bortle"
    return "configuration_invalid_site"


_CONFIGURATION_INTENT_PROGRESS_CONFLICT_CODES = frozenset({
    "intent_progress_baseline_invalid",
    "intent_progress_baseline_required",
    "intent_progress_baseline_immutable",
    "intent_progress_credits_immutable",
    "intent_progress_field_locked",
    "intent_progress_base_locked",
})


def create_app(
    *,
    service_factory: Callable = _production_service_factory,
    weather_provider: Callable = _production_weather_provider,
    profile_provider: Callable = _production_profile_provider,
    clock: Callable[[], datetime] = _utc_now,
    selection_id_factory: Callable[[], str] = _generate_selection_id,
) -> FastAPI:
    application_version = canonical_version()
    application = FastAPI(title="AstroPilot API", version=application_version)
    resolved_service = None

    @application.exception_handler(RequestValidationError)
    async def configuration_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ):
        if request.url.path != "/v1/configuration":
            return await request_validation_exception_handler(request, exc)
        locations = [tuple(error.get("loc", ())) for error in exc.errors()]
        if any("bortle" in location for location in locations):
            code = "configuration_invalid_bortle"
        elif any("site" in location for location in locations):
            code = "configuration_invalid_site"
        elif any("custom" in location for location in locations):
            code = "configuration_invalid_custom_equipment"
        elif any("equipment" in location for location in locations):
            code = "configuration_invalid_equipment"
        elif any("projects" in location for location in locations):
            code = "configuration_invalid_project"
        else:
            code = "configuration_revision_conflict"
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": code,
                    "message": "The configuration request is invalid.",
                }
            },
        )

    def application_service():
        nonlocal resolved_service
        if resolved_service is None:
            resolved_service = service_factory()
        return resolved_service

    web_root = Path(__file__).with_name("web")
    ui_asset_token = f"{application_version}-{build_identifier()}"
    ui_document = (web_root / "index.html").read_text(encoding="utf-8").replace(
        "__ASTROPILOT_ASSET_TOKEN__",
        ui_asset_token,
    )

    @application.middleware("http")
    async def ui_cache_policy(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path in {"/ui/app.js", "/ui/styles.css"}:
            response.headers["Cache-Control"] = "no-cache"
        return response

    application.mount(
        "/ui",
        StaticFiles(directory=web_root),
        name="tonight-ui",
    )

    @application.get("/", include_in_schema=False)
    def tonight_ui():
        return HTMLResponse(ui_document)

    @application.get("/v1/runtime-identity", include_in_schema=False)
    def runtime_identity():
        return runtime_identity_payload()

    def project_progress_projection(profile: dict, project_id: str) -> dict:
        project = profile.get("projects", {}).get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail={"code": "project_not_found"})
        field_id = project.get("imaging_field_id")
        field = next(
            (item for item in IMAGING_FIELD_DEFINITIONS if item.imaging_field_id == field_id),
            None,
        )
        credits = credit_totals(profile, project_id)
        progress = tuple(project.get("acquisition_intent_progress", ()))
        derived = (derive_acquisition_intent_remaining_progress(
            field,
            tuple(ProjectAcquisitionIntentTarget(**item) for item in project.get("acquisition_intent_targets", ())),
            progress, credits,
        ) if field else ())
        by_base = {item["acquisition_intent_id"]: item for item in progress}
        return {
            "project_id": project_id,
            "profile_revision": profile.get("profile_revision", 0),
            "imaging_field_id": field_id,
            "imaging_fields": [
                {"imaging_field_id": item.imaging_field_id, "display_name": item.display_name,
                 "acquisition_intents": [
                     {"acquisition_intent_id": intent.acquisition_intent_id,
                      "filter_type": intent.filter_type}
                     for intent in item.acquisition_intents
                 ]}
                for item in IMAGING_FIELD_DEFINITIONS
            ],
            "acquisition_intents": [
                {"acquisition_intent_id": intent.acquisition_intent_id,
                 "filter_type": intent.filter_type}
                for intent in field.acquisition_intents
            ] if field else [],
            "acquisition_intent_progress": project.get("acquisition_intent_progress", []),
            "acquisition_intent_targets": project.get("acquisition_intent_targets", []),
            "acquisition_intent_remaining_progress": remaining_progress_projection(derived),
            "intent_progress_breakdown": [
                {"acquisition_intent_id": item.acquisition_intent_id,
                 "base_seconds": base_seconds(by_base.get(item.acquisition_intent_id)),
                 "credits_us": credits.get(item.acquisition_intent_id, 0),
                 "effective_total_seconds": item.acquired_seconds,
                 "remaining_hours": item.remaining_hours}
                for item in derived
            ],
        }

    @application.get("/v1/projects/{project_id}/progress")
    def get_project_progress(project_id: str):
        try:
            if not (get_user_data_dir() / "user_profile.json").exists():
                raise HTTPException(status_code=404, detail={"code": "project_not_found"})
            return project_progress_projection(load_user_profile(), project_id)
        except UserProfileError as exc:
            raise HTTPException(status_code=503, detail={"code": "configuration_corrupt"}) from exc

    @application.put("/v1/projects/{project_id}/progress")
    def put_project_progress(project_id: str, request: ProjectProgressWriteRequest):
        try:
            if not (get_user_data_dir() / "user_profile.json").exists():
                raise HTTPException(status_code=404, detail={"code": "project_not_found"})
            try:
                profile = load_user_profile()
            except UserProfileError as exc:
                raise HTTPException(status_code=503, detail={"code": "configuration_corrupt"}) from exc
            if project_id not in profile.get("projects", {}):
                raise HTTPException(status_code=404, detail={"code": "project_not_found"})
            if request.expected_revision != profile.get("profile_revision", 0):
                raise ProfileRevisionConflictError("profile_revision_conflict")
            project = profile["projects"][project_id]
            if ("imaging_field_id" in request.model_fields_set
                and request.imaging_field_id != project.get("imaging_field_id")
                and any(entry["project_id"] == project_id for entry in load_credits(profile).values())):
                raise HTTPException(status_code=409, detail={"code": "intent_progress_field_locked"})
            for name in (
                "imaging_field_id", "acquisition_intent_progress",
                "acquisition_intent_targets",
            ):
                if name in request.model_fields_set:
                    project[name] = getattr(request, name)
                    if name != "imaging_field_id":
                        project[name] = [
                            item.model_dump() if isinstance(item, BaseModel) else item
                            for item in project[name]
                        ]
            saved = save_user_profile(profile, expected_revision=request.expected_revision)
            return project_progress_projection(saved, project_id)
        except ProfileRevisionConflictError as exc:
            raise HTTPException(status_code=409, detail={"code": "project_revision_conflict"}) from exc
        except UserProfileError as exc:
            code = str(exc) if str(exc).startswith("intent_progress_") else "project_progress_invalid"
            raise HTTPException(status_code=409 if code != "project_progress_invalid" else 422,
                                detail={"code": code}) from exc

    @application.post("/v1/executions/{execution_id}/intent-progress-credit")
    def post_intent_progress_credit(execution_id: str, request: IntentProgressCreditRequest):
        try:
            status, credit, revision = application_service().apply_intent_progress_credit(
                execution_id=execution_id, evidence_ids=request.evidence_ids,
                expected_revision=request.expected_revision,
                confirm_historical_baseline=request.confirm_historical_baseline,
            )
            return {"status": status, "profile_revision": revision, **credit}
        except ProfileRevisionConflictError as exc:
            raise HTTPException(status_code=409, detail={"code": "profile_revision_conflict"}) from exc
        except IntentProgressCreditError as exc:
            code = str(exc)
            raise HTTPException(status_code=409 if code.endswith("conflict") or "baseline" in code else 422,
                                detail={"code": code}) from exc
        except (ExecutionOutcomeApplicationError, DecisionAcceptanceError) as exc:
            raise HTTPException(status_code=422, detail={"code": str(exc)}) from exc
        except UserProfileError as exc:
            code = str(exc)
            if code.startswith("intent_progress_"):
                try:
                    load_user_profile()
                except UserProfileError:
                    pass
                else:
                    raise HTTPException(status_code=409, detail={"code": code}) from exc
            raise HTTPException(status_code=503, detail={"code": "configuration_corrupt"}) from exc

    @application.get(
        "/v1/configuration",
        response_model=ConfigurationResponse,
        response_model_exclude_unset=True,
        summary="Read the first-run user configuration",
    )
    def get_configuration():
        try:
            profile_path = get_user_data_dir() / "user_profile.json"
            if not profile_path.exists():
                return _configuration_projection(None)
            return _configuration_projection(load_user_profile())
        except LocationTimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": exc.code,
                    "message": "The saved site timezone could not be resolved.",
                },
            ) from exc
        except UserProfileError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "configuration_corrupt",
                    "message": "The saved configuration is invalid.",
                },
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "configuration_persistence_error",
                    "message": "The configuration could not be read.",
                },
            ) from exc

    @application.post(
        "/v1/configuration/recover",
        response_model=ConfigurationResponse,
        response_model_exclude_unset=True,
        summary="Recover from an unreadable saved configuration",
    )
    def recover_configuration(
        recovery_request: ConfigurationRecoveryRequest | None = None,
    ):
        del recovery_request
        try:
            quarantine_corrupt_user_profile(
                validate_configuration=_configuration_projection,
            )
            return _configuration_projection(None)
        except (ProfileRecoveryConflictError, LocationTimeError) as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "configuration_recovery_conflict",
                    "message": "The active configuration is no longer corrupt.",
                },
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "configuration_recovery_unavailable",
                    "message": "The configuration could not be recovered.",
                },
            ) from exc

    @application.put(
        "/v1/configuration",
        response_model=ConfigurationResponse,
        response_model_exclude_unset=True,
        summary="Create or replace the first-run user configuration",
    )
    def put_configuration(request: ConfigurationWriteRequest):
        try:
            profile_path = get_user_data_dir() / "user_profile.json"
            try:
                existing_profile = (
                    load_user_profile() if profile_path.exists() else None
                )
            except UserProfileError as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "configuration_corrupt",
                        "message": "The saved configuration is invalid.",
                    },
                ) from exc
            if (
                existing_profile is not None
                and request.expected_revision is None
            ):
                raise ProfileRevisionConflictError(
                    "profile_revision_conflict"
                )
            LocationTimeResolver.resolve(
                request.site.latitude,
                request.site.longitude,
            )
            profile = create_or_replace_user_configuration(
                _configuration_candidate(
                    request,
                    existing_profile=existing_profile,
                ),
                expected_revision=request.expected_revision,
                preserve_legacy_setups="setups" in (existing_profile or {}),
            )
            return _configuration_projection(profile)
        except ProfileRevisionConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "configuration_revision_conflict",
                    "message": (
                        "The configuration changed. Reload it before saving."
                    ),
                },
            ) from exc
        except LocationTimeError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "message": "The site timezone could not be resolved.",
                },
            ) from exc
        except PersistedProfileCorruptError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "configuration_corrupt",
                    "message": "The saved configuration is invalid.",
                },
            ) from exc
        except UserProfileError as exc:
            code = _configuration_validation_code(exc)
            status_code = 409 if code in _CONFIGURATION_INTENT_PROGRESS_CONFLICT_CODES else 422
            raise HTTPException(
                status_code=status_code,
                detail={"code": code, "message": "The configuration request is invalid."},
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "configuration_persistence_error",
                    "message": "The configuration could not be saved.",
                },
            ) from exc

    @application.post(
        "/v1/tonight",
        response_model=TonightResponseModel,
        summary="Recommend tonight's astrophotography mission",
        description=(
            "Evaluates the next available night and returns a transport-safe "
            "mission enriched with Decision Intelligence: astronomical "
            "quality, productivity, operational risks and season context."
        ),
        responses={
            422: {
                "description": "The request or profile location is invalid.",
                "content": {
                    "application/json": {
                        "examples": {
                            "invalid_request": {
                                "summary": "Bortle value outside the range 1-9",
                                "value": {
                                    "detail": [
                                        {
                                            "type": "less_than_equal",
                                            "loc": ["body", "bortle"],
                                            "msg": "Input should be less than or equal to 9",
                                            "input": 12,
                                            "ctx": {"le": 9},
                                        }
                                    ]
                                },
                            },
                            "invalid_profile_location": {
                                "summary": "Invalid location stored in profile",
                                "value": {
                                    "detail": {
                                        "code": "invalid_profile_location",
                                        "message": "Profile location is invalid.",
                                    }
                                },
                            },
                        }
                    }
                },
            },
            503: {
                "description": (
                    "Weather is unavailable, invalid or insufficient, or the "
                    "snapshot is stale, or the tonight forecast is unavailable."
                ),
                "content": {
                    "application/json": {
                        "examples": {
                            "weather_unavailable": {
                                "summary": "Weather provider unavailable",
                                "value": {
                                    "detail": {
                                        "code": "weather_unavailable",
                                        "message": (
                                            "Weather data is temporarily unavailable."
                                        ),
                                    }
                                },
                            },
                            "weather_invalid": {
                                "summary": "Weather response rejected",
                                "value": {
                                    "detail": {
                                        "code": "weather_invalid",
                                        "message": "Weather data failed validation.",
                                    }
                                },
                            },
                            "weather_insufficient": {
                                "summary": "Weather coverage is insufficient",
                                "value": {
                                    "detail": {
                                        "code": "weather_insufficient",
                                        "message": "Weather coverage is insufficient.",
                                    }
                                },
                            },
                            "weather_stale": {
                                "summary": "Weather snapshot is too old",
                                "value": {
                                    "detail": {
                                        "code": "weather_stale",
                                        "message": (
                                            "Weather data is too old for a reliable decision."
                                        ),
                                    }
                                },
                            },
                            "decision_invalid": {
                                "summary": "Decision consistency check failed",
                                "value": {
                                    "detail": {
                                        "code": "decision_invalid",
                                        "message": (
                                            "The decision failed consistency validation."
                                        ),
                                    }
                                },
                            },
                            "location_timezone_unresolved": {
                                "summary": "Location timezone unresolved",
                                "value": {
                                    "detail": {
                                        "code": "location_timezone_unresolved",
                                        "message": (
                                            "The location timezone could not be resolved."
                                        ),
                                    }
                                },
                            },
                            "forecast_unavailable": {
                                "summary": "Tonight forecast unavailable",
                                "value": {
                                    "detail": {
                                        "code": "forecast_unavailable",
                                        "message": (
                                            "Tonight forecast is temporarily unavailable."
                                        ),
                                    }
                                },
                            },
                        }
                    }
                },
            },
        },
    )
    def tonight(request: TonightRequest):
        reference_time_utc = clock()
        try:
            profile = dict(profile_provider())
            requested_location = (
                request.location.model_dump()
                if request.location is not None
                else None
            )
            preliminary_inputs = resolve_tonight_inputs(
                profile,
                location=requested_location,
                bortle=request.bortle,
                equipment=request.equipment,
                availability=None,
            )
            availability = None
            if request.availability is not None:
                site_zone = None
                if request.availability.has_local_wall_time:
                    site_zone = LocationTimeResolver.resolve(
                        preliminary_inputs.location["latitude"],
                        preliminary_inputs.location["longitude"],
                    ).zone
                availability = request.availability.to_domain(
                    site_zone=site_zone
                )
            inputs = resolve_tonight_inputs(
                profile,
                location=requested_location,
                bortle=request.bortle,
                equipment=request.equipment,
                availability=availability,
            )
        except LocalWallTimeError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "message": "The local session availability is invalid.",
                },
            ) from exc
        except LocationTimeError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "message": "The location timezone could not be resolved.",
                },
            ) from exc
        except UserProfileError:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "user_profile_unavailable",
                    "message": (
                        "AstroPilot requires a valid user_profile.json. "
                        "Check ASTROPILOT_DATA_DIR and the profile contents."
                    ),
                },
            )
        except TonightEquipmentSelectionError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "message": (
                        "The requested equipment is unknown or unavailable."
                    ),
                },
            ) from exc
        except ValueError as exc:
            if str(exc).startswith("session_availability_"):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": str(exc),
                        "message": "The local session availability is invalid.",
                    },
                ) from exc
            raise
        location = inputs.location
        profile["location"] = location
        effective_bortle = inputs.bortle

        weather_freshness: WeatherFreshness | None = None
        try:
            weather = weather_provider(
                location["latitude"],
                location["longitude"],
            )
            if weather is not None and not isinstance(weather, WeatherSnapshot):
                raise WeatherIngressError(["invalid_weather_snapshot"])
            if weather is not None:
                weather_freshness = validate_weather_freshness(
                    weather,
                    reference_time_utc=reference_time_utc,
                )
        except WeatherIngressError as exc:
            messages = {
                "weather_insufficient": "Weather coverage is insufficient.",
                "weather_stale": (
                    "Weather data is too old for a reliable decision."
                ),
            }
            message = messages.get(exc.code, "Weather data failed validation.")
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": message},
            ) from exc
        except LocationTimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": exc.code,
                    "message": "The location timezone could not be resolved.",
                },
            ) from exc
        if weather is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "weather_unavailable",
                    "message": "Weather data is temporarily unavailable.",
                },
            )

        try:
            result = application_service().evaluate(
                profile=profile,
                weather=weather,
                reference_time_utc=reference_time_utc,
                equipment=inputs.equipment,
                goal=request.goal,
                target=request.target,
                bortle=effective_bortle,
                availability=inputs.availability,
            )
        except DecisionConsistencyError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": exc.code,
                    "message": "The decision failed consistency validation.",
                },
            ) from exc
        except WeatherWindowCoverageError as exc:
            weather_invalid = "invalid_weather_coverage" in exc.issues
            raise HTTPException(
                status_code=503,
                detail={
                    "code": (
                        "weather_invalid"
                        if weather_invalid
                        else "decision_invalid"
                    ),
                    "message": (
                        "Weather data failed validation."
                        if weather_invalid
                        else "The decision failed consistency validation."
                    ),
                },
            ) from exc
        except (DecisionForecastEvidencePersistenceError, OSError) as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "decision_persistence_unavailable",
                    "message": (
                        "Durable decision persistence is temporarily unavailable."
                    ),
                },
            ) from exc
        if result.status is TonightStatus.FORECAST_UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "forecast_unavailable",
                    "message": "Tonight forecast is temporarily unavailable.",
                },
            )

        weather_decision = None
        candidate_assessments = {}
        weather_coverage_subject = result.mission
        if (
            result.status is TonightStatus.AVAILABLE
            and isinstance(weather, WeatherSnapshot)
        ):
            if weather_coverage_subject is None:
                recommendation = getattr(result, "recommendation", None)
                opportunity = (
                    recommendation.opportunity
                    if recommendation is not None
                    else None
                )
                night = getattr(result, "night", None) or {}
                object_evaluations = night.get("object_evaluations", {})
                primary_evaluation = (
                    object_evaluations.get(opportunity.candidate.catalog_key)
                    if opportunity is not None
                    else None
                )
                if (
                    isinstance(primary_evaluation, dict)
                    and "window" in primary_evaluation
                ):
                    weather_coverage_subject = _production_build_mission_input(
                        primary_evaluation,
                        profile=profile,
                    )
            selected_window_covered = True
            try:
                validate_selected_window_weather_coverage(
                    weather_coverage_subject,
                    weather,
                )
            except WeatherWindowCoverageError as exc:
                issues = set(exc.issues)
                decisional_issues = {
                    "window_starts_before_weather",
                    "window_ends_after_weather",
                }
                if (issues and issues <= decisional_issues) or (
                    weather_coverage_subject is None
                    and issues == {"invalid_mission_window"}
                ):
                    selected_window_covered = False
                else:
                    weather_invalid = "invalid_weather_coverage" in issues
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": (
                                "weather_invalid"
                                if weather_invalid
                                else "decision_invalid"
                            ),
                            "message": (
                                "Weather data failed validation."
                                if weather_invalid
                                else "The decision failed consistency validation."
                            ),
                        },
                    ) from exc

            weather_decision = WeatherTrustDecisionEvaluator.evaluate(
                WeatherTrustEvidence(
                    snapshot=weather,
                    freshness=weather_freshness,
                    selected_window_covered=selected_window_covered,
                    provider_reliability=None,
                ),
                context=WeatherDecisionContext(
                    provider_id=weather.provider,
                    decision_location=WeatherLocation(
                        latitude=location["latitude"],
                        longitude=location["longitude"],
                    ),
                    reliability_context=None,
                ),
            )

            try:
                candidate_assessments = _assess_shortlist_candidates(
                    result,
                    profile=profile,
                    weather_snapshot=weather,
                    weather_freshness=weather_freshness,
                    decision_location=WeatherLocation(
                        latitude=location["latitude"],
                        longitude=location["longitude"],
                    ),
                    build_mission_input=_production_build_mission_input,
                )
            except WeatherWindowCoverageError as exc:
                weather_invalid = "invalid_weather_coverage" in exc.issues
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": (
                            "weather_invalid"
                            if weather_invalid
                            else "decision_invalid"
                        ),
                        "message": (
                            "Weather data failed validation."
                            if weather_invalid
                            else "The decision failed consistency validation."
                        ),
                    },
                ) from exc

        viable_shortlist_catalog_keys = set()
        try:
            for catalog_key, assessment in candidate_assessments.items():
                if CandidateViabilityEvaluator.is_viable(assessment):
                    viable_shortlist_catalog_keys.add(catalog_key)
        except DecisionConsistencyError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": exc.code,
                    "message": "The decision failed consistency validation.",
                },
            ) from exc

        recommendation = getattr(result, "recommendation", None)
        opportunity = (
            recommendation.opportunity
            if recommendation is not None
            else None
        )
        selected_alternatives = select_actionable_alternatives(
            opportunity.shortlist_entries if opportunity is not None else (),
            viable_shortlist_catalog_keys,
            candidate_assessments,
            inputs.availability,
            primary_catalog_key=(
                opportunity.candidate.catalog_key
                if opportunity is not None
                else None
            ),
        )

        target_insufficiencies = []
        if opportunity is not None:
            primary_insufficiency = qualify_primary_evidence_insufficiency(
                candidate=opportunity.candidate,
                weather_decision=weather_decision,
            )
            if primary_insufficiency is not None:
                target_insufficiencies.append(primary_insufficiency)
            for candidate in opportunity.shortlist_entries:
                insufficiency = qualify_candidate_evidence_insufficiency(
                    candidate=candidate,
                    assessment=candidate_assessments.get(candidate.catalog_key),
                )
                if insufficiency is not None:
                    target_insufficiencies.append(insufficiency)

        weather_refused = (
            weather_decision is not None
            and weather_decision.admissibility is WeatherDecisionAdmissibility.REFUSED
        )
        primary_mission_actionable = (
            result.mission is not None
            and result.mission.window_start is not None
            and result.mission.window_end is not None
            and result.mission.window_end > result.mission.window_start
            and result.mission.recommended_hours > 0
        )
        primary_reasons = ()
        primary_reason_entries = ()
        if opportunity is not None and not weather_refused and primary_mission_actionable:
            primary_reasons = opportunity.structured_reasons
            if weather_decision is not None:
                primary_reasons += primary_window_reasons(
                    candidate=opportunity.candidate,
                    weather_decision=weather_decision,
                )
            primary_reason_entries = primary_reason_responses(primary_reasons)

        alternative_reason_sets = ()
        alternative_reason_entries = ()
        if opportunity is not None and selected_alternatives and not weather_refused:
            alternative_reason_sets = tuple(
                candidate_reasons(candidate) + candidate_assessment_reasons(
                    candidate=candidate,
                    assessment=candidate_assessments.get(candidate.catalog_key),
                )
                for candidate in selected_alternatives
            )
            alternative_reason_entries = tuple(
                alternative_reason_responses(reasons)
                for reasons in alternative_reason_sets
            )

        target_explanations = target_explanation_responses(
            build_target_explanations(
                primary=(
                    (opportunity.candidate.catalog_key, primary_reason_entries)
                    if opportunity is not None and not weather_refused and primary_mission_actionable
                    else None
                ),
                alternatives=tuple(
                    (candidate.catalog_key, alternative_reason_entries[index])
                    for index, candidate in enumerate(selected_alternatives)
                ) if not weather_refused else (),
            )
        )

        alternative_comparisons = ()
        if (
            opportunity is not None
            and selected_alternatives
            and not weather_refused
            and primary_mission_actionable
        ):
            alternative_comparisons = build_alternative_comparisons(
                primary_catalog_key=opportunity.candidate.catalog_key,
                primary_reasons=primary_reasons,
                alternatives=tuple(
                    (
                        candidate.catalog_key,
                        alternative_reason_sets[index],
                    )
                    for index, candidate in enumerate(selected_alternatives)
                ),
            )

        payload = TonightResponse.from_result(
            result,
            weather_decision=weather_decision,
            viable_shortlist_catalog_keys=viable_shortlist_catalog_keys,
            selected_alternatives=selected_alternatives,
            alternative_reasons=alternative_reason_entries,
            rejected_targets=map_rejected_targets(result.candidate_rejections),
            insufficient_evidence_targets=map_target_evidence_insufficiencies(
                tuple(target_insufficiencies)
            ),
            alternative_comparisons=alternative_comparisons,
            primary_reasons=primary_reason_entries,
            target_explanations=target_explanations,
        ).to_dict()
        if opportunity is not None:
            payload["acquisition_intent_options"] = _intent_options(
                opportunity.candidate
            )
        for alternative_payload, candidate in zip(
            payload["alternatives"], selected_alternatives
        ):
            alternative_payload.update({
                "imaging_field_id": candidate.imaging_field_id,
                "selected_acquisition_intent_id": candidate.selected_acquisition_intent_id,
                "viable_acquisition_intent_ids": candidate.viable_acquisition_intent_ids,
                "acquisition_intent_selection_status": (
                    candidate.acquisition_intent_selection_status
                ),
                "acquisition_intent_options": _intent_options(candidate),
            })
        register_decision_context = getattr(
            application_service(),
            "register_decision_context",
            None,
        )
        if (
            register_decision_context is not None
            and result.decision_id is not None
            and opportunity is not None
            and result.night is not None
        ):
            object_evaluations = result.night.get("object_evaluations") or {}
            register_decision_context(
                decision_id=result.decision_id,
                recommendation=recommendation,
                night=result.night,
                profile={
                    **profile,
                    "location": inputs.location,
                    "active_equipment": inputs.equipment,
                    "available_equipment": [inputs.equipment],
                },
                availability=inputs.availability,
                primary_catalog_key=(
                    opportunity.candidate.catalog_key
                    if payload["target_decision_status"] == "recommended"
                    else None
                ),
                exposed_alternative_catalog_keys=tuple(
                    candidate.catalog_key for candidate in selected_alternatives
                ),
                explicitly_evaluated_catalog_keys=tuple(
                    key for key in object_evaluations
                    if not (
                        key == opportunity.candidate.catalog_key
                        and payload["target_decision_status"] != "recommended"
                    )
                    and key not in {
                        entry.catalog_key for entry in target_insufficiencies
                    }
                ),
            )

        if isinstance(weather, WeatherSnapshot):
            payload["weather_trust"] = weather.trust_transport(weather_freshness)
        return payload

    @application.post(
        "/v1/decision-selections",
        response_model=UserSelectionResponse,
        summary="Accept or decline an exact Tonight decision",
    )
    def accept_decision(request: UserSelectionRequest):
        selection_id = selection_id_factory()
        if not isinstance(selection_id, str) or not selection_id.strip():
            raise HTTPException(
                status_code=503,
                detail={"code": "decision_acceptance_unavailable"},
            )
        selection = request.to_domain(selection_id=selection_id)
        accept = getattr(application_service(), "accept_idempotently", None)
        if accept is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "decision_acceptance_unavailable"},
            )
        try:
            acceptance = accept(
                selection,
                acceptance_request_id=request.acceptance_request_id,
            )
        except DecisionAcceptanceError as exc:
            code = str(exc)
            raise HTTPException(
                status_code=404 if code == "decision_context_not_found" else 409,
                detail={"code": code},
            ) from exc
        except UserSelectionValidationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": str(exc)},
            ) from exc

        canonical_selection = acceptance.selection
        mission = acceptance.mission
        return UserSelectionResponse(
            status="declined" if mission is None else "accepted",
            mission_id=mission.mission_id if mission is not None else None,
            decision_id=canonical_selection.decision_id,
            selection_id=canonical_selection.selection_id,
            catalog_key=(
                canonical_selection.selected_catalog_key
                if mission is not None
                else None
            ),
            selected_imaging_field_id=(
                canonical_selection.selected_imaging_field_id
                if mission is not None
                else None
            ),
            selected_acquisition_intent_id=(
                canonical_selection.selected_acquisition_intent_id
                if mission is not None
                else None
            ),
            mission=(
                _accepted_mission_response(mission)
                if mission is not None
                else None
            ),
        )

    @application.get(
        "/v1/accepted-mission/current",
        response_model=UserSelectionResponse | None,
        summary="Read the current persisted accepted mission",
    )
    def current_accepted_mission():
        try:
            profile = profile_provider()
            if not isinstance(profile, dict):
                return None
            latest = application_service().latest_accepted_mission(
                profile=profile, now=clock(),
            )
        except (OSError, ValueError, UserProfileError) as exc:
            raise HTTPException(
                status_code=503, detail={"code": "acceptance_lineage_unavailable"},
            ) from exc
        if latest is None:
            return None
        selection, mission = latest
        return UserSelectionResponse(
            status="accepted",
            mission_id=mission.mission_id,
            decision_id=selection.decision_id,
            selection_id=selection.selection_id,
            catalog_key=selection.selected_catalog_key,
            selected_imaging_field_id=selection.selected_imaging_field_id,
            selected_acquisition_intent_id=selection.selected_acquisition_intent_id,
            mission=_accepted_mission_response(mission),
        )

    def execution_response(execution: Execution) -> ExecutionResponse:
        return ExecutionResponse(
            execution_id=execution.execution_id,
            mission_id=execution.mission_id,
            status=execution.status,
            actual_start=execution.actual_start,
            actual_end=execution.actual_end,
            actual_duration=execution.actual_duration,
        )

    def validated_session_credits(profile: dict, service, project_id: str,
                                  intent_id: str, current_aggregate) -> dict:
        try:
            ledger = load_credits(profile)
        except IntentProgressCreditError as exc:
            raise HTTPException(status_code=503, detail={"code": "session_credit_inconsistent"}) from exc
        relevant = {execution_id: entry for execution_id, entry in ledger.items()
                    if (entry["project_id"], entry["acquisition_intent_id"]) == (project_id, intent_id)
                    or execution_id == current_aggregate.execution.execution_id}
        for execution_id, credit in relevant.items():
            try:
                aggregate = (current_aggregate if execution_id == current_aggregate.execution.execution_id
                             else service.load_session(execution_id))
                execution = aggregate.execution if aggregate is not None else None
                mission = service.load_mission(execution.mission_id) if execution is not None else None
                selection = service.load_selection(mission.selection_id) if mission is not None else None
            except (ExecutionOutcomeApplicationError, DecisionAcceptanceError, OSError) as exc:
                raise HTTPException(status_code=503, detail={"code": "session_credit_inconsistent"}) from exc
            if (execution is None or execution.execution_id != execution_id
                or execution.status is not ExecutionStatus.COMPLETED
                or mission is None or mission.mission_id != execution.mission_id
                or selection is None or selection.selection_id != mission.selection_id
                or selection.decision_id != mission.decision_id
                or selection.selected_imaging_field_id != mission.imaging_field_id
                or selection.selected_acquisition_intent_id != mission.acquisition_intent_id):
                raise HTTPException(status_code=503, detail={"code": "session_credit_inconsistent"})
            provenance = {
                "execution_id": execution_id, "mission_id": mission.mission_id,
                "decision_id": mission.decision_id, "selection_id": mission.selection_id,
                "project_id": selection.selected_catalog_key,
                "imaging_field_id": mission.imaging_field_id,
                "acquisition_intent_id": mission.acquisition_intent_id,
            }
            evidence_by_id = {item.evidence_id: item for item in aggregate.evidence}
            durations = []
            for evidence_id in credit["evidence_ids"]:
                evidence = evidence_by_id.get(evidence_id)
                if (not isinstance(evidence, AcquisitionOutcomeEvidence)
                    or evidence.execution_id != execution_id
                    or evidence.usable_integration_duration is None):
                    raise HTTPException(status_code=503, detail={"code": "session_credit_inconsistent"})
                value = duration_us(evidence.usable_integration_duration)
                if value <= 0:
                    raise HTTPException(status_code=503, detail={"code": "session_credit_inconsistent"})
                durations.append(value)
            if (any(credit.get(key) != value for key, value in provenance.items())
                or len(evidence_by_id) != len(aggregate.evidence)
                or durations != credit["usable_durations_us"]
                or sum(durations) != credit["total_duration_us"]):
                raise HTTPException(status_code=503, detail={"code": "session_credit_inconsistent"})
        return relevant

    def session_projection(aggregate, profile: dict) -> dict:
        execution = aggregate.execution
        service = application_service()
        mission = service.load_mission(execution.mission_id)
        if mission is None or mission.mission_id != execution.mission_id:
            raise HTTPException(status_code=503, detail={"code": "mission_provenance_invalid"})
        selection = service.load_selection(mission.selection_id)
        if (selection is None or selection.selection_id != mission.selection_id
            or selection.decision_id != mission.decision_id
            or selection.selected_imaging_field_id != mission.imaging_field_id
            or selection.selected_acquisition_intent_id != mission.acquisition_intent_id):
            raise HTTPException(status_code=503, detail={"code": "mission_provenance_invalid"})
        project_id = selection.selected_catalog_key
        project = profile.get("projects", {}).get(project_id)
        if project is None or project.get("imaging_field_id") != mission.imaging_field_id:
            raise HTTPException(status_code=503, detail={"code": "project_field_mismatch"})
        intent_id = mission.acquisition_intent_id
        credits = validated_session_credits(profile, service, project_id, intent_id, aggregate)
        progress = project_progress_projection(profile, project_id)
        breakdown = next((item for item in progress["intent_progress_breakdown"]
                          if item["acquisition_intent_id"] == intent_id), None)
        derived = next((item for item in progress["acquisition_intent_remaining_progress"]
                        if item["acquisition_intent_id"] == intent_id), None)
        if breakdown is None or derived is None:
            raise HTTPException(status_code=503, detail={"code": "intent_unknown"})
        credit = credits.get(execution.execution_id)
        session_seconds = credit["total_duration_us"] / 1_000_000 if credit else 0
        total = breakdown["effective_total_seconds"]
        baseline = breakdown["base_seconds"]
        if total is not None and total < session_seconds:
            raise HTTPException(status_code=503, detail={"code": "session_credit_inconsistent"})
        # applied_at is immutable on replay. Break timestamp ties by execution ID,
        # never by ledger insertion order (or the order of files on disk).
        before = total
        if credit is not None:
            selected_key = (datetime.fromisoformat(credit["applied_at"]), execution.execution_id)
            prior_us = sum(entry["total_duration_us"] for entry_id, entry in credits.items()
                           if (entry["project_id"], entry["acquisition_intent_id"]) == (project_id, intent_id)
                           and (datetime.fromisoformat(entry["applied_at"]), entry_id) < selected_key)
            before = (baseline or 0) + prior_us / 1_000_000
        after = before + session_seconds if before is not None else None
        return {
            "execution": execution_response(execution).model_dump(mode="json"),
            "mission": _accepted_mission_response(mission).model_dump(mode="json"),
            "mission_id": mission.mission_id,
            "chronology_at": (execution.actual_start or mission.window_start).isoformat(),
            "project_id": project_id,
            "acquisition_intent_id": intent_id,
            "profile_revision": profile.get("profile_revision", 0),
            "evidence": [OutcomeEvidenceResponse(
                evidence_id=item.evidence_id, execution_id=item.execution_id,
                category=item.category, observed_at=item.observed_at, source=item.source,
                actual_capture_duration=getattr(item, "actual_capture_duration", None),
                usable_integration_duration=getattr(item, "usable_integration_duration", None),
            ).model_dump(mode="json") | {
                "usable_integration_duration": (
                    item.usable_integration_duration.total_seconds()
                    if isinstance(item, AcquisitionOutcomeEvidence)
                    and item.usable_integration_duration is not None else None
                ),
            } for item in aggregate.evidence],
            "credit": credit,
            "historical_baseline_seconds": baseline,
            "historical_baseline_confirmed": intent_id in profile.get("intent_progress_baselines", {}).get(project_id, {}),
            "acquired_before_seconds": before,
            "session_credit_seconds": session_seconds,
            "acquired_after_seconds": after,
            "current_acquired_seconds": total,
            "target_hours": derived["target_hours"],
            "remaining_hours": derived["remaining_hours"],
        }

    def read_sessions(mission_id: str | None = None, execution_id: str | None = None):
        try:
            service = application_service()
            if execution_id is not None:
                aggregate = service.load_session(execution_id)
                if aggregate is None:
                    raise HTTPException(status_code=404, detail={"code": "execution_not_found"})
                aggregates = [aggregate]
            else:
                if mission_id is not None and service.load_mission(mission_id) is None:
                    raise HTTPException(status_code=404, detail={"code": "mission_not_found"})
                aggregates = service.list_sessions(mission_id)
            if not aggregates:
                return []
            profile = load_user_profile()
            projections = [session_projection(item, profile) for item in aggregates]
            return sorted(projections, key=lambda item: (
                datetime.fromisoformat(item["chronology_at"]).timestamp(),
                item["execution"]["execution_id"]), reverse=True)
        except ExecutionOutcomeApplicationError as exc:
            raise HTTPException(status_code=503, detail={"code": str(exc)}) from exc
        except UserProfileError as exc:
            raise HTTPException(status_code=503, detail={"code": "configuration_corrupt"}) from exc

    @application.get("/v1/execution-sessions")
    def list_execution_sessions():
        return read_sessions()

    @application.get("/v1/missions/{mission_id}/executions")
    def list_mission_executions(mission_id: str):
        return read_sessions(mission_id=mission_id)

    @application.get("/v1/executions/{execution_id}/session")
    def get_execution_session(execution_id: str):
        return read_sessions(execution_id=execution_id)[0]

    def execution_command(name: str):
        command = getattr(application_service(), name, None)
        if command is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "execution_commands_unavailable"},
            )
        return command

    def raise_execution_command_error(exc: Exception):
        code = str(exc)
        raise HTTPException(
            status_code=(
                404
                if code in {"mission_not_found", "execution_not_found"}
                else 409
            ),
            detail={"code": code},
        ) from exc

    @application.post(
        "/v1/executions",
        response_model=ExecutionResponse,
        summary="Create an execution for an exact mission",
    )
    def create_execution(request: ExecutionCreateRequest):
        try:
            created = execution_command("create_execution")(
                execution_id=request.execution_id,
                mission_id=request.mission_id,
            )
        except ExecutionOutcomeApplicationError as exc:
            raise_execution_command_error(exc)
        return execution_response(created)

    @application.post(
        "/v1/execution-transitions",
        response_model=ExecutionResponse,
        summary="Transition an exact execution",
    )
    def transition_execution(request: ExecutionTransitionRequest):
        try:
            transitioned = execution_command("transition_execution")(
                request.to_domain()
            )
        except (ExecutionOutcomeApplicationError, ExecutionTransitionError) as exc:
            raise_execution_command_error(exc)
        return execution_response(transitioned)

    @application.post(
        "/v1/outcome-evidence",
        response_model=OutcomeEvidenceResponse,
        summary="Record typed evidence for an exact execution",
    )
    def record_outcome_evidence(request: OutcomeEvidenceRequest):
        evidence = request.to_domain()
        try:
            recorded = execution_command("record_outcome_evidence")(
                execution_id=request.execution_id,
                evidence=evidence,
            )
        except ExecutionOutcomeApplicationError as exc:
            raise_execution_command_error(exc)
        return OutcomeEvidenceResponse(
            evidence_id=recorded.evidence_id,
            execution_id=recorded.execution_id,
            category=recorded.category,
            observed_at=recorded.observed_at,
            source=recorded.source,
            actual_capture_duration=getattr(
                recorded,
                "actual_capture_duration",
                None,
            ),
            usable_integration_duration=getattr(
                recorded,
                "usable_integration_duration",
                None,
            ),
        )

    @application.post(
        "/v1/portfolio-credit-applications",
        response_model=PortfolioCreditApplicationResponse,
        summary="Apply validated portfolio credit to an explicit destination",
    )
    def apply_durable_portfolio_credit(
        request: PortfolioCreditApplicationCommand,
    ):
        command = getattr(application_service(), "apply_portfolio_credit", None)
        if command is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "portfolio_credit_application_unavailable"},
            )
        try:
            result = command(
                request.application.to_domain(),
                request.credit.to_domain(),
            )
        except OSError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "portfolio_credit_persistence_unavailable"},
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": str(exc)},
            ) from exc
        except (TypeError, ValueError) as exc:
            code = str(exc)
            raise HTTPException(
                status_code=(
                    404
                    if code in {
                        "execution_not_found",
                        "evidence_not_found",
                        "project_destination_unresolved",
                    }
                    else 409
                ),
                detail={"code": code},
            ) from exc

        applied = result.application
        return PortfolioCreditApplicationResponse(
            outcome=result.outcome,
            application_id=applied.application_id,
            credit_id=applied.credit_id,
            object_name=applied.object_name,
            destination_kind=applied.destination_kind,
            applied_duration=applied.applied_duration,
            applied_at=applied.applied_at,
        )

    return application


app = create_app()
