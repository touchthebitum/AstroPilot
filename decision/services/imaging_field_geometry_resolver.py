from collections.abc import Collection

from decision.models.imaging_field_geometry import (
    ImagingFieldGeometryDefinition,
)


class ImagingFieldGeometryResolutionError(ValueError):
    """Raised when imaging-field geometry cannot be resolved safely."""


class ImagingFieldGeometryResolver:
    """Resolve immutable field geometry by exact imaging-field identity."""

    def __init__(
        self,
        definitions: Collection[ImagingFieldGeometryDefinition],
    ) -> None:
        if not isinstance(definitions, Collection):
            raise TypeError("definitions must be a collection")

        snapshot = tuple(definitions)
        self._definitions_by_imaging_field_id = self._index(snapshot)

    @staticmethod
    def _index(
        definitions: tuple[ImagingFieldGeometryDefinition, ...],
    ) -> dict[str, ImagingFieldGeometryDefinition]:
        index: dict[str, ImagingFieldGeometryDefinition] = {}
        for definition in definitions:
            if not isinstance(definition, ImagingFieldGeometryDefinition):
                raise TypeError(
                    "definitions must contain "
                    "ImagingFieldGeometryDefinition values"
                )
            if definition.imaging_field_id in index:
                raise ImagingFieldGeometryResolutionError(
                    "duplicate imaging_field_id: "
                    f"{definition.imaging_field_id}"
                )
            index[definition.imaging_field_id] = definition
        return index

    def resolve(
        self,
        imaging_field_id: str,
    ) -> ImagingFieldGeometryDefinition:
        if (
            not isinstance(imaging_field_id, str)
            or not imaging_field_id.strip()
        ):
            raise ImagingFieldGeometryResolutionError(
                "imaging_field_id must be a non-empty string"
            )
        try:
            return self._definitions_by_imaging_field_id[imaging_field_id]
        except KeyError as error:
            raise ImagingFieldGeometryResolutionError(
                f"unknown imaging_field_id: {imaging_field_id}"
            ) from error
