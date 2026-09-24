from dataclasses import dataclass


def _validate_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class CelestialObjectDefinition:
    celestial_object_id: str
    canonical_name: str
    object_type: str
    object_subtype: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty(
            self.celestial_object_id,
            "celestial_object_id",
        )
        _validate_non_empty(self.canonical_name, "canonical_name")
        _validate_non_empty(self.object_type, "object_type")
        if self.object_subtype is not None:
            _validate_non_empty(self.object_subtype, "object_subtype")


@dataclass(frozen=True, slots=True)
class ImagingFieldComponent:
    celestial_object_id: str

    def __post_init__(self) -> None:
        _validate_non_empty(
            self.celestial_object_id,
            "celestial_object_id",
        )


@dataclass(frozen=True, slots=True)
class AcquisitionIntent:
    acquisition_intent_id: str
    filter_type: str
    primary_component_ids: tuple[str, ...]
    label: str

    def __post_init__(self) -> None:
        _validate_non_empty(
            self.acquisition_intent_id,
            "acquisition_intent_id",
        )
        _validate_non_empty(self.filter_type, "filter_type")
        _validate_non_empty(self.label, "label")
        if not isinstance(self.primary_component_ids, tuple):
            raise TypeError("primary_component_ids must be a tuple")
        if not self.primary_component_ids:
            raise ValueError("primary_component_ids must not be empty")

        seen_component_ids: set[str] = set()
        for component_id in self.primary_component_ids:
            _validate_non_empty(component_id, "primary_component_id")
            if component_id in seen_component_ids:
                raise ValueError(
                    "primary_component_ids must not contain duplicates"
                )
            seen_component_ids.add(component_id)


@dataclass(frozen=True, slots=True)
class ImagingFieldDefinition:
    imaging_field_id: str
    display_name: str
    components: tuple[ImagingFieldComponent, ...]
    acquisition_intents: tuple[AcquisitionIntent, ...]

    def __post_init__(self) -> None:
        _validate_non_empty(self.imaging_field_id, "imaging_field_id")
        _validate_non_empty(self.display_name, "display_name")
        if not isinstance(self.components, tuple):
            raise TypeError("components must be a tuple")
        if not self.components:
            raise ValueError("components must not be empty")
        if not isinstance(self.acquisition_intents, tuple):
            raise TypeError("acquisition_intents must be a tuple")

        component_ids: set[str] = set()
        for component in self.components:
            if not isinstance(component, ImagingFieldComponent):
                raise TypeError(
                    "components must contain ImagingFieldComponent values"
                )
            if component.celestial_object_id in component_ids:
                raise ValueError(
                    "duplicate celestial_object_id in imaging field"
                )
            component_ids.add(component.celestial_object_id)

        intent_ids: set[str] = set()
        for intent in self.acquisition_intents:
            if not isinstance(intent, AcquisitionIntent):
                raise TypeError(
                    "acquisition_intents must contain AcquisitionIntent values"
                )
            if intent.acquisition_intent_id in intent_ids:
                raise ValueError(
                    "duplicate acquisition_intent_id in imaging field"
                )
            intent_ids.add(intent.acquisition_intent_id)

            missing_ids = set(intent.primary_component_ids) - component_ids
            if missing_ids:
                missing = ", ".join(sorted(missing_ids))
                raise ValueError(
                    f"unknown primary component in acquisition intent: {missing}"
                )
