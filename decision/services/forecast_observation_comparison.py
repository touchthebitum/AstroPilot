from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from enum import Enum
from types import GetSetDescriptorType, MemberDescriptorType
from zoneinfo import ZoneInfo

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
)
from decision.models.forecast_observation_comparison import (
    ALGORITHM_VERSION,
    FORECAST_SCOPE,
    CloudComparisonOutcome,
    CloudMappingComparisonPolicy,
    CloudVariableComparison,
    ComparisonReason,
    ForecastObservationComparison,
    ForecastObservationComparisonStatus,
    ForecastObservationParameters,
    ForecastPointProvenance,
    NumericVariableComparison,
    ObservationComparisonProvenance,
    TemporalComparisonPolicy,
    VariableComparison,
    VariableComparisonStatus,
)
from decision.weather.cloud_mapping_policy import map_cloud_cover_to_condition
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.forecast_temporal_candidates import (
    build_forecast_temporal_candidates,
)
from decision.weather.forecast_temporal_selection import (
    ForecastTemporalSelectionError,
    select_forecast_temporal_candidate,
)
from decision.weather.provider_reliability import (
    CANONICAL_UNITS,
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
    calculate_weather_variable_error,
)


class ForecastObservationComparisonInputError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical_datetime(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def _is_canonical_utc_datetime(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is timezone.utc
        and value.fold == 0
    )


def _is_canonical_string(
    value: object,
    *,
    allow_none: bool = False,
    nonempty: bool = False,
    trimmed: bool = False,
) -> bool:
    if value is None:
        return allow_none
    if type(value) is not str:
        return False
    if nonempty and not value:
        return False
    if trimmed and value != value.strip():
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def _canonicalize(value):
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float) and value == 0.0:
        return 0.0
    if isinstance(value, tuple):
        return [_canonicalize(item) for item in value]
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    return value


def _canonical_json(value) -> str:
    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_location(location) -> dict:
    return {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "altitude_m": location.altitude_m,
    }


def _canonical_weather_value(value: WeatherValue) -> dict:
    return {
        "variable": value.variable.value,
        "value": value.value,
        "unit": value.unit,
        "aggregation_period_seconds": (
            value.aggregation_period.total_seconds()
            if value.aggregation_period is not None
            else None
        ),
    }


def _canonical_forecast_point(point: WeatherForecastPoint) -> dict:
    return {
        "provider_id": point.provider_id,
        "model_id": point.model_id,
        "retrieved_at_utc": point.retrieved_at_utc,
        "forecast_for_utc": point.forecast_for_utc,
        "requested_location": _canonical_location(point.requested_location),
        "grid_location": _canonical_location(point.grid_location),
        "values": sorted(
            (_canonical_weather_value(value) for value in point.values),
            key=_canonical_json,
        ),
    }


def _deduplicate_identical_points(
    points: tuple[WeatherForecastPoint, ...],
) -> tuple[WeatherForecastPoint, ...]:
    unique = []
    identities = set()
    for point in points:
        identity = _canonical_json(_canonical_forecast_point(point))
        if identity in identities:
            continue
        identities.add(identity)
        unique.append(point)
    return tuple(unique)


class _InvalidEvidence(ValueError):
    def __init__(self, code: str, path: str, value: object) -> None:
        self.code = code
        self.path = path
        self.value = value
        super().__init__(code)


def _safe_fingerprint_token(
    value: object,
    *,
    seen: set[int] | None = None,
    depth: int = 0,
) -> dict:
    try:
        if value is None:
            return {"kind": "none"}
        if type(value) is str:
            encoded = value.encode("utf-8", errors="surrogatepass")
            return {
                "kind": "str",
                "digest": hashlib.sha256(encoded).hexdigest(),
            }
        if type(value) is bool:
            return {"kind": "bool", "value": value}
        if type(value) is int:
            byte_count = max(1, (value.bit_length() + 8) // 8)
            encoded = value.to_bytes(byte_count, "big", signed=True)
            return {
                "kind": "int",
                "digest": hashlib.sha256(encoded).hexdigest(),
            }
        if type(value) is float:
            logical_value = 0.0 if value == 0.0 else value
            return {
                "kind": "float",
                "digest": hashlib.sha256(
                    struct.pack(">d", logical_value)
                ).hexdigest(),
            }
        if type(value) is timezone:
            offset = value.utcoffset(None)
            name = value.tzname(None)
            return {
                "kind": "timezone",
                "offset": _safe_fingerprint_token(
                    offset,
                    seen=seen,
                    depth=depth + 1,
                ),
                "name": _safe_fingerprint_token(
                    name,
                    seen=seen,
                    depth=depth + 1,
                ),
            }
        if type(value) is ZoneInfo:
            return {
                "kind": "zoneinfo",
                "key": _safe_fingerprint_token(
                    value.key,
                    seen=seen,
                    depth=depth + 1,
                ),
                # A key distinguishes ordinary zones but does not prove which
                # ruleset created a ZoneInfo (for example, from_file permits a
                # caller-supplied key). Keep the identity useful but refuse to
                # advertise it as persistence-safe without the full ruleset.
                "persistable": False,
            }
        if isinstance(value, tzinfo):
            if seen is None:
                seen = set()
            state, _ = _safe_object_state(
                value,
                seen=seen,
                depth=depth,
            )
            return {
                "kind": "arbitrary_tzinfo",
                "type": _safe_type_metadata_token(
                    type(value),
                    seen=seen,
                    depth=depth + 1,
                ),
                "state": state or {"kind": "opaque"},
                "persistable": False,
            }
        if isinstance(value, datetime):
            return _safe_temporal_fingerprint(
                value,
                base_type=datetime,
                kind="datetime",
                components=(
                    ("year", datetime.year.__get__(value, datetime)),
                    ("month", datetime.month.__get__(value, datetime)),
                    ("day", datetime.day.__get__(value, datetime)),
                    ("hour", datetime.hour.__get__(value, datetime)),
                    ("minute", datetime.minute.__get__(value, datetime)),
                    ("second", datetime.second.__get__(value, datetime)),
                    (
                        "microsecond",
                        datetime.microsecond.__get__(value, datetime),
                    ),
                    ("fold", datetime.fold.__get__(value, datetime)),
                    ("tzinfo", datetime.tzinfo.__get__(value, datetime)),
                ),
                seen=seen,
                depth=depth,
            )
        if isinstance(value, date):
            return _safe_temporal_fingerprint(
                value,
                base_type=date,
                kind="date",
                components=(
                    ("year", date.year.__get__(value, date)),
                    ("month", date.month.__get__(value, date)),
                    ("day", date.day.__get__(value, date)),
                ),
                seen=seen,
                depth=depth,
            )
        if isinstance(value, time):
            return _safe_temporal_fingerprint(
                value,
                base_type=time,
                kind="time",
                components=(
                    ("hour", time.hour.__get__(value, time)),
                    ("minute", time.minute.__get__(value, time)),
                    ("second", time.second.__get__(value, time)),
                    ("microsecond", time.microsecond.__get__(value, time)),
                    ("fold", time.fold.__get__(value, time)),
                    ("tzinfo", time.tzinfo.__get__(value, time)),
                ),
                seen=seen,
                depth=depth,
            )
        if isinstance(value, timedelta):
            return _safe_temporal_fingerprint(
                value,
                base_type=timedelta,
                kind="timedelta",
                components=(
                    ("days", timedelta.days.__get__(value, timedelta)),
                    ("seconds", timedelta.seconds.__get__(value, timedelta)),
                    (
                        "microseconds",
                        timedelta.microseconds.__get__(value, timedelta),
                    ),
                ),
                seen=seen,
                depth=depth,
            )
        if type(value) is WeatherVariable:
            return {
                "kind": "weather_variable",
                "digest": _digest(value.value),
            }
        if depth >= 8:
            return {"kind": "depth_limit", "persistable": False}
        if seen is None:
            seen = set()
        identity = id(value)
        if identity in seen:
            return {"kind": "cycle", "persistable": False}
        if type(value) in (tuple, list):
            seen.add(identity)
            items = [
                _safe_fingerprint_token(item, seen=seen, depth=depth + 1)
                for item in value
            ]
            seen.remove(identity)
            return {
                "kind": "tuple" if type(value) is tuple else "list",
                "items": items,
            }
        if type(value) is dict:
            seen.add(identity)
            entries = [
                {
                    "key": _safe_fingerprint_token(
                        key, seen=seen, depth=depth + 1
                    ),
                    "value": _safe_fingerprint_token(
                        item, seen=seen, depth=depth + 1
                    ),
                }
                for key, item in dict.items(value)
            ]
            seen.remove(identity)
            entries.sort(key=_canonical_json)
            return {"kind": "dict", "entries": entries}
        if type(value) in (set, frozenset):
            seen.add(identity)
            items = [
                _safe_fingerprint_token(item, seen=seen, depth=depth + 1)
                for item in value
            ]
            seen.remove(identity)
            items.sort(key=_canonical_json)
            return {
                "kind": "set" if type(value) is set else "frozenset",
                "items": items,
            }
        if type(value) in (bytes, bytearray):
            return {
                "kind": "bytes" if type(value) is bytes else "bytearray",
                "digest": hashlib.sha256(bytes(value)).hexdigest(),
            }
        if type(value) in (
            DecisionForecastEvidence,
            WeatherForecastPoint,
            WeatherLocation,
            WeatherValue,
        ):
            seen.add(identity)
            try:
                attributes = object.__getattribute__(value, "__dict__")
                attributes_token = _safe_fingerprint_token(
                    attributes,
                    seen=seen,
                    depth=depth + 1,
                )
            finally:
                seen.remove(identity)
            return {
                "kind": "structured_object",
                "type": _safe_type_metadata_token(
                    type(value),
                    seen=seen,
                    depth=depth + 1,
                ),
                "attributes": attributes_token,
            }
        object_state, state_is_complete = _safe_object_state(
            value,
            seen=seen,
            depth=depth,
        )
        if object_state is not None:
            return {
                "kind": "object",
                "type": _safe_type_metadata_token(
                    type(value),
                    seen=seen,
                    depth=depth + 1,
                ),
                "state": object_state,
                "persistable": state_is_complete,
            }
        return {
            "kind": "opaque",
            "type": _safe_type_metadata_token(
                type(value),
                seen=seen,
                depth=depth + 1,
            ),
            "persistable": False,
        }
    except Exception:
        return {"kind": "unavailable", "persistable": False}


def _safe_type_metadata_token(
    value_type: type,
    *,
    seen: set[int] | None,
    depth: int,
) -> dict:
    """Redact runtime type metadata before it enters a fingerprint document."""
    try:
        module = type.__getattribute__(value_type, "__module__")
        qualname = type.__getattribute__(value_type, "__qualname__")
    except Exception:
        module = None
        qualname = None
    return {
        "module": _safe_fingerprint_token(
            module,
            seen=seen,
            depth=depth + 1,
        ),
        "qualname": _safe_fingerprint_token(
            qualname,
            seen=seen,
            depth=depth + 1,
        ),
    }


def _safe_slot_metadata_token(
    owner: type,
    slot_name: str,
    binding_names: tuple[str, ...],
    *,
    seen: set[int],
    depth: int,
) -> dict:
    """Redact a material slot and every class-dictionary binding to it."""
    return {
        "owner": _safe_type_metadata_token(
            owner,
            seen=seen,
            depth=depth + 1,
        ),
        "name": _safe_fingerprint_token(
            slot_name,
            seen=seen,
            depth=depth + 1,
        ),
        "bindings": [
            _safe_fingerprint_token(
                binding_name,
                seen=seen,
                depth=depth + 1,
            )
            for binding_name in binding_names
        ],
    }


_TYPE_DICTIONARY_DESCRIPTOR = type.__getattribute__(type, "__dict__")[
    "__dict__"
]
_TYPE_LAYOUT_DESCRIPTORS = {
    name: type.__getattribute__(type, "__dict__")[name]
    for name in (
        "__base__",
        "__basicsize__",
        "__dictoffset__",
        "__itemsize__",
        "__mro__",
        "__name__",
        "__weakrefoffset__",
    )
}


def _raw_type_dictionary(owner: type):
    """Read a class dictionary without consulting its metaclass hooks."""
    return _TYPE_DICTIONARY_DESCRIPTOR.__get__(owner, type(owner))


def _raw_type_layout_attribute(owner: type, name: str):
    """Read immutable type-layout metadata through ``type``'s descriptor."""
    return _TYPE_LAYOUT_DESCRIPTORS[name].__get__(owner, type(owner))


def _safe_material_instance_dictionary(
    value: object,
) -> tuple[dict | None, bool, bool]:
    """Read the real instance dictionary only when its layout is provable.

    ``object.__getattribute__(value, "__dict__")`` still honors a data
    descriptor named ``__dict__``. Instead, inspect raw class dictionaries
    and call the genuine CPython get-set descriptors directly. A material
    dictionary that has lost or had its expected binding shadowed is treated
    as present but incomplete, even if another alias still permits reading it.
    """
    try:
        value_type = type(value)
        value_mro = _raw_type_layout_attribute(value_type, "__mro__")
        dictionary_offset = _raw_type_layout_attribute(
            value_type, "__dictoffset__"
        )
    except Exception:
        return None, False, False
    if (
        type(value_mro) is not tuple
        or not value_mro
        or value_mro[0] is not value_type
        or type(dictionary_offset) is not int
    ):
        return None, False, False
    if dictionary_offset == 0:
        return None, True, False

    complete = True
    descriptors: dict[int, GetSetDescriptorType] = {}
    missing_binding = object()
    for owner in value_mro:
        try:
            owner_dictionary = _raw_type_dictionary(owner)
            owner_dictionary_offset = _raw_type_layout_attribute(
                owner, "__dictoffset__"
            )
        except Exception:
            complete = False
            continue
        if type(owner_dictionary_offset) is not int:
            complete = False

        binding = owner_dictionary.get("__dict__", missing_binding)
        if binding is not missing_binding:
            if type(binding) is not GetSetDescriptorType:
                complete = False
            else:
                try:
                    binding_owner = binding.__objclass__
                    binding_name = binding.__name__
                except Exception:
                    complete = False
                else:
                    if binding_owner is not owner or binding_name != "__dict__":
                        complete = False

        for candidate in owner_dictionary.values():
            if type(candidate) is not GetSetDescriptorType:
                continue
            try:
                candidate_owner = candidate.__objclass__
                candidate_name = candidate.__name__
            except Exception:
                complete = False
                continue
            if candidate_owner is owner and candidate_name == "__dict__":
                descriptors[id(candidate)] = candidate
                if binding is not candidate:
                    complete = False

    if not descriptors:
        return None, False, True

    dictionaries = []
    for descriptor in descriptors.values():
        try:
            attributes = descriptor.__get__(value, value_type)
        except Exception:
            complete = False
            continue
        if type(attributes) is not dict:
            complete = False
            continue
        dictionaries.append(attributes)
    if not dictionaries:
        return None, False, True
    material_dictionary = dictionaries[0]
    if any(
        attributes is not material_dictionary for attributes in dictionaries[1:]
    ):
        complete = False
    return material_dictionary, complete, True


def _safe_material_slot_values(
    value: object,
    *,
    owners: tuple[type, ...],
    seen: set[int],
    depth: int,
) -> tuple[list[dict], bool, bool]:
    """Read slots only when their complete CPython layout is provable.

    The raw type dictionary and layout fields bypass metaclass attribute
    hooks.  The immutable basic-size delta then proves how many pointer slots
    were allocated even if a binding and ``__slots__`` are both changed after
    class creation.  Any mismatch is fail-closed.
    """
    slot_values = []
    complete = True
    found_material_slot = False
    canonical_slot_keys: set[str] = set()
    for owner in owners:
        try:
            owner_dictionary = _raw_type_dictionary(owner)
            owner_name = _raw_type_layout_attribute(owner, "__name__")
            owner_base = _raw_type_layout_attribute(owner, "__base__")
            owner_basicsize = _raw_type_layout_attribute(
                owner, "__basicsize__"
            )
            owner_itemsize = _raw_type_layout_attribute(owner, "__itemsize__")
            owner_dictionary_offset = _raw_type_layout_attribute(
                owner, "__dictoffset__"
            )
            owner_weakref_offset = _raw_type_layout_attribute(
                owner, "__weakrefoffset__"
            )
            base_basicsize = _raw_type_layout_attribute(
                owner_base, "__basicsize__"
            )
            base_itemsize = _raw_type_layout_attribute(
                owner_base, "__itemsize__"
            )
            base_dictionary_offset = _raw_type_layout_attribute(
                owner_base, "__dictoffset__"
            )
            base_weakref_offset = _raw_type_layout_attribute(
                owner_base, "__weakrefoffset__"
            )
        except Exception:
            complete = False
            continue

        descriptors: dict[int, tuple[MemberDescriptorType, list[str]]] = {}
        for binding_name, candidate in owner_dictionary.items():
            if type(candidate) is not MemberDescriptorType:
                continue
            descriptor_identity = id(candidate)
            if descriptor_identity not in descriptors:
                descriptors[descriptor_identity] = (candidate, [])
            descriptors[descriptor_identity][1].append(binding_name)

        owned_descriptors: dict[str, MemberDescriptorType] = {}
        for descriptor, _ in descriptors.values():
            try:
                descriptor_owner = descriptor.__objclass__
                descriptor_name = descriptor.__name__
            except Exception:
                complete = False
                continue
            if descriptor_owner is not owner or type(descriptor_name) is not str:
                complete = False
                continue
            if descriptor_name in owned_descriptors:
                complete = False
                continue
            owned_descriptors[descriptor_name] = descriptor

        pointer_size = struct.calcsize("P")
        layout_delta = owner_basicsize - base_basicsize
        special_layout_delta = 0
        if base_weakref_offset == 0 and owner_weakref_offset > 0:
            special_layout_delta += pointer_size
        elif (
            owner_weakref_offset != base_weakref_offset
            and not (base_weakref_offset == 0 and owner_weakref_offset < 0)
        ):
            complete = False
        if base_dictionary_offset == 0 and owner_dictionary_offset > 0:
            special_layout_delta += pointer_size
        elif (
            base_dictionary_offset != owner_dictionary_offset
            and not (
                base_dictionary_offset == 0 and owner_dictionary_offset < 0
            )
        ):
            complete = False
        material_slot_delta = layout_delta - special_layout_delta
        if (
            type(owner_basicsize) is not int
            or type(base_basicsize) is not int
            or type(owner_itemsize) is not int
            or type(base_itemsize) is not int
            or type(owner_dictionary_offset) is not int
            or type(base_dictionary_offset) is not int
            or type(owner_weakref_offset) is not int
            or type(base_weakref_offset) is not int
            or owner_itemsize != base_itemsize
            or material_slot_delta < 0
            or material_slot_delta % pointer_size
            or material_slot_delta // pointer_size != len(owned_descriptors)
        ):
            complete = False

        declared_slots = owner_dictionary.get("__slots__", ())
        if type(declared_slots) is str:
            declared_slot_names = (declared_slots,)
        elif type(declared_slots) in (tuple, list):
            declared_slot_names = tuple(declared_slots)
        elif type(declared_slots) is dict:
            declared_slot_names = tuple(declared_slots)
        else:
            declared_slot_names = ()
            complete = False
        if not all(type(name) is str for name in declared_slot_names):
            declared_slot_names = ()
            complete = False

        material_declared_names = []
        for declared_name in declared_slot_names:
            if declared_name in ("__dict__", "__weakref__"):
                continue
            mangled_name = declared_name
            if (
                declared_name.startswith("__")
                and not declared_name.endswith("__")
                and "." not in declared_name
            ):
                stripped_owner_name = owner_name.lstrip("_")
                if stripped_owner_name:
                    mangled_name = f"_{stripped_owner_name}{declared_name}"
            material_declared_names.append(mangled_name)
        if (
            len(material_declared_names) != len(set(material_declared_names))
            or set(material_declared_names) != set(owned_descriptors)
        ):
            complete = False
        for expected_name in material_declared_names:
            if owner_dictionary.get(expected_name) is not owned_descriptors.get(
                expected_name
            ):
                complete = False

        for descriptor, binding_names in descriptors.values():
            try:
                descriptor_owner = descriptor.__objclass__
                descriptor_name = descriptor.__name__
            except Exception:
                complete = False
                continue
            if descriptor_owner is not owner or type(descriptor_name) is not str:
                complete = False
                continue
            if not all(type(binding_name) is str for binding_name in binding_names):
                complete = False
                continue

            found_material_slot = True
            binding_names_tuple = tuple(sorted(binding_names))
            slot_metadata = _safe_slot_metadata_token(
                owner,
                descriptor_name,
                binding_names_tuple,
                seen=seen,
                depth=depth + 1,
            )
            canonical_slot_key = _canonical_json(slot_metadata)
            if canonical_slot_key in canonical_slot_keys:
                complete = False
            canonical_slot_keys.add(canonical_slot_key)
            try:
                slot_value = descriptor.__get__(value, type(value))
            except AttributeError:
                slot_token = {"kind": "unset"}
            except Exception:
                complete = False
                continue
            else:
                slot_token = _safe_fingerprint_token(
                    slot_value,
                    seen=seen,
                    depth=depth + 1,
                )
            slot_values.append(
                {
                    "slot": slot_metadata,
                    "value": slot_token,
                }
            )
    slot_values.sort(key=_canonical_json)
    return slot_values, complete, found_material_slot


def _safe_temporal_fingerprint(
    value: object,
    *,
    base_type: type,
    kind: str,
    components: tuple[tuple[str, object], ...],
    seen: set[int] | None,
    depth: int,
) -> dict:
    """Fingerprint temporal primitives without hiding nested safety markers."""
    if depth >= 8:
        return {"kind": "depth_limit", "persistable": False}
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return {"kind": "cycle", "persistable": False}
    seen.add(identity)
    try:
        component_tokens = {
            name: _safe_fingerprint_token(
                component,
                seen=seen,
                depth=depth + 1,
            )
            for name, component in components
        }
        storage = {"kind": "exact_builtin"}
        storage_is_complete = True
        if type(value) is not base_type:
            storage, storage_is_complete = _safe_temporal_subclass_state(
                value,
                base_type=base_type,
                seen=seen,
                depth=depth,
            )
    finally:
        seen.remove(identity)
    return {
        "kind": kind,
        "type": _safe_type_metadata_token(
            type(value),
            seen=seen,
            depth=depth + 1,
        ),
        "components": component_tokens,
        "storage": storage,
        "persistable": storage_is_complete,
    }


def _safe_temporal_subclass_state(
    value: object,
    *,
    base_type: type,
    seen: set[int],
    depth: int,
) -> tuple[dict, bool]:
    """Return all Python storage added above a known temporal primitive."""
    try:
        value_type = type(value)
        value_mro = _raw_type_layout_attribute(value_type, "__mro__")
    except Exception:
        return {"kind": "unavailable"}, False
    attributes, dictionary_complete, _ = _safe_material_instance_dictionary(
        value
    )
    owners = []
    for owner in value_mro:
        if owner is base_type:
            break
        owners.append(owner)
    slot_values, slots_complete, _ = _safe_material_slot_values(
        value,
        owners=tuple(owners),
        seen=seen,
        depth=depth,
    )
    dictionary_token = (
        _safe_fingerprint_token(
            attributes,
            seen=seen,
            depth=depth + 1,
        )
        if type(attributes) is dict
        else {"kind": "absent"}
    )
    return {
        "dictionary": dictionary_token,
        "slots": slot_values,
    }, dictionary_complete and slots_complete


def _safe_object_state(
    value: object,
    *,
    seen: set[int],
    depth: int,
) -> tuple[dict | None, bool]:
    """Return redacted Python storage only when all material storage is known.

    Instance dictionaries and real slot member descriptors are combined. Any
    opaque native base, custom slot descriptor, or unreadable slot makes the
    technical fingerprint explicitly non-persistable.
    """
    identity = id(value)
    seen.add(identity)
    try:
        value_type = type(value)
        value_mro = _raw_type_layout_attribute(value_type, "__mro__")
        attributes, dictionary_complete, has_material_dictionary = (
            _safe_material_instance_dictionary(value)
        )
        complete = dictionary_complete
        has_python_storage = has_material_dictionary
        owners = tuple(owner for owner in value_mro if owner is not object)
        slot_values, slots_complete, found_material_slot = (
            _safe_material_slot_values(
                value,
                owners=owners,
                seen=seen,
                depth=depth,
            )
        )
        complete = complete and slots_complete
        has_python_storage = has_python_storage or found_material_slot
        for owner in owners:
            try:
                owner_dictionary = _raw_type_dictionary(owner)
                owner_module = owner_dictionary.get("__module__")
            except Exception:
                complete = False
                continue
            if (
                owner_module == "builtins"
                and owner_dictionary.get("__slots__") is None
            ):
                complete = False
        dictionary_token = (
            _safe_fingerprint_token(
                attributes,
                seen=seen,
                depth=depth + 1,
            )
            if type(attributes) is dict
            else {"kind": "absent"}
        )
    finally:
        seen.remove(identity)
    if not has_python_storage:
        return None, False
    return {
        "dictionary": dictionary_token,
        "slots": slot_values,
    }, complete


def _fingerprint_is_persistable(value: object) -> bool:
    if type(value) is dict:
        if value.get("persistable") is False:
            return False
        return all(_fingerprint_is_persistable(item) for item in value.values())
    if type(value) in (tuple, list):
        return all(_fingerprint_is_persistable(item) for item in value)
    return True


def _record_inspected_value(
    context: dict,
    fingerprint_parts: list[dict],
    path: str,
    value: object,
) -> object:
    context["path"] = path
    context["value"] = value
    fingerprint_parts.append(
        {"path": path, "value": _safe_fingerprint_token(value)}
    )
    return value


def _require_evidence_invariant(
    condition: bool,
    code: str,
    path: str,
    value: object,
) -> None:
    if not condition:
        raise _InvalidEvidence(code, path, value)


def _require_exact_stored_attributes(
    value: object,
    expected: frozenset[str],
    *,
    path: str,
) -> None:
    try:
        attributes = object.__getattribute__(value, "__dict__")
    except Exception:
        attributes = None
    _require_evidence_invariant(
        type(attributes) is dict and frozenset(attributes) == expected,
        "unexpected_stored_attributes",
        path,
        value,
    )


def _validated_location(
    location: object,
    *,
    path: str,
    context: dict,
    fingerprint_parts: list[dict],
) -> WeatherLocation:
    _require_evidence_invariant(
        type(location) is WeatherLocation,
        "invalid_location_type",
        path,
        location,
    )
    _require_exact_stored_attributes(
        location,
        frozenset(("latitude", "longitude", "altitude_m")),
        path=path,
    )
    latitude = _record_inspected_value(
        context, fingerprint_parts, f"{path}.latitude", location.latitude
    )
    longitude = _record_inspected_value(
        context, fingerprint_parts, f"{path}.longitude", location.longitude
    )
    altitude_m = _record_inspected_value(
        context, fingerprint_parts, f"{path}.altitude_m", location.altitude_m
    )
    _require_evidence_invariant(
        type(latitude) is float,
        "non_canonical_latitude",
        f"{path}.latitude",
        latitude,
    )
    _require_evidence_invariant(
        type(longitude) is float,
        "non_canonical_longitude",
        f"{path}.longitude",
        longitude,
    )
    _require_evidence_invariant(
        altitude_m is None or type(altitude_m) is float,
        "non_canonical_altitude",
        f"{path}.altitude_m",
        altitude_m,
    )
    rebuilt = WeatherLocation(latitude, longitude, altitude_m=altitude_m)
    _require_evidence_invariant(
        rebuilt == location,
        "location_invariant_mismatch",
        path,
        location,
    )
    return rebuilt


def _validated_weather_value(
    value: object,
    *,
    path: str,
    context: dict,
    fingerprint_parts: list[dict],
) -> WeatherValue:
    _require_evidence_invariant(
        type(value) is WeatherValue,
        "invalid_weather_value_type",
        path,
        value,
    )
    _require_exact_stored_attributes(
        value,
        frozenset(("variable", "value", "unit", "aggregation_period")),
        path=path,
    )
    variable = _record_inspected_value(
        context, fingerprint_parts, f"{path}.variable", value.variable
    )
    numeric_value = _record_inspected_value(
        context, fingerprint_parts, f"{path}.value", value.value
    )
    unit = _record_inspected_value(
        context, fingerprint_parts, f"{path}.unit", value.unit
    )
    aggregation_period = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.aggregation_period",
        value.aggregation_period,
    )
    _require_evidence_invariant(
        type(variable) is WeatherVariable,
        "invalid_weather_variable",
        f"{path}.variable",
        variable,
    )
    _require_evidence_invariant(
        type(numeric_value) is float,
        "non_canonical_weather_value",
        f"{path}.value",
        numeric_value,
    )
    _require_evidence_invariant(
        _is_canonical_string(unit),
        "non_canonical_weather_unit",
        f"{path}.unit",
        unit,
    )
    _require_evidence_invariant(
        unit == CANONICAL_UNITS[variable],
        "non_canonical_weather_unit",
        f"{path}.unit",
        unit,
    )
    _require_evidence_invariant(
        aggregation_period is None or type(aggregation_period) is timedelta,
        "non_canonical_aggregation_period",
        f"{path}.aggregation_period",
        aggregation_period,
    )
    rebuilt = WeatherValue(
        variable=variable,
        value=numeric_value,
        unit=unit,
        aggregation_period=aggregation_period,
    )
    _require_evidence_invariant(
        rebuilt == value,
        "weather_value_invariant_mismatch",
        path,
        value,
    )
    return rebuilt


def _validated_forecast_point(
    point: object,
    *,
    index: int,
    context: dict,
    fingerprint_parts: list[dict],
) -> WeatherForecastPoint:
    path = f"forecast_points[{index}]"
    _require_evidence_invariant(
        type(point) is WeatherForecastPoint,
        "invalid_forecast_point_type",
        path,
        point,
    )
    _require_exact_stored_attributes(
        point,
        frozenset(
            (
                "provider_id",
                "model_id",
                "retrieved_at_utc",
                "forecast_for_utc",
                "requested_location",
                "grid_location",
                "values",
            )
        ),
        path=path,
    )
    provider_id = _record_inspected_value(
        context, fingerprint_parts, f"{path}.provider_id", point.provider_id
    )
    model_id = _record_inspected_value(
        context, fingerprint_parts, f"{path}.model_id", point.model_id
    )
    retrieved_at_utc = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.retrieved_at_utc",
        point.retrieved_at_utc,
    )
    forecast_for_utc = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.forecast_for_utc",
        point.forecast_for_utc,
    )
    requested_location = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.requested_location",
        point.requested_location,
    )
    grid_location = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.grid_location",
        point.grid_location,
    )
    values = _record_inspected_value(
        context, fingerprint_parts, f"{path}.values", point.values
    )
    _require_evidence_invariant(
        _is_canonical_string(provider_id, nonempty=True, trimmed=True),
        "non_canonical_provider_id",
        f"{path}.provider_id",
        provider_id,
    )
    _require_evidence_invariant(
        _is_canonical_string(
            model_id,
            allow_none=True,
            nonempty=True,
            trimmed=True,
        ),
        "non_canonical_model_id",
        f"{path}.model_id",
        model_id,
    )
    _require_evidence_invariant(
        _is_canonical_utc_datetime(retrieved_at_utc),
        "non_canonical_retrieved_at_utc",
        f"{path}.retrieved_at_utc",
        retrieved_at_utc,
    )
    _require_evidence_invariant(
        _is_canonical_utc_datetime(forecast_for_utc),
        "non_canonical_forecast_for_utc",
        f"{path}.forecast_for_utc",
        forecast_for_utc,
    )
    _require_evidence_invariant(
        type(values) is tuple,
        "non_canonical_forecast_values",
        f"{path}.values",
        values,
    )
    _require_evidence_invariant(
        bool(values),
        "forecast_values_required",
        f"{path}.values",
        values,
    )
    rebuilt_requested_location = _validated_location(
        requested_location,
        path=f"{path}.requested_location",
        context=context,
        fingerprint_parts=fingerprint_parts,
    )
    rebuilt_grid_location = _validated_location(
        grid_location,
        path=f"{path}.grid_location",
        context=context,
        fingerprint_parts=fingerprint_parts,
    )
    rebuilt_values = tuple(
        _validated_weather_value(
            value,
            path=f"{path}.values[{value_index}]",
            context=context,
            fingerprint_parts=fingerprint_parts,
        )
        for value_index, value in enumerate(values)
    )
    context["path"] = path
    context["value"] = point
    rebuilt = WeatherForecastPoint(
        provider_id=provider_id,
        model_id=model_id,
        retrieved_at_utc=retrieved_at_utc,
        forecast_for_utc=forecast_for_utc,
        requested_location=rebuilt_requested_location,
        grid_location=rebuilt_grid_location,
        values=rebuilt_values,
    )
    _require_evidence_invariant(
        rebuilt == point
        and _canonical_datetime(rebuilt.retrieved_at_utc)
        == _canonical_datetime(retrieved_at_utc)
        and _canonical_datetime(rebuilt.forecast_for_utc)
        == _canonical_datetime(forecast_for_utc),
        "forecast_point_invariant_mismatch",
        path,
        point,
    )
    return rebuilt


def _invalid_evidence_document(
    *,
    code: str,
    path: str,
    value: object,
    fingerprint_parts: list[dict],
) -> dict:
    fingerprint_document = {
        "inspected": fingerprint_parts,
        "failure": {
            "path": path,
            "value": _safe_fingerprint_token(value),
        },
    }
    return {
        "state": "invalid",
        "invalid_reason_code": code,
        "invalid_path": path,
        "invalid_identity_persistable": _fingerprint_is_persistable(
            fingerprint_document
        ),
        "invalid_fingerprint": _digest(fingerprint_document),
    }


def _inspect_evidence(evidence: object) -> tuple[bool, dict]:
    if evidence is None:
        return False, {"state": "missing"}
    fingerprint_parts: list[dict] = []
    context = {"path": "evidence", "value": evidence}
    try:
        _require_evidence_invariant(
            type(evidence) is DecisionForecastEvidence,
            "invalid_evidence_type",
            "evidence",
            evidence,
        )
        _require_exact_stored_attributes(
            evidence,
            frozenset(("forecast_points",)),
            path="evidence",
        )
        points = _record_inspected_value(
            context,
            fingerprint_parts,
            "forecast_points",
            evidence.forecast_points,
        )
        _require_evidence_invariant(
            type(points) is tuple,
            "non_canonical_forecast_points",
            "forecast_points",
            points,
        )
        rebuilt_points = tuple(
            _validated_forecast_point(
                point,
                index=index,
                context=context,
                fingerprint_parts=fingerprint_parts,
            )
            for index, point in enumerate(points)
        )
        context["path"] = "evidence"
        context["value"] = evidence
        rebuilt_evidence = DecisionForecastEvidence(rebuilt_points)
        _require_evidence_invariant(
            rebuilt_evidence == evidence,
            "evidence_invariant_mismatch",
            "evidence",
            evidence,
        )
        unique_points = _deduplicate_identical_points(rebuilt_points)
        documents = [_canonical_forecast_point(point) for point in unique_points]
        documents.sort(key=_canonical_json)
        return True, {"state": "present", "forecast_points": documents}
    except Exception as error:
        if isinstance(error, _InvalidEvidence):
            code = error.code
            path = error.path
            value = error.value
        else:
            code = "evidence_inspection_failed"
            path = context["path"]
            value = context["value"]
        return False, _invalid_evidence_document(
            code=code,
            path=path,
            value=value,
            fingerprint_parts=fingerprint_parts,
        )


def _canonical_evidence(evidence: object) -> dict:
    return _inspect_evidence(evidence)[1]


def _evidence_is_well_formed(evidence: object) -> bool:
    return _inspect_evidence(evidence)[0]


def _validated_field_observation(value: object) -> FieldObservation:
    """Rebuild an observation from exact, known section types.

    This validation deliberately runs before canonicalization or property
    access. Subclasses are rejected because their additional material storage
    is outside the v1 observation identity contract.
    """
    if type(value) is not FieldObservation:
        raise ForecastObservationComparisonInputError(
            "field_observation_invalid"
        )
    try:
        conditions = value.conditions
        acquisition = value.acquisition
        technical = value.technical
        provenance = value.provenance
        quality = value.quality
        if type(conditions) is not ObservedConditions:
            raise ValueError("invalid_conditions")
        if type(acquisition) is not ObservedAcquisition:
            raise ValueError("invalid_acquisition")
        if type(technical) is not ObservedTechnical:
            raise ValueError("invalid_technical")
        if type(provenance) is not ObservationProvenance:
            raise ValueError("invalid_provenance")
        if type(quality) is not ObservationQuality:
            raise ValueError("invalid_quality")

        observation_id = value.observation_id
        decision_id = value.decision_id
        execution_id = value.execution_id
        observed_at_utc = value.observed_at_utc
        recorded_at_utc = value.recorded_at_utc
        supersedes_observation_id = value.supersedes_observation_id

        temperature_c = conditions.temperature_c
        relative_humidity_percent = conditions.relative_humidity_percent
        cloud_state = conditions.cloud_state
        transparency = conditions.transparency
        seeing = conditions.seeing
        wind_speed_kmh = conditions.wind_speed_kmh
        surface_condition = conditions.surface_condition
        moon_halo = conditions.moon_halo

        attempted_frames = acquisition.attempted_frames
        usable_frames = acquisition.usable_frames
        stop_reason = acquisition.stop_reason

        hfr = technical.hfr
        hfr_unit = technical.hfr_unit
        sky_background = technical.sky_background
        sky_background_unit = technical.sky_background_unit
        guiding_rms_arcsec = technical.guiding_rms_arcsec

        source_type = provenance.source_type
        capture_method = provenance.capture_method
        source_id = provenance.source_id
        imported_at_utc = provenance.imported_at_utc

        confidence = quality.confidence
        flags = quality.flags

        exact_optional_strings = (
            decision_id,
            execution_id,
            supersedes_observation_id,
        )
        exact_trimmed_optional_strings = (source_id, sky_background_unit)
        exact_utc_datetimes = (observed_at_utc, recorded_at_utc)
        exact_optional_utc_datetimes = (imported_at_utc,)
        exact_optional_floats = (
            temperature_c,
            relative_humidity_percent,
            wind_speed_kmh,
            hfr,
            sky_background,
            guiding_rms_arcsec,
        )
        exact_optional_integers = (attempted_frames, usable_frames)
        exact_optional_enums = (
            (cloud_state, CloudState),
            (transparency, Transparency),
            (seeing, SeeingCondition),
            (surface_condition, SurfaceCondition),
            (stop_reason, StopReason),
            (hfr_unit, HfrUnit),
        )
        if not _is_canonical_string(observation_id):
            raise ValueError("non_canonical_observation_string")
        if any(
            not _is_canonical_string(item, allow_none=True)
            for item in exact_optional_strings
        ):
            raise ValueError("non_canonical_observation_string")
        if any(
            not _is_canonical_string(
                item,
                allow_none=True,
                nonempty=True,
                trimmed=True,
            )
            for item in exact_trimmed_optional_strings
        ):
            raise ValueError("non_canonical_observation_string")
        if any(
            not _is_canonical_utc_datetime(item)
            for item in exact_utc_datetimes
        ):
            raise ValueError("non_canonical_observation_datetime")
        if any(
            item is not None
            and not _is_canonical_utc_datetime(item)
            for item in exact_optional_utc_datetimes
        ):
            raise ValueError("non_canonical_observation_datetime")
        if any(
            item is not None and type(item) is not float
            for item in exact_optional_floats
        ):
            raise ValueError("non_canonical_observation_float")
        if any(
            item is not None and type(item) is not int
            for item in exact_optional_integers
        ):
            raise ValueError("non_canonical_observation_integer")
        if any(
            item is not None and type(item) is not expected_type
            for item, expected_type in exact_optional_enums
        ):
            raise ValueError("non_canonical_observation_enum")
        if moon_halo is not None and type(moon_halo) is not bool:
            raise ValueError("non_canonical_observation_boolean")
        if type(source_type) is not ObservationSourceType:
            raise ValueError("non_canonical_observation_source_type")
        if type(capture_method) is not CaptureMethod:
            raise ValueError("non_canonical_observation_capture_method")
        if type(confidence) is not Confidence:
            raise ValueError("non_canonical_observation_confidence")
        if type(flags) is not tuple or any(
            type(item) is not QualityFlag for item in flags
        ):
            raise ValueError("non_canonical_observation_quality_flags")

        rebuilt_conditions = ObservedConditions(
            temperature_c=temperature_c,
            relative_humidity_percent=relative_humidity_percent,
            cloud_state=cloud_state,
            transparency=transparency,
            seeing=seeing,
            wind_speed_kmh=wind_speed_kmh,
            surface_condition=surface_condition,
            moon_halo=moon_halo,
        )
        rebuilt_acquisition = ObservedAcquisition(
            attempted_frames=attempted_frames,
            usable_frames=usable_frames,
            stop_reason=stop_reason,
        )
        rebuilt_technical = ObservedTechnical(
            hfr=hfr,
            hfr_unit=hfr_unit,
            sky_background=sky_background,
            sky_background_unit=sky_background_unit,
            guiding_rms_arcsec=guiding_rms_arcsec,
        )
        rebuilt_provenance = ObservationProvenance(
            source_type=source_type,
            capture_method=capture_method,
            source_id=source_id,
            imported_at_utc=imported_at_utc,
        )
        rebuilt_quality = ObservationQuality(
            confidence=confidence,
            flags=flags,
        )
        rebuilt = FieldObservation(
            observation_id=observation_id,
            decision_id=decision_id,
            execution_id=execution_id,
            observed_at_utc=observed_at_utc,
            recorded_at_utc=recorded_at_utc,
            supersedes_observation_id=supersedes_observation_id,
            conditions=rebuilt_conditions,
            acquisition=rebuilt_acquisition,
            technical=rebuilt_technical,
            provenance=rebuilt_provenance,
            quality=rebuilt_quality,
        )
        return rebuilt
    except ForecastObservationComparisonInputError:
        raise
    except Exception as error:
        raise ForecastObservationComparisonInputError(
            "field_observation_invalid"
        ) from error


def _canonical_observation(observation: FieldObservation) -> dict:
    return {
        "observation_id": observation.observation_id,
        "decision_id": observation.decision_id,
        "execution_id": observation.execution_id,
        "observed_at_utc": observation.observed_at_utc,
        "recorded_at_utc": observation.recorded_at_utc,
        "supersedes_observation_id": observation.supersedes_observation_id,
        "conditions": asdict(observation.conditions),
        "acquisition": asdict(observation.acquisition),
        "technical": asdict(observation.technical),
        "provenance": asdict(observation.provenance),
        "quality": asdict(observation.quality),
    }


def _parameter_document(parameters: ForecastObservationParameters) -> dict:
    return {
        "temporal_policy": {
            "version": parameters.temporal_policy.version,
            "maximum_absolute_offset_seconds": (
                parameters.temporal_policy.maximum_absolute_offset.total_seconds()
            ),
            "timezone_name": parameters.temporal_policy.timezone_name,
            "selection_mode": parameters.temporal_policy.selection_mode,
            "interpolation_enabled": (
                parameters.temporal_policy.interpolation_enabled
            ),
            "averaging_enabled": parameters.temporal_policy.averaging_enabled,
        },
        "cloud_mapping_policy": {
            "version": parameters.cloud_mapping_policy.version,
            "boundaries_percent": (
                parameters.cloud_mapping_policy.boundaries_percent
            ),
        },
    }


def _validated_parameters(value: object) -> ForecastObservationParameters:
    """Validate every material parameter field before identity generation."""
    if type(value) is not ForecastObservationParameters:
        raise ForecastObservationComparisonInputError(
            "invalid_forecast_observation_parameters"
        )
    try:
        temporal_policy = value.temporal_policy
        cloud_mapping_policy = value.cloud_mapping_policy
        if type(temporal_policy) is not TemporalComparisonPolicy:
            raise ValueError("invalid_temporal_policy")
        if type(cloud_mapping_policy) is not CloudMappingComparisonPolicy:
            raise ValueError("invalid_cloud_mapping_policy")

        temporal_version = temporal_policy.version
        maximum_absolute_offset = temporal_policy.maximum_absolute_offset
        timezone_name = temporal_policy.timezone_name
        selection_mode = temporal_policy.selection_mode
        interpolation_enabled = temporal_policy.interpolation_enabled
        averaging_enabled = temporal_policy.averaging_enabled
        if any(
            not _is_canonical_string(item, nonempty=True, trimmed=True)
            for item in (temporal_version, timezone_name, selection_mode)
        ):
            raise ValueError("non_canonical_temporal_policy_string")
        if type(maximum_absolute_offset) is not timedelta:
            raise ValueError("non_canonical_maximum_absolute_offset")
        if type(interpolation_enabled) is not bool or type(
            averaging_enabled
        ) is not bool:
            raise ValueError("non_canonical_temporal_policy_boolean")

        cloud_version = cloud_mapping_policy.version
        boundaries_percent = cloud_mapping_policy.boundaries_percent
        if not _is_canonical_string(
            cloud_version,
            nonempty=True,
            trimmed=True,
        ):
            raise ValueError("non_canonical_cloud_mapping_version")
        if type(boundaries_percent) is not tuple or any(
            type(item) is not float for item in boundaries_percent
        ):
            raise ValueError("non_canonical_cloud_mapping_boundaries")

        rebuilt_temporal_policy = TemporalComparisonPolicy(
            version=temporal_version,
            maximum_absolute_offset=maximum_absolute_offset,
            timezone_name=timezone_name,
            selection_mode=selection_mode,
            interpolation_enabled=interpolation_enabled,
            averaging_enabled=averaging_enabled,
        )
        rebuilt_cloud_mapping_policy = CloudMappingComparisonPolicy(
            version=cloud_version,
            boundaries_percent=boundaries_percent,
        )
        return ForecastObservationParameters(
            temporal_policy=rebuilt_temporal_policy,
            cloud_mapping_policy=rebuilt_cloud_mapping_policy,
        )
    except ForecastObservationComparisonInputError:
        raise
    except Exception as error:
        raise ForecastObservationComparisonInputError(
            "invalid_forecast_observation_parameters"
        ) from error


def _source_digest(
    canonical_evidence: dict,
    observation: FieldObservation,
    *,
    identity_persistable: bool,
) -> str:
    return _digest(
        {
            "decision_forecast_evidence": canonical_evidence,
            "field_observation": _canonical_observation(observation),
            "identity_persistable": identity_persistable,
        }
    )


def _comparison_id(
    *,
    observation: FieldObservation,
    source_digest: str,
    identity_persistable: bool,
    algorithm_version: str,
    parameters: ForecastObservationParameters,
) -> str:
    return _digest(
        {
            "decision_id": observation.decision_id,
            "observation_id": observation.observation_id,
            "source_digest": source_digest,
            "identity_persistable": identity_persistable,
            "algorithm_version": algorithm_version,
            "forecast_scope": FORECAST_SCOPE,
            "parameters": _parameter_document(parameters),
        }
    )


def _observation_provenance(
    observation: FieldObservation,
) -> ObservationComparisonProvenance:
    return ObservationComparisonProvenance(
        source_type=observation.provenance.source_type,
        source_id=observation.provenance.source_id,
        capture_method=observation.provenance.capture_method,
        confidence=observation.quality.confidence,
        quality_flags=observation.quality.flags,
    )


def _point_provenance(
    point: WeatherForecastPoint,
    *,
    observed_at_utc: datetime,
) -> ForecastPointProvenance:
    return ForecastPointProvenance(
        provider_id=point.provider_id,
        model_id=point.model_id,
        retrieved_at_utc=point.retrieved_at_utc,
        forecast_for_utc=point.forecast_for_utc,
        temporal_offset=point.forecast_for_utc - observed_at_utc,
    )


def _observed_values(
    observation: FieldObservation,
) -> tuple[tuple[WeatherVariable, float | CloudState], ...]:
    conditions = observation.conditions
    values = []
    for variable, value in (
        (WeatherVariable.TEMPERATURE_C, conditions.temperature_c),
        (
            WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
            conditions.relative_humidity_percent,
        ),
        (WeatherVariable.WIND_SPEED_KMH, conditions.wind_speed_kmh),
        (WeatherVariable.CLOUD_COVER_PERCENT, conditions.cloud_state),
    ):
        if value is not None:
            values.append((variable, value))
    return tuple(values)


def _not_comparable_result(
    variable: WeatherVariable,
    reason: ComparisonReason,
) -> VariableComparison:
    if variable is WeatherVariable.CLOUD_COVER_PERCENT:
        return CloudVariableComparison(
            variable=variable,
            status=VariableComparisonStatus.NOT_COMPARABLE,
            unit=CANONICAL_UNITS[variable],
            reasons=(reason,),
        )
    return NumericVariableComparison(
        variable=variable,
        status=VariableComparisonStatus.NOT_COMPARABLE,
        unit=CANONICAL_UNITS[variable],
        reasons=(reason,),
    )


def _points_for_variable(
    evidence: DecisionForecastEvidence,
    variable: WeatherVariable,
) -> tuple[WeatherForecastPoint, ...]:
    compatible = tuple(
        point
        for point in evidence.forecast_points
        if any(value.variable is variable for value in point.values)
    )
    return _deduplicate_identical_points(compatible)


def _select_point(
    evidence: DecisionForecastEvidence,
    observation: FieldObservation,
    variable: WeatherVariable,
    parameters: ForecastObservationParameters,
) -> tuple[WeatherForecastPoint | None, ComparisonReason | None]:
    points = _points_for_variable(evidence, variable)
    if not points:
        return None, ComparisonReason(
            code="forecast_variable_unavailable",
            variable=variable,
        )
    candidates = build_forecast_temporal_candidates(
        points,
        observation.observed_at_utc,
    )
    try:
        selected = select_forecast_temporal_candidate(
            candidates,
            maximum_absolute_offset=(
                parameters.temporal_policy.maximum_absolute_offset
            ),
        )
    except ForecastTemporalSelectionError:
        return None, ComparisonReason(
            code="ambiguous_nearest_forecast",
            variable=variable,
        )
    if selected is None:
        return None, ComparisonReason(
            code="forecast_outside_temporal_tolerance",
            variable=variable,
        )
    return selected.forecast_point, None


def _value_for_variable(
    point: WeatherForecastPoint,
    variable: WeatherVariable,
) -> WeatherValue:
    for value in point.values:
        if value.variable is variable:
            return value
    raise AssertionError("selected_forecast_variable_missing")


def _numeric_result(
    *,
    variable: WeatherVariable,
    observed_value: float,
    point: WeatherForecastPoint,
    observation: FieldObservation,
) -> NumericVariableComparison:
    forecast_value = _value_for_variable(point, variable)
    error = calculate_weather_variable_error(
        variable=variable,
        forecast_value=forecast_value.value,
        observed_value=observed_value,
        unit=forecast_value.unit,
    )
    return NumericVariableComparison(
        variable=variable,
        status=VariableComparisonStatus.COMPARABLE,
        unit=error.unit,
        forecast_value=error.forecast_value,
        observed_value=error.observed_value,
        signed_error=error.signed_error,
        absolute_error=error.absolute_error,
        forecast_point=_point_provenance(
            point,
            observed_at_utc=observation.observed_at_utc,
        ),
    )


def _cloud_result(
    *,
    observed_condition: CloudState,
    point: WeatherForecastPoint,
    observation: FieldObservation,
) -> CloudVariableComparison:
    variable = WeatherVariable.CLOUD_COVER_PERCENT
    forecast_value = _value_for_variable(point, variable)
    predicted = map_cloud_cover_to_condition(forecast_value.value)
    outcome = (
        CloudComparisonOutcome.MATCH
        if predicted is observed_condition
        else CloudComparisonOutcome.MISMATCH
    )
    return CloudVariableComparison(
        variable=variable,
        status=VariableComparisonStatus.COMPARABLE,
        unit=forecast_value.unit,
        forecast_coverage_percent=forecast_value.value,
        predicted_condition=predicted,
        observed_condition=observed_condition,
        outcome=outcome,
        confusion_cell=(predicted, observed_condition),
        forecast_point=_point_provenance(
            point,
            observed_at_utc=observation.observed_at_utc,
        ),
    )


def _comparison_status(
    results: tuple[VariableComparison, ...],
) -> ForecastObservationComparisonStatus:
    comparable_count = sum(
        result.status is VariableComparisonStatus.COMPARABLE
        for result in results
    )
    if comparable_count == 0:
        return ForecastObservationComparisonStatus.NOT_COMPARABLE
    if comparable_count == len(results):
        return ForecastObservationComparisonStatus.COMPARABLE
    return ForecastObservationComparisonStatus.PARTIAL


def compare_forecast_to_field_observation(
    evidence: object,
    observation: FieldObservation,
    *,
    computed_at_utc: datetime,
    algorithm_version: str = ALGORITHM_VERSION,
    parameters: ForecastObservationParameters | None = None,
) -> ForecastObservationComparison:
    """Compare immutable decision evidence to one immutable field observation.

    The caller supplies ``computed_at_utc`` so the engine has no clock or other
    side effect. Missing or invalid forecast evidence is represented as a
    structured not-comparable result. A missing/invalid observation raises a
    typed input error because no comparison identity can be constructed.

    ``comparison_id`` remains a deterministic technical correlation ID when
    ``identity_persistable`` is false. Persistence boundaries must reject such
    a result because its invalid evidence could not be covered completely and
    safely by the redacted identity document.
    """
    if observation is None:
        raise ForecastObservationComparisonInputError(
            "field_observation_missing"
        )
    observation = _validated_field_observation(observation)
    if not _is_canonical_string(
        algorithm_version,
        nonempty=True,
        trimmed=True,
    ):
        raise ForecastObservationComparisonInputError("invalid_algorithm_version")
    effective_parameters = (
        ForecastObservationParameters() if parameters is None else parameters
    )
    effective_parameters = _validated_parameters(effective_parameters)

    evidence_is_well_formed, canonical_evidence = _inspect_evidence(evidence)
    identity_persistable = canonical_evidence.get(
        "invalid_identity_persistable",
        True,
    )
    digest = _source_digest(
        canonical_evidence,
        observation,
        identity_persistable=identity_persistable,
    )
    identity = _comparison_id(
        observation=observation,
        source_digest=digest,
        identity_persistable=identity_persistable,
        algorithm_version=algorithm_version,
        parameters=effective_parameters,
    )
    provenance = _observation_provenance(observation)

    evidence_reason = None
    if evidence is None:
        evidence_reason = "decision_forecast_evidence_missing"
    elif not evidence_is_well_formed:
        evidence_reason = "decision_forecast_evidence_invalid"
    elif not evidence.forecast_points:
        evidence_reason = "decision_forecast_evidence_empty"

    observed_values = _observed_values(observation)
    blocking_reasons = []
    if observation.legacy_lineage_incomplete:
        blocking_reasons.append(ComparisonReason("legacy_lineage_incomplete"))
    if QualityFlag.TIME_UNCERTAIN in observation.quality.flags:
        blocking_reasons.append(ComparisonReason("observation_time_uncertain"))
    if QualityFlag.LOCATION_UNCERTAIN in observation.quality.flags:
        blocking_reasons.append(
            ComparisonReason("observation_location_uncertain")
        )
    if blocking_reasons:
        reasons = []
        if evidence_reason is not None:
            reasons.append(ComparisonReason(evidence_reason))
        reasons.extend(blocking_reasons)
        if not observed_values:
            reasons.append(ComparisonReason("no_supported_observed_variables"))
        return ForecastObservationComparison(
            comparison_id=identity,
            identity_persistable=identity_persistable,
            algorithm_version=algorithm_version,
            computed_at_utc=computed_at_utc,
            decision_id=observation.decision_id,
            observation_id=observation.observation_id,
            execution_id=observation.execution_id,
            source_digest=digest,
            parameters=effective_parameters,
            observation_provenance=provenance,
            results=(),
            status=ForecastObservationComparisonStatus.NOT_COMPARABLE,
            reasons=tuple(reasons),
        )

    results = []
    reasons = []
    if not observed_values:
        if evidence_reason is not None:
            reasons.append(ComparisonReason(evidence_reason))
        reasons.append(ComparisonReason("no_supported_observed_variables"))
    elif evidence_reason is not None:
        reasons.append(ComparisonReason(evidence_reason))
        for variable, _ in observed_values:
            result_reason = ComparisonReason(evidence_reason, variable)
            results.append(_not_comparable_result(variable, result_reason))
    else:
        assert isinstance(evidence, DecisionForecastEvidence)
        for variable, observed_value in observed_values:
            if (
                variable is WeatherVariable.CLOUD_COVER_PERCENT
                and observed_value is CloudState.UNKNOWN
            ):
                reason = ComparisonReason("observed_cloud_unknown", variable)
                results.append(_not_comparable_result(variable, reason))
                reasons.append(reason)
                continue
            point, selection_reason = _select_point(
                evidence,
                observation,
                variable,
                effective_parameters,
            )
            if selection_reason is not None:
                results.append(_not_comparable_result(variable, selection_reason))
                reasons.append(selection_reason)
                continue
            assert point is not None
            if variable is WeatherVariable.CLOUD_COVER_PERCENT:
                assert isinstance(observed_value, CloudState)
                results.append(
                    _cloud_result(
                        observed_condition=observed_value,
                        point=point,
                        observation=observation,
                    )
                )
            else:
                assert isinstance(observed_value, float)
                results.append(
                    _numeric_result(
                        variable=variable,
                        observed_value=observed_value,
                        point=point,
                        observation=observation,
                    )
                )

    result_tuple = tuple(results)
    return ForecastObservationComparison(
        comparison_id=identity,
        identity_persistable=identity_persistable,
        algorithm_version=algorithm_version,
        computed_at_utc=computed_at_utc,
        decision_id=observation.decision_id,
        observation_id=observation.observation_id,
        execution_id=observation.execution_id,
        source_digest=digest,
        parameters=effective_parameters,
        observation_provenance=provenance,
        results=result_tuple,
        status=_comparison_status(result_tuple),
        reasons=tuple(reasons),
    )
