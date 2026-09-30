from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import AbstractContextManager
from datetime import datetime
from enum import Enum
from typing import Protocol, TypeVar

from decision.field_observation import (
    CaptureMethod,
    CloudState,
    Confidence,
    FieldObservation,
    HfrUnit,
    ObservationProvenance,
    ObservationQuality,
    ObservationSourceType,
    ObservedAcquisition,
    ObservedConditions,
    ObservedTechnical,
    QualityFlag,
    SeeingCondition,
    StopReason,
    SurfaceCondition,
    Transparency,
    validate_observation_identity,
)


SCHEMA_VERSION = 2
DOMAIN_VERSION = "field_observation.v1"
_ROOT_V2_FIELDS = frozenset(("schema_version", "domain_version", "observation"))
_OBSERVATION_V2_FIELDS = frozenset(
    (
        "observation_id",
        "decision_id",
        "execution_id",
        "observed_at_utc",
        "recorded_at_utc",
        "supersedes_observation_id",
        "conditions",
        "acquisition",
        "technical",
        "provenance",
        "quality",
    )
)
_CONDITION_FIELDS = frozenset(
    (
        "temperature_c",
        "relative_humidity_percent",
        "cloud_state",
        "transparency",
        "seeing",
        "wind_speed_kmh",
        "surface_condition",
        "moon_halo",
    )
)
_ACQUISITION_FIELDS = frozenset(
    ("attempted_frames", "usable_frames", "stop_reason")
)
_TECHNICAL_FIELDS = frozenset(
    (
        "hfr",
        "hfr_unit",
        "sky_background",
        "sky_background_unit",
        "guiding_rms_arcsec",
    )
)
_PROVENANCE_FIELDS = frozenset(
    ("source_type", "source_id", "capture_method", "imported_at_utc")
)
_QUALITY_FIELDS = frozenset(("confidence", "flags"))
_ROOT_V1_FIELDS = frozenset(("schema_version", "observation"))
_OBSERVATION_V1_FIELDS = frozenset(
    (
        "observation_id",
        "execution_id",
        "observed_at_utc",
        "cloud_condition",
        "transparency",
        "seeing",
        "dew_detected",
    )
)


class FieldObservationPersistenceError(ValueError):
    pass


class FieldObservationStore(Protocol):
    def save(self, *, observation: FieldObservation) -> bool: ...

    def load(self, *, observation_id: str) -> FieldObservation | None: ...

    def list_by_decision(self, *, decision_id: str) -> list[FieldObservation]: ...

    def list_by_execution(self, *, execution_id: str) -> list[FieldObservation]: ...

    def active_observation_lease(
        self,
        *,
        observation_id: str,
    ) -> AbstractContextManager[FieldObservation]: ...


def _enum_value(value: Enum | None) -> str | None:
    return None if value is None else value.value


def _datetime_value(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def serialize_field_observation(observation: FieldObservation) -> str:
    if type(observation) is not FieldObservation:
        raise FieldObservationPersistenceError("invalid_field_observation")
    if observation.legacy_lineage_incomplete:
        raise FieldObservationPersistenceError(
            "legacy_field_observation_read_only"
        )
    document = {
        "schema_version": SCHEMA_VERSION,
        "domain_version": DOMAIN_VERSION,
        "observation": {
            "observation_id": observation.observation_id,
            "decision_id": observation.decision_id,
            "execution_id": observation.execution_id,
            "observed_at_utc": observation.observed_at_utc.isoformat(),
            "recorded_at_utc": observation.recorded_at_utc.isoformat(),
            "supersedes_observation_id": (
                observation.supersedes_observation_id
            ),
            "conditions": {
                "temperature_c": observation.conditions.temperature_c,
                "relative_humidity_percent": (
                    observation.conditions.relative_humidity_percent
                ),
                "cloud_state": _enum_value(observation.conditions.cloud_state),
                "transparency": _enum_value(
                    observation.conditions.transparency
                ),
                "seeing": _enum_value(observation.conditions.seeing),
                "wind_speed_kmh": observation.conditions.wind_speed_kmh,
                "surface_condition": _enum_value(
                    observation.conditions.surface_condition
                ),
                "moon_halo": observation.conditions.moon_halo,
            },
            "acquisition": {
                "attempted_frames": observation.acquisition.attempted_frames,
                "usable_frames": observation.acquisition.usable_frames,
                "stop_reason": _enum_value(observation.acquisition.stop_reason),
            },
            "technical": {
                "hfr": observation.technical.hfr,
                "hfr_unit": _enum_value(observation.technical.hfr_unit),
                "sky_background": observation.technical.sky_background,
                "sky_background_unit": (
                    observation.technical.sky_background_unit
                ),
                "guiding_rms_arcsec": (
                    observation.technical.guiding_rms_arcsec
                ),
            },
            "provenance": {
                "source_type": observation.provenance.source_type.value,
                "source_id": observation.provenance.source_id,
                "capture_method": observation.provenance.capture_method.value,
                "imported_at_utc": _datetime_value(
                    observation.provenance.imported_at_utc
                ),
            },
            "quality": {
                "confidence": observation.quality.confidence.value,
                "flags": [flag.value for flag in observation.quality.flags],
            },
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
        raise FieldObservationPersistenceError(
            "invalid_field_observation"
        ) from error


def _mapping(
    value: object,
    *,
    fields: frozenset[str],
    code: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise FieldObservationPersistenceError(code)
    return value


def _datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise FieldObservationPersistenceError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise FieldObservationPersistenceError(f"invalid_{field}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FieldObservationPersistenceError(f"invalid_{field}")
    return parsed


def _optional_datetime(value: object, *, field: str) -> datetime | None:
    return None if value is None else _datetime(value, field=field)


EnumType = TypeVar("EnumType", bound=Enum)


def _enum(
    value: object,
    enum_type: type[EnumType],
    *,
    field: str,
    optional: bool = True,
) -> EnumType | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise FieldObservationPersistenceError(f"invalid_{field}")
    try:
        return enum_type(value)
    except ValueError as error:
        raise FieldObservationPersistenceError(f"invalid_{field}") from error


def _reject_json_constant(value: str):
    raise ValueError(f"invalid_json_constant:{value}")


def _identity(value: object, *, field: str) -> str:
    try:
        return validate_observation_identity(value, field=field)
    except ValueError as error:
        raise FieldObservationPersistenceError(f"invalid_{field}") from error


def _deserialize_v2(
    root: Mapping[str, object],
    *,
    observation_id: str,
) -> FieldObservation:
    document = _mapping(
        root["observation"],
        fields=_OBSERVATION_V2_FIELDS,
        code="invalid_observation_fields",
    )
    stored_identity = _identity(
        document["observation_id"],
        field="observation_id",
    )
    if stored_identity != observation_id:
        raise FieldObservationPersistenceError("observation_id_mismatch")
    conditions = _mapping(
        document["conditions"],
        fields=_CONDITION_FIELDS,
        code="invalid_conditions_fields",
    )
    acquisition = _mapping(
        document["acquisition"],
        fields=_ACQUISITION_FIELDS,
        code="invalid_acquisition_fields",
    )
    technical = _mapping(
        document["technical"],
        fields=_TECHNICAL_FIELDS,
        code="invalid_technical_fields",
    )
    provenance = _mapping(
        document["provenance"],
        fields=_PROVENANCE_FIELDS,
        code="invalid_provenance_fields",
    )
    quality = _mapping(
        document["quality"],
        fields=_QUALITY_FIELDS,
        code="invalid_quality_fields",
    )
    raw_flags = quality["flags"]
    if type(raw_flags) is not list:
        raise FieldObservationPersistenceError("invalid_quality_flags")
    try:
        return FieldObservation(
            observation_id=stored_identity,
            decision_id=document["decision_id"],
            execution_id=document["execution_id"],
            observed_at_utc=_datetime(
                document["observed_at_utc"],
                field="observed_at_utc",
            ),
            recorded_at_utc=_datetime(
                document["recorded_at_utc"],
                field="recorded_at_utc",
            ),
            supersedes_observation_id=document["supersedes_observation_id"],
            conditions=ObservedConditions(
                temperature_c=conditions["temperature_c"],
                relative_humidity_percent=(
                    conditions["relative_humidity_percent"]
                ),
                cloud_state=_enum(
                    conditions["cloud_state"], CloudState, field="cloud_state"
                ),
                transparency=_enum(
                    conditions["transparency"],
                    Transparency,
                    field="transparency",
                ),
                seeing=_enum(
                    conditions["seeing"], SeeingCondition, field="seeing"
                ),
                wind_speed_kmh=conditions["wind_speed_kmh"],
                surface_condition=_enum(
                    conditions["surface_condition"],
                    SurfaceCondition,
                    field="surface_condition",
                ),
                moon_halo=conditions["moon_halo"],
            ),
            acquisition=ObservedAcquisition(
                attempted_frames=acquisition["attempted_frames"],
                usable_frames=acquisition["usable_frames"],
                stop_reason=_enum(
                    acquisition["stop_reason"], StopReason, field="stop_reason"
                ),
            ),
            technical=ObservedTechnical(
                hfr=technical["hfr"],
                hfr_unit=_enum(
                    technical["hfr_unit"], HfrUnit, field="hfr_unit"
                ),
                sky_background=technical["sky_background"],
                sky_background_unit=technical["sky_background_unit"],
                guiding_rms_arcsec=technical["guiding_rms_arcsec"],
            ),
            provenance=ObservationProvenance(
                source_type=_enum(
                    provenance["source_type"],
                    ObservationSourceType,
                    field="source_type",
                    optional=False,
                ),
                source_id=provenance["source_id"],
                capture_method=_enum(
                    provenance["capture_method"],
                    CaptureMethod,
                    field="capture_method",
                    optional=False,
                ),
                imported_at_utc=_optional_datetime(
                    provenance["imported_at_utc"],
                    field="imported_at_utc",
                ),
            ),
            quality=ObservationQuality(
                confidence=_enum(
                    quality["confidence"],
                    Confidence,
                    field="confidence",
                    optional=False,
                ),
                flags=tuple(
                    _enum(
                        value,
                        QualityFlag,
                        field="quality_flag",
                        optional=False,
                    )
                    for value in raw_flags
                ),
            ),
        )
    except FieldObservationPersistenceError:
        raise
    except (TypeError, ValueError) as error:
        raise FieldObservationPersistenceError(
            "invalid_field_observation"
        ) from error


def _deserialize_v1(
    root: Mapping[str, object],
    *,
    observation_id: str,
) -> FieldObservation:
    document = _mapping(
        root["observation"],
        fields=_OBSERVATION_V1_FIELDS,
        code="invalid_observation_fields",
    )
    stored_identity = _identity(
        document["observation_id"], field="observation_id"
    )
    if stored_identity != observation_id:
        raise FieldObservationPersistenceError("observation_id_mismatch")
    observed_at = _datetime(
        document["observed_at_utc"], field="observed_at_utc"
    )
    dew_detected = document["dew_detected"]
    if dew_detected is not None and type(dew_detected) is not bool:
        raise FieldObservationPersistenceError("invalid_dew_detected")
    surface = (
        None
        if dew_detected is None
        else SurfaceCondition.DEW_PRESENT
        if dew_detected
        else SurfaceCondition.DRY
    )
    try:
        return FieldObservation(
            observation_id=stored_identity,
            decision_id=None,
            execution_id=document["execution_id"],
            observed_at_utc=observed_at,
            recorded_at_utc=observed_at,
            supersedes_observation_id=None,
            conditions=ObservedConditions(
                cloud_state=_enum(
                    document["cloud_condition"],
                    CloudState,
                    field="cloud_condition",
                ),
                transparency=_enum(
                    document["transparency"],
                    Transparency,
                    field="transparency",
                ),
                seeing=_enum(
                    document["seeing"],
                    SeeingCondition,
                    field="seeing",
                ),
                surface_condition=surface,
            ),
            acquisition=ObservedAcquisition(),
            technical=ObservedTechnical(),
            provenance=ObservationProvenance(
                source_type=ObservationSourceType.USER,
                capture_method=CaptureMethod.MANUAL,
            ),
            quality=ObservationQuality(
                confidence=Confidence.UNKNOWN,
                flags=(QualityFlag.LEGACY_LINEAGE_INCOMPLETE,),
            ),
        )
    except FieldObservationPersistenceError:
        raise
    except (TypeError, ValueError) as error:
        raise FieldObservationPersistenceError(
            "invalid_field_observation"
        ) from error


def deserialize_field_observation(
    document: str,
    *,
    observation_id: str,
) -> FieldObservation:
    identity = _identity(observation_id, field="observation_id")
    if not isinstance(document, str):
        raise FieldObservationPersistenceError("invalid_json_document")
    try:
        payload = json.loads(document, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise FieldObservationPersistenceError("invalid_json_document") from error
    if not isinstance(payload, Mapping):
        raise FieldObservationPersistenceError("invalid_root_fields")
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise FieldObservationPersistenceError("invalid_schema_version")
    if version == 1:
        root = _mapping(
            payload,
            fields=_ROOT_V1_FIELDS,
            code="invalid_root_fields",
        )
        return _deserialize_v1(root, observation_id=identity)
    if version != SCHEMA_VERSION:
        raise FieldObservationPersistenceError("invalid_schema_version")
    root = _mapping(
        payload,
        fields=_ROOT_V2_FIELDS,
        code="invalid_root_fields",
    )
    if root["domain_version"] != DOMAIN_VERSION:
        raise FieldObservationPersistenceError("invalid_domain_version")
    return _deserialize_v2(root, observation_id=identity)
