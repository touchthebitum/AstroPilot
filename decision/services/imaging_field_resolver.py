from collections.abc import Collection

from decision.models.imaging_field import (
    CelestialObjectDefinition,
    ImagingFieldDefinition,
)


class ImagingFieldResolutionError(ValueError):
    """Raised when an imaging-field reference cannot be resolved safely."""


class ImagingFieldResolver:
    """Resolve immutable imaging-field definitions from a coherent snapshot."""

    def __init__(
        self,
        imaging_fields: Collection[ImagingFieldDefinition],
        celestial_objects: Collection[CelestialObjectDefinition],
    ) -> None:
        if not isinstance(imaging_fields, Collection):
            raise TypeError("imaging_fields must be a collection")
        if not isinstance(celestial_objects, Collection):
            raise TypeError("celestial_objects must be a collection")

        imaging_field_snapshot = tuple(imaging_fields)
        celestial_object_snapshot = tuple(celestial_objects)

        self._imaging_fields_by_id = self._index_imaging_fields(
            imaging_field_snapshot
        )
        self._celestial_objects_by_id = self._index_celestial_objects(
            celestial_object_snapshot
        )

        for imaging_field in imaging_field_snapshot:
            for component in imaging_field.components:
                if (
                    component.celestial_object_id
                    not in self._celestial_objects_by_id
                ):
                    raise ImagingFieldResolutionError(
                        "unknown celestial object referenced by imaging field: "
                        f"{component.celestial_object_id}"
                    )

    @staticmethod
    def _index_imaging_fields(
        imaging_fields: tuple[ImagingFieldDefinition, ...],
    ) -> dict[str, ImagingFieldDefinition]:
        index: dict[str, ImagingFieldDefinition] = {}
        for imaging_field in imaging_fields:
            if not isinstance(imaging_field, ImagingFieldDefinition):
                raise TypeError(
                    "imaging_fields must contain ImagingFieldDefinition values"
                )
            if imaging_field.imaging_field_id in index:
                raise ImagingFieldResolutionError(
                    "duplicate imaging_field_id: "
                    f"{imaging_field.imaging_field_id}"
                )
            index[imaging_field.imaging_field_id] = imaging_field
        return index

    @staticmethod
    def _index_celestial_objects(
        celestial_objects: tuple[CelestialObjectDefinition, ...],
    ) -> dict[str, CelestialObjectDefinition]:
        index: dict[str, CelestialObjectDefinition] = {}
        for celestial_object in celestial_objects:
            if not isinstance(
                celestial_object,
                CelestialObjectDefinition,
            ):
                raise TypeError(
                    "celestial_objects must contain "
                    "CelestialObjectDefinition values"
                )
            if celestial_object.celestial_object_id in index:
                raise ImagingFieldResolutionError(
                    "duplicate celestial_object_id: "
                    f"{celestial_object.celestial_object_id}"
                )
            index[celestial_object.celestial_object_id] = celestial_object
        return index

    def resolve(self, imaging_field_id: str) -> ImagingFieldDefinition:
        self._validate_identifier(imaging_field_id, "imaging_field_id")
        try:
            return self._imaging_fields_by_id[imaging_field_id]
        except KeyError as error:
            raise ImagingFieldResolutionError(
                f"unknown imaging_field_id: {imaging_field_id}"
            ) from error

    def resolve_object(
        self,
        celestial_object_id: str,
    ) -> CelestialObjectDefinition:
        self._validate_identifier(
            celestial_object_id,
            "celestial_object_id",
        )
        try:
            return self._celestial_objects_by_id[celestial_object_id]
        except KeyError as error:
            raise ImagingFieldResolutionError(
                f"unknown celestial_object_id: {celestial_object_id}"
            ) from error

    @staticmethod
    def _validate_identifier(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ImagingFieldResolutionError(
                f"{name} must be a non-empty string"
            )
