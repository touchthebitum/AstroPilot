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

# Additional single-component fields use the existing, explicitly identified catalog
# entries. sh2-190/sh2-199 explicitly mean the whole H II regions; the
# IC1805/IC1848 canonical names retain the existing portfolio keys, not a claim
# that the embedded open cluster has the same extent as its surrounding nebula.
# Discovery does not give these fields project progress or target hours.
CELESTIAL_OBJECT_DEFINITIONS += tuple(
    CelestialObjectDefinition(celestial_object_id=identity, canonical_name=key,
                              object_type="emission nebula", object_subtype="H II region")
    for identity, key in (("ngc7000", "NorthAmerica"), ("rosette", "Rosette"), ("m42", "M42"),
                          ("sh2-190", "IC1805"), ("sh2-199", "IC1848"))
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
                label="Hα · Sh2-129",
            ),
            AcquisitionIntent(
                acquisition_intent_id="ou4_oiii",
                filter_type="OIII",
                primary_component_ids=("ou4",),
                label="OIII · Ou4",
            ),
        ),
    ),
)

IMAGING_FIELD_DEFINITIONS += tuple(
    ImagingFieldDefinition(
        imaging_field_id=identity, display_name=name,
        components=(ImagingFieldComponent(celestial_object_id=identity),),
        acquisition_intents=(AcquisitionIntent(
            acquisition_intent_id=identity + "_ha", filter_type="Ha",
            primary_component_ids=(identity,), label="Hα · " + name),),
    )
    for identity, name in (("ngc7000", "North America · NGC 7000"),
                           ("rosette", "Nébuleuse de la Rosette"),
                           ("m42", "Nébuleuse d’Orion · M42"),
                           ("sh2-190", "Nébuleuse du Cœur · Sh2-190"),
                           ("sh2-199", "Nébuleuse de l’Âme · Sh2-199"))
)


from decision.definitions.production_extended_targets import EXTENDED_HA_TARGETS

CELESTIAL_OBJECT_DEFINITIONS += tuple(
    CelestialObjectDefinition(celestial_object_id=t["identity"], canonical_name=t["key"],
        object_type="emission nebula", object_subtype="H II region")
    for t in EXTENDED_HA_TARGETS
)
IMAGING_FIELD_DEFINITIONS += tuple(
    ImagingFieldDefinition(imaging_field_id=t["identity"], display_name=t["name"],
        components=(ImagingFieldComponent(celestial_object_id=t["identity"]),),
        acquisition_intents=(AcquisitionIntent(acquisition_intent_id=t["identity"] + "_ha",
            filter_type="Ha", primary_component_ids=(t["identity"],), label="Hα · " + t["name"]),))
    for t in EXTENDED_HA_TARGETS
)


def build_production_imaging_field_resolver() -> ImagingFieldResolver:
    return ImagingFieldResolver(
        IMAGING_FIELD_DEFINITIONS,
        CELESTIAL_OBJECT_DEFINITIONS,
    )
