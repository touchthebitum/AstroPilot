from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timedelta

from decision.filtering.selected_filter import SelectedFilter
from decision.intelligence.analysis_result import AnalysisResult
from decision.mission.mission_input import MissionInput
from decision.mission.night_mission import MissionReason, NightMission
from decision.mission.night_planner import NightTask
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.context.decision_context import DecisionContext
from decision.models.context.equipment_context import EquipmentContext
from decision.models.context.portfolio_context import PortfolioContext
from decision.models.context.preferences_context import PreferencesContext
from decision.models.context.session_context import SessionContext
from decision.models.context.site_context import SiteContext
from decision.models.context.sky_context import SkyContext
from decision.models.context.weather_context import WeatherContext
from decision.models.decision_summary import DecisionSummary
from decision.models.equipment.camera import Camera
from decision.models.equipment.imaging_filter import ImagingFilter
from decision.models.equipment.imaging_optics import ImagingOptics
from decision.models.equipment.imaging_setup import ImagingSetup
from decision.models.equipment.mount import Mount
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.models.sky.celestial_object import CelestialObject
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.night_productivity.night_productivity_result import (
    NightProductivityResult,
)
from decision.night_productivity.night_slice import NightSlice
from decision.night_productivity.night_timeline import NightTimeline
from decision.night_productivity.night_window import NightWindow
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.opportunity.opportunity_reason import OpportunityReason
from decision.quality.astro_quality_result import AstroQualityResult
from decision.quality.dew_risk_result import DewRiskResult
from decision.recommendation.recommendation import Recommendation
from decision.risk.project_risk_context import ProjectRiskContext
from decision.risk.risk_report import RiskReport
from decision.services.decision_acceptance_application import (
    DecisionAcceptanceContext,
)
from decision.services.user_selection_validator import (
    UserSelectionDecisionContext,
)
from decision.weather.weather_forecast import WeatherForecast


SCHEMA_VERSION = 1
_IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_ROOT_FIELDS = frozenset(
    ("schema_version", "decision_id", "context", "selections", "missions")
)


class AcceptanceLineagePersistenceError(ValueError):
    pass


class AcceptanceLineageNotFoundError(AcceptanceLineagePersistenceError):
    pass


class AcceptanceLineageConflictError(AcceptanceLineagePersistenceError):
    pass


class AcceptanceLineageCorruptionError(AcceptanceLineagePersistenceError):
    pass


_DATACLASS_TYPES = (
    DecisionAcceptanceContext,
    UserSelectionDecisionContext,
    Recommendation,
    Opportunity,
    OpportunityReason,
    Candidate,
    DecisionContext,
    SessionContext,
    SiteContext,
    EquipmentContext,
    WeatherContext,
    SkyContext,
    PortfolioContext,
    PreferencesContext,
    ImagingSetup,
    Mount,
    ImagingOptics,
    Camera,
    ImagingFilter,
    CelestialObject,
    DecisionSummary,
    SessionAvailability,
    UserSelection,
    NightMission,
    MissionReason,
    MissionInput,
    NightTask,
    RiskReport,
    ProjectRiskContext,
    AnalysisResult,
    NightProductivityResult,
    NightWindow,
    NightTimeline,
    NightSlice,
    AstroQualityResult,
    DewRiskResult,
    SelectedFilter,
    WeatherForecast,
)
_ENUM_TYPES = (
    Action,
    CandidateProvenance,
    SessionAvailabilityMode,
    UserSelectionSource,
)
_DATACLASS_BY_TAG = {
    f"{value.__module__}.{value.__qualname__}": value
    for value in _DATACLASS_TYPES
}
_DATACLASS_TAG_BY_TYPE = {
    value: tag for tag, value in _DATACLASS_BY_TAG.items()
}
_ENUM_BY_TAG = {
    f"{value.__module__}.{value.__qualname__}": value
    for value in _ENUM_TYPES
}
_ENUM_TAG_BY_TYPE = {value: tag for tag, value in _ENUM_BY_TAG.items()}


@dataclass(frozen=True, slots=True)
class DecisionAcceptanceAggregate:
    context: DecisionAcceptanceContext
    selections: tuple[UserSelection, ...] = ()
    missions: tuple[NightMission, ...] = ()

    @property
    def decision_id(self) -> str:
        return self.context.decision_context.decision_id


def validate_lineage_identity(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _IDENTITY_PATTERN.fullmatch(value) is None:
        raise AcceptanceLineageCorruptionError(f"invalid_{field}")
    return value


def _duration_microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def _encode(value: object) -> object:
    enum_tag = _ENUM_TAG_BY_TYPE.get(type(value))
    if enum_tag is not None:
        return {"$type": "enum", "class": enum_tag, "value": value.value}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AcceptanceLineageCorruptionError("non_finite_number")
        return value
    if type(value) is datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise AcceptanceLineageCorruptionError("datetime_timezone_required")
        return {"$type": "datetime", "value": value.isoformat()}
    if type(value) is timedelta:
        return {
            "$type": "timedelta",
            "microseconds": _duration_microseconds(value),
        }
    dataclass_tag = _DATACLASS_TAG_BY_TYPE.get(type(value))
    if dataclass_tag is not None:
        return {
            "$type": "dataclass",
            "class": dataclass_tag,
            "fields": {
                field.name: _encode(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [_encode(item) for item in value]}
    if isinstance(value, list):
        return {"$type": "list", "items": [_encode(item) for item in value]}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise AcceptanceLineageCorruptionError("mapping_key_must_be_string")
        return {
            "$type": "mapping",
            "items": {key: _encode(item) for key, item in value.items()},
        }
    raise AcceptanceLineageCorruptionError(
        f"unsupported_typed_value:{type(value).__module__}.{type(value).__qualname__}"
    )


def _exact_mapping(
    value: object,
    expected_fields: frozenset[str],
    code: str,
) -> dict:
    if type(value) is not dict or set(value) != expected_fields:
        raise AcceptanceLineageCorruptionError(code)
    return value


def _decode(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AcceptanceLineageCorruptionError("non_finite_number")
        return value
    if type(value) is not dict:
        raise AcceptanceLineageCorruptionError("invalid_typed_value")
    kind = value.get("$type")
    if kind == "datetime":
        document = _exact_mapping(
            value, frozenset(("$type", "value")), "invalid_datetime_document"
        )
        raw = document["value"]
        if not isinstance(raw, str):
            raise AcceptanceLineageCorruptionError("invalid_datetime")
        try:
            result = datetime.fromisoformat(raw)
        except ValueError as error:
            raise AcceptanceLineageCorruptionError("invalid_datetime") from error
        if result.tzinfo is None or result.utcoffset() is None:
            raise AcceptanceLineageCorruptionError("invalid_datetime")
        return result
    if kind == "timedelta":
        document = _exact_mapping(
            value,
            frozenset(("$type", "microseconds")),
            "invalid_timedelta_document",
        )
        raw = document["microseconds"]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise AcceptanceLineageCorruptionError("invalid_timedelta")
        try:
            return timedelta(microseconds=raw)
        except OverflowError as error:
            raise AcceptanceLineageCorruptionError("invalid_timedelta") from error
    if kind == "enum":
        document = _exact_mapping(
            value,
            frozenset(("$type", "class", "value")),
            "invalid_enum_document",
        )
        enum_type = _ENUM_BY_TAG.get(document["class"])
        if enum_type is None:
            raise AcceptanceLineageCorruptionError("unsupported_enum_type")
        try:
            return enum_type(document["value"])
        except (TypeError, ValueError) as error:
            raise AcceptanceLineageCorruptionError("invalid_enum_value") from error
    if kind in {"tuple", "list"}:
        document = _exact_mapping(
            value,
            frozenset(("$type", "items")),
            f"invalid_{kind}_document",
        )
        items = document["items"]
        if not isinstance(items, list):
            raise AcceptanceLineageCorruptionError(f"invalid_{kind}_items")
        restored = [_decode(item) for item in items]
        return tuple(restored) if kind == "tuple" else restored
    if kind == "mapping":
        document = _exact_mapping(
            value,
            frozenset(("$type", "items")),
            "invalid_mapping_document",
        )
        items = document["items"]
        if type(items) is not dict or any(not isinstance(key, str) for key in items):
            raise AcceptanceLineageCorruptionError("invalid_mapping_items")
        return {key: _decode(item) for key, item in items.items()}
    if kind == "dataclass":
        document = _exact_mapping(
            value,
            frozenset(("$type", "class", "fields")),
            "invalid_dataclass_document",
        )
        dataclass_type = _DATACLASS_BY_TAG.get(document["class"])
        if dataclass_type is None:
            raise AcceptanceLineageCorruptionError("unsupported_dataclass_type")
        supplied = document["fields"]
        expected = frozenset(field.name for field in fields(dataclass_type))
        supplied = _exact_mapping(
            supplied, expected, "invalid_dataclass_fields"
        )
        try:
            return dataclass_type(
                **{name: _decode(item) for name, item in supplied.items()}
            )
        except AcceptanceLineagePersistenceError:
            raise
        except (TypeError, ValueError) as error:
            raise AcceptanceLineageCorruptionError(
                "invalid_dataclass_value"
            ) from error
    raise AcceptanceLineageCorruptionError("unsupported_typed_value")


def _typed_document(value: object, expected_type: type, code: str) -> dict:
    if type(value) is not expected_type:
        raise AcceptanceLineageCorruptionError(code)
    encoded = _encode(value)
    if type(encoded) is not dict:
        raise AcceptanceLineageCorruptionError(code)
    return encoded


def _typed_value(document: object, expected_type: type, code: str):
    value = _decode(document)
    if type(value) is not expected_type:
        raise AcceptanceLineageCorruptionError(code)
    return value


def serialize_decision_acceptance_context(
    context: DecisionAcceptanceContext,
) -> dict:
    return _typed_document(
        context,
        DecisionAcceptanceContext,
        "invalid_decision_acceptance_context",
    )


def deserialize_decision_acceptance_context(
    document: object,
) -> DecisionAcceptanceContext:
    return _typed_value(
        document,
        DecisionAcceptanceContext,
        "invalid_decision_acceptance_context",
    )


def serialize_user_selection(selection: UserSelection) -> dict:
    return _typed_document(selection, UserSelection, "invalid_user_selection")


def deserialize_user_selection(document: object) -> UserSelection:
    return _typed_value(document, UserSelection, "invalid_user_selection")


def serialize_night_mission(mission: NightMission) -> dict:
    return _typed_document(mission, NightMission, "invalid_night_mission")


def deserialize_night_mission(document: object) -> NightMission:
    return _typed_value(document, NightMission, "invalid_night_mission")


def _validate_aggregate(aggregate: DecisionAcceptanceAggregate) -> None:
    decision_id = validate_lineage_identity(
        aggregate.decision_id, field="decision_id"
    )
    selection_by_id = {}
    for selection in aggregate.selections:
        selection_id = validate_lineage_identity(
            selection.selection_id, field="selection_id"
        )
        if selection.decision_id != decision_id:
            raise AcceptanceLineageCorruptionError("selection_decision_mismatch")
        if selection_id in selection_by_id:
            raise AcceptanceLineageCorruptionError("duplicate_selection_id")
        selection_by_id[selection_id] = selection
    mission_ids = set()
    for mission in aggregate.missions:
        mission_id = validate_lineage_identity(mission.mission_id, field="mission_id")
        if mission.decision_id != decision_id:
            raise AcceptanceLineageCorruptionError("mission_decision_mismatch")
        if mission.selection_id not in selection_by_id:
            raise AcceptanceLineageCorruptionError("mission_selection_not_found")
        if mission_id in mission_ids:
            raise AcceptanceLineageCorruptionError("duplicate_mission_id")
        mission_ids.add(mission_id)


def serialize_decision_acceptance_aggregate(
    aggregate: DecisionAcceptanceAggregate,
) -> str:
    if type(aggregate) is not DecisionAcceptanceAggregate:
        raise AcceptanceLineageCorruptionError("invalid_aggregate")
    _validate_aggregate(aggregate)
    document = {
        "schema_version": SCHEMA_VERSION,
        "decision_id": aggregate.decision_id,
        "context": serialize_decision_acceptance_context(aggregate.context),
        "selections": {
            item.selection_id: serialize_user_selection(item)
            for item in aggregate.selections
        },
        "missions": {
            item.mission_id: serialize_night_mission(item)
            for item in aggregate.missions
        },
    }
    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise AcceptanceLineageCorruptionError("invalid_json_document") from error


def _reject_json_constant(value: str):
    raise ValueError(f"invalid_json_constant:{value}")


def deserialize_decision_acceptance_aggregate(
    document: str,
    *,
    decision_id: str | None = None,
) -> DecisionAcceptanceAggregate:
    if not isinstance(document, str):
        raise AcceptanceLineageCorruptionError("invalid_json_document")
    try:
        payload = json.loads(document, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise AcceptanceLineageCorruptionError("invalid_json_document") from error
    root = _exact_mapping(payload, _ROOT_FIELDS, "invalid_root_fields")
    version = root["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise AcceptanceLineageCorruptionError("invalid_schema_version")
    stored_decision_id = validate_lineage_identity(
        root["decision_id"], field="decision_id"
    )
    if decision_id is not None:
        expected = validate_lineage_identity(decision_id, field="decision_id")
        if stored_decision_id != expected:
            raise AcceptanceLineageCorruptionError("decision_id_mismatch")
    context = deserialize_decision_acceptance_context(root["context"])
    selections_document = root["selections"]
    missions_document = root["missions"]
    if type(selections_document) is not dict:
        raise AcceptanceLineageCorruptionError("invalid_selections")
    if type(missions_document) is not dict:
        raise AcceptanceLineageCorruptionError("invalid_missions")
    selections = []
    for identity, item in selections_document.items():
        validate_lineage_identity(identity, field="selection_id")
        selection = deserialize_user_selection(item)
        if selection.selection_id != identity:
            raise AcceptanceLineageCorruptionError("selection_id_mismatch")
        selections.append(selection)
    missions = []
    for identity, item in missions_document.items():
        validate_lineage_identity(identity, field="mission_id")
        mission = deserialize_night_mission(item)
        if mission.mission_id != identity:
            raise AcceptanceLineageCorruptionError("mission_id_mismatch")
        missions.append(mission)
    aggregate = DecisionAcceptanceAggregate(
        context=context,
        selections=tuple(selections),
        missions=tuple(missions),
    )
    if aggregate.decision_id != stored_decision_id:
        raise AcceptanceLineageCorruptionError("context_decision_mismatch")
    _validate_aggregate(aggregate)
    return aggregate
