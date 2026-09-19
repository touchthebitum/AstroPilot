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


def build_production_imaging_field_geometry_resolver(
) -> ImagingFieldGeometryResolver:
    return ImagingFieldGeometryResolver(IMAGING_FIELD_GEOMETRY_DEFINITIONS)
