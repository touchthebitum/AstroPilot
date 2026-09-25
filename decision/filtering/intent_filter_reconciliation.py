from collections.abc import Iterable

from decision.definitions.production_imaging_fields import (
    build_production_imaging_field_resolver,
)
from decision.filtering.selected_filter import SelectedFilter


SELECTED_FILTER_INTENT_MISMATCH = "selected_filter_intent_mismatch"


def resolve_required_filter_type(
    imaging_field_id: str,
    acquisition_intent_id: str,
) -> str:
    imaging_field = build_production_imaging_field_resolver().resolve(
        imaging_field_id
    )
    matches = tuple(
        intent
        for intent in imaging_field.acquisition_intents
        if intent.acquisition_intent_id == acquisition_intent_id
    )
    if len(matches) != 1:
        raise ValueError("acquisition_intent_not_in_imaging_field")
    return matches[0].filter_type


def reconcile_selected_filter(
    *,
    imaging_field_id: str,
    acquisition_intent_id: str,
    available_filters: Iterable[SelectedFilter],
    selected_filter: SelectedFilter | None,
) -> SelectedFilter | None:
    required_filter_type = resolve_required_filter_type(
        imaging_field_id,
        acquisition_intent_id,
    )
    if selected_filter is not None and (
        selected_filter.filter_type == required_filter_type
    ):
        return selected_filter
    return next(
        (
            item
            for item in available_filters
            if item.filter_type == required_filter_type
        ),
        None,
    )


def validate_selected_filter_for_intent(
    *,
    imaging_field_id: str | None,
    acquisition_intent_id: str | None,
    selected_filter: SelectedFilter | None,
) -> None:
    if None in (imaging_field_id, acquisition_intent_id, selected_filter):
        return
    required_filter_type = resolve_required_filter_type(
        imaging_field_id,
        acquisition_intent_id,
    )
    if selected_filter.filter_type != required_filter_type:
        raise ValueError(SELECTED_FILTER_INTENT_MISMATCH)
