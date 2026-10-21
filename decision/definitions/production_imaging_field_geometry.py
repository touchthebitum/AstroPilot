from decision.models.imaging_field_geometry import (
    ImagingFieldGeometryDefinition,
)
from decision.services.imaging_field_geometry_resolver import (
    ImagingFieldGeometryResolver,
)


IMAGING_FIELD_GEOMETRY_DEFINITIONS: tuple[
    ImagingFieldGeometryDefinition, ...
] = (
    # ICRS/J2000 framing/reference center for the composite imaging field.
    # This is not an official object coordinate for Sh2-129 or Ou4.
    ImagingFieldGeometryDefinition(
        imaging_field_id="sh2-129_ou4",
        reference_ra_deg=317.95,
        reference_dec_deg=59.97,
    ),
)

# Same ICRS/J2000 reference centers as the legacy scoring catalog. These
# identify the planning field, not the orientation or crop of the reference image.
IMAGING_FIELD_GEOMETRY_DEFINITIONS += (
    ImagingFieldGeometryDefinition(imaging_field_id="ngc7000",
        reference_ra_deg=314.75, reference_dec_deg=44.33),
    ImagingFieldGeometryDefinition(imaging_field_id="rosette",
        reference_ra_deg=97.5, reference_dec_deg=4.95),
)


def build_production_imaging_field_geometry_resolver(
) -> ImagingFieldGeometryResolver:
    return ImagingFieldGeometryResolver(IMAGING_FIELD_GEOMETRY_DEFINITIONS)
