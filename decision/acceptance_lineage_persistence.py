from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from decision.filtering.selected_filter import SelectedFilter
from decision.intelligence.analysis_result import AnalysisResult
from decision.mission.mission_input import MissionInput
from decision.mission.night_mission import MissionReason, NightMission
from decision.mission.night_planner import NightTask
from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelectionStatus,
)
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


SCHEMA_VERSION = 8
_IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_LEGACY_ROOT_FIELDS = frozenset(
    ("schema_version", "decision_id", "context", "selections", "missions")
)
_ROOT_FIELDS = _LEGACY_ROOT_FIELDS | frozenset(("acceptance_requests",))


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
    AcquisitionIntentSelectionStatus,
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
class AcceptanceRequestMapping:
    acceptance_request_id: str
    selection_id: str
    mission_id: str | None


@dataclass(frozen=True, slots=True)
class DecisionAcceptanceAggregate:
    context: DecisionAcceptanceContext
    selections: tuple[UserSelection, ...] = ()
    missions: tuple[NightMission, ...] = ()
    acceptance_requests: tuple[AcceptanceRequestMapping, ...] = ()

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
    if type(value) is date:
        return {"$type": "date", "value": value.isoformat()}
    if type(value) is timedelta:
        return {
            "$type": "timedelta",
            "microseconds": _duration_microseconds(value),
        }
    if type(value) is SimpleNamespace:
        return {
            "$type": "simple_namespace",
            "attributes": {
                key: _encode(item) for key, item in vars(value).items()
            },
        }
    dataclass_tag = _DATACLASS_TAG_BY_TYPE.get(type(value))
    if dataclass_tag is not None:
        return {
            "$type": "dataclass",
            "class": dataclass_tag,
            "fields": {
                field.name: _encode(getattr(value, field.name))
                for field in fields(value)
                if not (
                    type(value) is Candidate
                    and field.name == "acquisition_intent_remaining_progress"
                )
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


def _decode(value: object, *, schema_version: int = SCHEMA_VERSION) -> object:
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
    if kind == "date":
        document = _exact_mapping(
            value, frozenset(("$type", "value")), "invalid_date_document"
        )
        raw = document["value"]
        if not isinstance(raw, str):
            raise AcceptanceLineageCorruptionError("invalid_date")
        try:
            result = date.fromisoformat(raw)
        except ValueError as error:
            raise AcceptanceLineageCorruptionError("invalid_date") from error
        if result.isoformat() != raw:
            raise AcceptanceLineageCorruptionError("invalid_date")
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
    if kind == "simple_namespace":
        document = _exact_mapping(
            value,
            frozenset(("$type", "attributes")),
            "invalid_simple_namespace_document",
        )
        attributes = document["attributes"]
        if type(attributes) is not dict or any(
            not isinstance(key, str) for key in attributes
        ):
            raise AcceptanceLineageCorruptionError(
                "invalid_simple_namespace_attributes"
            )
        return SimpleNamespace(
            **{
                key: _decode(item, schema_version=schema_version)
                for key, item in attributes.items()
            }
        )
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
        restored = [
            _decode(item, schema_version=schema_version) for item in items
        ]
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
        return {
            key: _decode(item, schema_version=schema_version)
            for key, item in items.items()
        }
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
        if dataclass_type is Candidate:
            expected -= frozenset(("acquisition_intent_remaining_progress",))
        if dataclass_type is Candidate and schema_version <= 5:
            expected = expected - frozenset((
                "selected_acquisition_intent_id",
                "viable_acquisition_intent_ids",
                "acquisition_intent_selection_status",
            ))
        if dataclass_type is Candidate and schema_version in (1, 2):
            expected = expected - frozenset(("imaging_field_id",))
        if dataclass_type is UserSelection and schema_version in (1, 2, 3):
            expected = expected - frozenset(("selected_imaging_field_id",))
        if dataclass_type is UserSelection and schema_version <= 6:
            expected = expected - frozenset((
                "selected_acquisition_intent_id",
            ))
        if dataclass_type in (MissionInput, NightMission) and schema_version <= 4:
            expected = expected - frozenset(("imaging_field_id",))
        if dataclass_type in (MissionInput, NightMission) and schema_version <= 7:
            expected = expected - frozenset(("acquisition_intent_id",))
        supplied = _exact_mapping(
            supplied, expected, "invalid_dataclass_fields"
        )
        restored_fields = {
            name: _decode(item, schema_version=schema_version)
            for name, item in supplied.items()
        }
        if dataclass_type is Candidate and schema_version <= 5:
            restored_fields.update(
                selected_acquisition_intent_id=None,
                viable_acquisition_intent_ids=(),
                acquisition_intent_selection_status=None,
            )
        if dataclass_type is Candidate and schema_version in (1, 2):
            restored_fields["imaging_field_id"] = None
        if dataclass_type is UserSelection and schema_version in (1, 2, 3):
            restored_fields["selected_imaging_field_id"] = None
        if dataclass_type is UserSelection and schema_version <= 6:
            restored_fields["selected_acquisition_intent_id"] = None
        if dataclass_type in (MissionInput, NightMission) and schema_version <= 4:
            restored_fields["imaging_field_id"] = None
        if dataclass_type in (MissionInput, NightMission) and schema_version <= 7:
            restored_fields["acquisition_intent_id"] = None
        try:
            return dataclass_type(**restored_fields)
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


def _typed_value(
    document: object,
    expected_type: type,
    code: str,
    *,
    schema_version: int = SCHEMA_VERSION,
):
    value = _decode(document, schema_version=schema_version)
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
    *,
    schema_version: int = SCHEMA_VERSION,
) -> DecisionAcceptanceContext:
    return _typed_value(
        document,
        DecisionAcceptanceContext,
        "invalid_decision_acceptance_context",
        schema_version=schema_version,
    )


def serialize_user_selection(selection: UserSelection) -> dict:
    return _typed_document(selection, UserSelection, "invalid_user_selection")


def deserialize_user_selection(
    document: object,
    *,
    schema_version: int = SCHEMA_VERSION,
) -> UserSelection:
    return _typed_value(
        document,
        UserSelection,
        "invalid_user_selection",
        schema_version=schema_version,
    )


def serialize_night_mission(mission: NightMission) -> dict:
    return _typed_document(mission, NightMission, "invalid_night_mission")


def deserialize_night_mission(
    document: object,
    *,
    schema_version: int = SCHEMA_VERSION,
) -> NightMission:
    return _typed_value(
        document,
        NightMission,
        "invalid_night_mission",
        schema_version=schema_version,
    )


def _validate_aggregate(
    aggregate: DecisionAcceptanceAggregate,
    *,
    enforce_imaging_field_consistency: bool = True,
    enforce_acquisition_intent_consistency: bool = True,
) -> None:
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
    mission_by_id = {}
    for mission in aggregate.missions:
        mission_id = validate_lineage_identity(mission.mission_id, field="mission_id")
        if mission.decision_id != decision_id:
            raise AcceptanceLineageCorruptionError("mission_decision_mismatch")
        if mission.selection_id not in selection_by_id:
            raise AcceptanceLineageCorruptionError("mission_selection_not_found")
        if (
            selection_by_id[mission.selection_id].source
            is UserSelectionSource.DECLINED
        ):
            raise AcceptanceLineageCorruptionError(
                "declined_selection_mission_conflict"
            )
        if enforce_imaging_field_consistency and (
            mission.imaging_field_id
            != selection_by_id[mission.selection_id].selected_imaging_field_id
        ):
            raise AcceptanceLineageCorruptionError(
                "mission_imaging_field_mismatch"
            )
        if enforce_acquisition_intent_consistency and (
            mission.acquisition_intent_id
            != selection_by_id[
                mission.selection_id
            ].selected_acquisition_intent_id
        ):
            raise AcceptanceLineageCorruptionError(
                "mission_acquisition_intent_mismatch"
            )
        if mission_id in mission_by_id:
            raise AcceptanceLineageCorruptionError("duplicate_mission_id")
        mission_by_id[mission_id] = mission
    request_ids = set()
    for request in aggregate.acceptance_requests:
        if type(request) is not AcceptanceRequestMapping:
            raise AcceptanceLineageCorruptionError(
                "invalid_acceptance_request_mapping"
            )
        request_id = validate_lineage_identity(
            request.acceptance_request_id,
            field="acceptance_request_id",
        )
        if request_id in request_ids:
            raise AcceptanceLineageCorruptionError(
                "duplicate_acceptance_request_id"
            )
        request_ids.add(request_id)
        selection = selection_by_id.get(request.selection_id)
        if selection is None:
            raise AcceptanceLineageCorruptionError(
                "acceptance_request_selection_not_found"
            )
        if request.mission_id is None:
            if selection.source is not UserSelectionSource.DECLINED:
                raise AcceptanceLineageCorruptionError(
                    "acceptance_request_mission_required"
                )
            continue
        mission = mission_by_id.get(request.mission_id)
        if mission is None:
            raise AcceptanceLineageCorruptionError(
                "acceptance_request_mission_not_found"
            )
        if mission.selection_id != selection.selection_id:
            raise AcceptanceLineageCorruptionError(
                "acceptance_request_provenance_mismatch"
            )
        if selection.source is UserSelectionSource.DECLINED:
            raise AcceptanceLineageCorruptionError(
                "declined_selection_mission_conflict"
            )


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
        "acceptance_requests": {
            item.acceptance_request_id: {
                "selection_id": item.selection_id,
                "mission_id": item.mission_id,
            }
            for item in aggregate.acceptance_requests
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
    if type(payload) is not dict:
        raise AcceptanceLineageCorruptionError("invalid_root_fields")
    version = payload.get("schema_version")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version not in (1, 2, 3, 4, 5, 6, 7, SCHEMA_VERSION)
    ):
        raise AcceptanceLineageCorruptionError("invalid_schema_version")
    root = _exact_mapping(
        payload,
        _LEGACY_ROOT_FIELDS if version == 1 else _ROOT_FIELDS,
        "invalid_root_fields",
    )
    stored_decision_id = validate_lineage_identity(
        root["decision_id"], field="decision_id"
    )
    if decision_id is not None:
        expected = validate_lineage_identity(decision_id, field="decision_id")
        if stored_decision_id != expected:
            raise AcceptanceLineageCorruptionError("decision_id_mismatch")
    context = deserialize_decision_acceptance_context(
        root["context"],
        schema_version=version,
    )
    selections_document = root["selections"]
    missions_document = root["missions"]
    acceptance_requests_document = (
        {} if version == 1 else root["acceptance_requests"]
    )
    if type(selections_document) is not dict:
        raise AcceptanceLineageCorruptionError("invalid_selections")
    if type(missions_document) is not dict:
        raise AcceptanceLineageCorruptionError("invalid_missions")
    if type(acceptance_requests_document) is not dict:
        raise AcceptanceLineageCorruptionError("invalid_acceptance_requests")
    selections = []
    for identity, item in selections_document.items():
        validate_lineage_identity(identity, field="selection_id")
        selection = deserialize_user_selection(item, schema_version=version)
        if selection.selection_id != identity:
            raise AcceptanceLineageCorruptionError("selection_id_mismatch")
        selections.append(selection)
    missions = []
    for identity, item in missions_document.items():
        validate_lineage_identity(identity, field="mission_id")
        mission = deserialize_night_mission(item, schema_version=version)
        if mission.mission_id != identity:
            raise AcceptanceLineageCorruptionError("mission_id_mismatch")
        missions.append(mission)
    acceptance_requests = []
    for identity, item in acceptance_requests_document.items():
        validate_lineage_identity(identity, field="acceptance_request_id")
        mapping = _exact_mapping(
            item,
            frozenset(("selection_id", "mission_id")),
            "invalid_acceptance_request_mapping",
        )
        selection_id = validate_lineage_identity(
            mapping["selection_id"], field="selection_id"
        )
        mission_id = mapping["mission_id"]
        if mission_id is not None:
            mission_id = validate_lineage_identity(
                mission_id, field="mission_id"
            )
        acceptance_requests.append(AcceptanceRequestMapping(
            acceptance_request_id=identity,
            selection_id=selection_id,
            mission_id=mission_id,
        ))
    aggregate = DecisionAcceptanceAggregate(
        context=context,
        selections=tuple(selections),
        missions=tuple(missions),
        acceptance_requests=tuple(acceptance_requests),
    )
    if aggregate.decision_id != stored_decision_id:
        raise AcceptanceLineageCorruptionError("context_decision_mismatch")
    _validate_aggregate(
        aggregate,
        enforce_imaging_field_consistency=version >= 5,
        enforce_acquisition_intent_consistency=version >= 8,
    )
    return aggregate
