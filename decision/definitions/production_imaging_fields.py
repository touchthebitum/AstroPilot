from decision.models.imaging_field import (
    AcquisitionIntent,
    CelestialObjectDefinition,
    ImagingFieldComponent,
    ImagingFieldDefinition,
)
from decision.services.imaging_field_resolver import ImagingFieldResolver


CELESTIAL_OBJECT_DEFINITIONS: tuple[CelestialObjectDefinition, ...] = (
    CelestialObjectDefinition(
        celestial_object_id="sh2-129",
        canonical_name="Sh2-129",
        object_type="emission nebula",
        object_subtype="H II region",
    ),
    CelestialObjectDefinition(
        celestial_object_id="ou4",
        canonical_name="Ou4",
        object_type="bipolar outflow",
    ),
)

IMAGING_FIELD_DEFINITIONS: tuple[ImagingFieldDefinition, ...] = (
    ImagingFieldDefinition(
        imaging_field_id="sh2-129_ou4",
        display_name="Sh2-129 + Ou4",
        components=(
            ImagingFieldComponent(celestial_object_id="sh2-129"),
            ImagingFieldComponent(celestial_object_id="ou4"),
        ),
        acquisition_intents=(
            AcquisitionIntent(
                acquisition_intent_id="sh2-129_ha",
                filter_type="Ha",
                primary_component_ids=("sh2-129",),
            ),
            AcquisitionIntent(
                acquisition_intent_id="ou4_oiii",
                filter_type="OIII",
                primary_component_ids=("ou4",),
            ),
        ),
    ),
)


def build_production_imaging_field_resolver() -> ImagingFieldResolver:
    return ImagingFieldResolver(
        IMAGING_FIELD_DEFINITIONS,
        CELESTIAL_OBJECT_DEFINITIONS,
    )
