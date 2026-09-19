from collections.abc import Mapping

from decision.models.imaging_field import (
    CelestialObjectDefinition,
    ImagingFieldComponent,
    ImagingFieldDefinition,
)


class LegacyImagingFieldResolver:
    """Expose a legacy catalog target through the ImagingField contract."""

    @staticmethod
    def resolve(
        *,
        catalog_key: str,
        catalog_entry: Mapping[str, object],
    ) -> ImagingFieldDefinition:
        celestial_object = LegacyImagingFieldResolver.resolve_object(
            catalog_key=catalog_key,
            catalog_entry=catalog_entry,
        )

        return ImagingFieldDefinition(
            imaging_field_id=catalog_key,
            display_name=celestial_object.canonical_name,
            components=(
                ImagingFieldComponent(
                    celestial_object_id=(
                        celestial_object.celestial_object_id
                    ),
                ),
            ),
            acquisition_intents=(),
        )

    @staticmethod
    def resolve_object(
        *,
        catalog_key: str,
        catalog_entry: Mapping[str, object],
    ) -> CelestialObjectDefinition:
        if not isinstance(catalog_key, str) or not catalog_key.strip():
            raise ValueError("catalog_key must not be empty")
        if not isinstance(catalog_entry, Mapping):
            raise TypeError("catalog_entry must be a mapping")

        name = catalog_entry.get("name")
        object_type = catalog_entry.get("type")
        object_subtype = catalog_entry.get("subtype")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("catalog_entry name must not be empty")
        if not isinstance(object_type, str) or not object_type.strip():
            raise ValueError("catalog_entry type must not be empty")
        if object_subtype is not None and not isinstance(
            object_subtype,
            str,
        ):
            raise ValueError("catalog_entry subtype must be a string")

        return CelestialObjectDefinition(
            celestial_object_id=catalog_key,
            canonical_name=name,
            object_type=object_type,
            object_subtype=object_subtype,
        )
