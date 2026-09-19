from collections.abc import Mapping

from decision.models.project_acquisition_intent_target import (
    ProjectAcquisitionIntentTarget,
)
from decision.services.imaging_field_resolver import ImagingFieldResolver
from decision.services.project_imaging_field_resolution import (
    ProjectImagingFieldResolutionError,
    resolve_project_imaging_field,
)


class ProjectAcquisitionIntentTargetsError(ValueError):
    """Raised when project acquisition-intent targets are invalid."""


def resolve_project_acquisition_intent_targets(
    project: Mapping[str, object],
    resolver: ImagingFieldResolver,
) -> tuple[ProjectAcquisitionIntentTarget, ...]:
    """Validate targets against the project's explicit imaging field."""
    if not isinstance(project, Mapping):
        raise ProjectAcquisitionIntentTargetsError(
            "project must be a mapping"
        )
    if "acquisition_intent_targets" not in project:
        return ()

    raw_targets = project["acquisition_intent_targets"]
    if not isinstance(raw_targets, (list, tuple)):
        raise ProjectAcquisitionIntentTargetsError(
            "acquisition_intent_targets must be a collection"
        )

    try:
        imaging_field = resolve_project_imaging_field(project, resolver)
    except ProjectImagingFieldResolutionError as error:
        raise ProjectAcquisitionIntentTargetsError(
            "acquisition_intent_targets require a valid imaging_field_id"
        ) from error
    if imaging_field is None:
        raise ProjectAcquisitionIntentTargetsError(
            "acquisition_intent_targets require imaging_field_id"
        )

    known_intent_ids = {
        intent.acquisition_intent_id
        for intent in imaging_field.acquisition_intents
    }
    targets: list[ProjectAcquisitionIntentTarget] = []
    seen_intent_ids: set[str] = set()
    expected_fields = {"acquisition_intent_id", "target_hours"}

    for raw_target in raw_targets:
        if (
            not isinstance(raw_target, Mapping)
            or set(raw_target) != expected_fields
        ):
            raise ProjectAcquisitionIntentTargetsError(
                "acquisition_intent_targets entries must contain exactly "
                "acquisition_intent_id and target_hours"
            )
        try:
            target = ProjectAcquisitionIntentTarget(
                acquisition_intent_id=raw_target["acquisition_intent_id"],
                target_hours=raw_target["target_hours"],
            )
        except (TypeError, ValueError) as error:
            raise ProjectAcquisitionIntentTargetsError(
                "invalid acquisition_intent_target"
            ) from error

        if target.acquisition_intent_id in seen_intent_ids:
            raise ProjectAcquisitionIntentTargetsError(
                "duplicate acquisition_intent_id"
            )
        if target.acquisition_intent_id not in known_intent_ids:
            raise ProjectAcquisitionIntentTargetsError(
                "acquisition_intent_id does not belong to imaging field"
            )

        seen_intent_ids.add(target.acquisition_intent_id)
        targets.append(target)

    return tuple(targets)
