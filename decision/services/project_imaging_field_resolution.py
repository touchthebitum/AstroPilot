from collections.abc import Mapping

from decision.models.imaging_field import ImagingFieldDefinition
from decision.services.imaging_field_resolver import (
    ImagingFieldResolutionError,
    ImagingFieldResolver,
)


class ProjectImagingFieldResolutionError(ValueError):
    """Raised when an explicit project imaging-field reference is invalid."""


def resolve_project_imaging_field(
    project: Mapping[str, object],
    resolver: ImagingFieldResolver,
) -> ImagingFieldDefinition | None:
    """Resolve a project's explicit imaging field without legacy fallback."""
    if not isinstance(project, Mapping):
        raise ProjectImagingFieldResolutionError(
            "project must be a mapping"
        )
    if "imaging_field_id" not in project:
        return None

    imaging_field_id = project["imaging_field_id"]
    if not isinstance(imaging_field_id, str) or not imaging_field_id.strip():
        raise ProjectImagingFieldResolutionError(
            "imaging_field_id must be a non-empty string"
        )

    try:
        return resolver.resolve(imaging_field_id)
    except ImagingFieldResolutionError as error:
        raise ProjectImagingFieldResolutionError(
            f"invalid project imaging_field_id: {imaging_field_id!r}"
        ) from error
