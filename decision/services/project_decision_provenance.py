"""Authorization classification; historical readers do not use this boundary."""
from collections.abc import Mapping
from enum import Enum

from decision.services.imaging_field_resolver import ImagingFieldResolver
from decision.services.project_imaging_field_resolution import (
    resolve_project_imaging_field,
)
from decision.services.project_acquisition_intent_targets import (
    resolve_project_acquisition_intent_targets,
)
from decision.services.project_acquisition_intent_progress import (
    resolve_project_acquisition_intent_progress,
)


class ProjectDecisionProvenance(str, Enum):
    LEGACY_READ_ONLY = "legacy_read_only"
    MODERN_AUTHORIZED = "modern_authorized"
    MODERN_PROVENANCE_MISSING = "modern_provenance_missing"


def resolve_project_decision_provenance(
    project: Mapping[str, object],
    resolver: ImagingFieldResolver,
) -> ProjectDecisionProvenance:
    """Absence is never legacy authorization. A label cannot supply evidence.

    MODERN_AUTHORIZED permits modern assessment only; eligibility and selected
    intent still gate mission authorization. An absent progress snapshot fails
    closed; an explicit empty snapshot retains unknown progress for assessment.
    """
    if not isinstance(project, Mapping):
        return ProjectDecisionProvenance.MODERN_PROVENANCE_MISSING
    # A historical label identifies fieldless data for READ only. It is not
    # an authorization switch: deleting any label must not change modern proof.
    missing = (
        ProjectDecisionProvenance.LEGACY_READ_ONLY
        if project.get("decision_provenance") == ProjectDecisionProvenance.LEGACY_READ_ONLY.value
        else ProjectDecisionProvenance.MODERN_PROVENANCE_MISSING
    )
    try:
        field = resolve_project_imaging_field(project, resolver)
        targets = resolve_project_acquisition_intent_targets(project, resolver)
        resolve_project_acquisition_intent_progress(project, resolver)
    except (ValueError, TypeError):
        return missing
    if field is None or not targets or "acquisition_intent_progress" not in project:
        return missing
    return ProjectDecisionProvenance.MODERN_AUTHORIZED
