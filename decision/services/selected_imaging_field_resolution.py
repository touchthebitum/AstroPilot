from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from decision.definitions.production_imaging_fields import (
    build_production_imaging_field_resolver,
)
from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelectionStatus,
)
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.services.project_imaging_field_resolution import (
    ProjectImagingFieldResolutionError,
    resolve_project_imaging_field,
)

if TYPE_CHECKING:
    from decision.services.decision_acceptance_application import (
        DecisionAcceptanceContext,
    )


class SelectedImagingFieldResolutionError(ValueError):
    pass


class SelectedAcquisitionIntentResolutionError(ValueError):
    pass


def acquisition_intent_provenance_expected(
    context: DecisionAcceptanceContext,
    selection: UserSelection,
) -> bool:
    if selection.source is UserSelectionSource.DECLINED:
        return False
    try:
        candidate = _candidate_for_selection(context, selection)
    except SelectedImagingFieldResolutionError as exc:
        if selection.source is UserSelectionSource.OTHER_EVALUATED_TARGET:
            opportunity = getattr(context.recommendation, "opportunity", None)
            shortlist = getattr(opportunity, "shortlist_entries", None)
            if not isinstance(shortlist, tuple) or not any(
                isinstance(candidate, Candidate)
                and candidate.catalog_key == selection.selected_catalog_key
                for candidate in shortlist
            ):
                return False
        raise SelectedAcquisitionIntentResolutionError(
            "selected_acquisition_intent_not_available"
        ) from exc
    return candidate.acquisition_intent_selection_status is not None


def _resolved_project_imaging_field_id(
    context: DecisionAcceptanceContext,
    catalog_key: str,
) -> str | None:
    profile = context.profile
    if not isinstance(profile, Mapping):
        raise SelectedImagingFieldResolutionError("invalid_profile_snapshot")
    if "projects" not in profile:
        return None
    projects = profile["projects"]
    if not isinstance(projects, Mapping):
        raise SelectedImagingFieldResolutionError("invalid_projects_snapshot")
    if catalog_key not in projects:
        return None
    project = projects[catalog_key]
    if not isinstance(project, Mapping):
        raise SelectedImagingFieldResolutionError("invalid_project_snapshot")
    try:
        resolved = resolve_project_imaging_field(
            project,
            build_production_imaging_field_resolver(),
        )
    except ProjectImagingFieldResolutionError as exc:
        raise SelectedImagingFieldResolutionError(
            "invalid_selected_imaging_field_reference"
        ) from exc
    return None if resolved is None else resolved.imaging_field_id


def _candidate_for_selection(
    context: DecisionAcceptanceContext,
    selection: UserSelection,
) -> Candidate:
    opportunity = getattr(context.recommendation, "opportunity", None)
    if selection.source is UserSelectionSource.PRIMARY_RECOMMENDATION:
        candidate = getattr(opportunity, "candidate", None)
        if (
            not isinstance(candidate, Candidate)
            or candidate.catalog_key != selection.selected_catalog_key
        ):
            raise SelectedImagingFieldResolutionError(
                "selected_candidate_not_found"
            )
        return candidate

    shortlist = getattr(opportunity, "shortlist_entries", None)
    if not isinstance(shortlist, tuple):
        raise SelectedImagingFieldResolutionError(
            "selected_candidate_not_found"
        )
    matches = [
        candidate
        for candidate in shortlist
        if isinstance(candidate, Candidate)
        and candidate.catalog_key == selection.selected_catalog_key
    ]
    if len(matches) != 1:
        raise SelectedImagingFieldResolutionError(
            "selected_candidate_not_found"
        )
    return matches[0]


def resolve_selected_acquisition_intent_id(
    context: DecisionAcceptanceContext,
    selection: UserSelection,
) -> str | None:
    requested = selection.selected_acquisition_intent_id
    if selection.source is UserSelectionSource.DECLINED:
        return None

    try:
        candidate = _candidate_for_selection(context, selection)
    except SelectedImagingFieldResolutionError as exc:
        # Explicitly evaluated legacy targets need not have been exposed as
        # recommendation candidates. They retain the pre-intent behavior.
        if (
            selection.source is UserSelectionSource.OTHER_EVALUATED_TARGET
            and requested is None
        ):
            return None
        raise SelectedAcquisitionIntentResolutionError(
            "selected_acquisition_intent_not_available"
        ) from exc

    status = candidate.acquisition_intent_selection_status
    selected = candidate.selected_acquisition_intent_id
    viable = candidate.viable_acquisition_intent_ids

    if status is None:
        if selected is not None or viable:
            raise SelectedAcquisitionIntentResolutionError(
                "invalid_acquisition_intent_selection_provenance"
            )
        if requested is not None:
            raise SelectedAcquisitionIntentResolutionError(
                "selected_acquisition_intent_not_available"
            )
        return None

    if selected is not None:
        if (
            status not in (
                AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
                AcquisitionIntentSelectionStatus.PREFERRED,
            )
            or viable != (selected,)
        ):
            raise SelectedAcquisitionIntentResolutionError(
                "invalid_acquisition_intent_selection_provenance"
            )
        if requested is None or requested == selected:
            return selected
        raise SelectedAcquisitionIntentResolutionError(
            "selected_acquisition_intent_mismatch"
        )

    if not viable:
        if status is not AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT:
            raise SelectedAcquisitionIntentResolutionError(
                "invalid_acquisition_intent_selection_provenance"
            )
        if requested is not None:
            raise SelectedAcquisitionIntentResolutionError(
                "selected_acquisition_intent_not_available"
            )
        return None

    if (
        len(viable) == 1
        or status is not AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE
    ):
        raise SelectedAcquisitionIntentResolutionError(
            "invalid_acquisition_intent_selection_provenance"
        )
    if requested is None:
        raise SelectedAcquisitionIntentResolutionError(
            "acquisition_intent_selection_required"
        )
    if requested not in viable:
        raise SelectedAcquisitionIntentResolutionError(
            "selected_acquisition_intent_not_viable"
        )
    return requested


def resolve_selected_imaging_field_id(
    context: DecisionAcceptanceContext,
    selection: UserSelection,
) -> str | None:
    if selection.source is UserSelectionSource.DECLINED:
        return None
    catalog_key = selection.selected_catalog_key
    if not isinstance(catalog_key, str) or not catalog_key.strip():
        raise SelectedImagingFieldResolutionError("invalid_selected_catalog_key")

    if selection.source is UserSelectionSource.OTHER_EVALUATED_TARGET:
        return _resolved_project_imaging_field_id(context, catalog_key)

    candidate = _candidate_for_selection(context, selection)
    if candidate.provenance is CandidateProvenance.DISCOVERY:
        authoritative_id = None
    else:
        authoritative_id = _resolved_project_imaging_field_id(
            context,
            catalog_key,
        )
    if candidate.imaging_field_id != authoritative_id:
        raise SelectedImagingFieldResolutionError(
            "selected_imaging_field_mismatch"
        )
    return authoritative_id
