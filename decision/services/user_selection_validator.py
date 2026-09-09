from dataclasses import dataclass

from decision.models.user_selection import UserSelection, UserSelectionSource


class UserSelectionValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UserSelectionDecisionContext:
    decision_id: str
    primary_catalog_key: str | None
    exposed_alternative_catalog_keys: tuple[str, ...]
    explicitly_evaluated_catalog_keys: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.decision_id, str) or not self.decision_id.strip():
            raise ValueError("decision_id_required")
        if self.primary_catalog_key is not None and (
            not isinstance(self.primary_catalog_key, str)
            or not self.primary_catalog_key.strip()
        ):
            raise ValueError("invalid_primary_catalog_key")

        for name in (
            "exposed_alternative_catalog_keys",
            "explicitly_evaluated_catalog_keys",
        ):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"invalid_{name}")
            object.__setattr__(self, name, values)


def validate_user_selection(
    selection: UserSelection,
    decision_context: UserSelectionDecisionContext,
) -> UserSelection:
    if not isinstance(selection, UserSelection):
        raise TypeError("Expected UserSelection")
    if not isinstance(decision_context, UserSelectionDecisionContext):
        raise TypeError("Expected UserSelectionDecisionContext")
    if selection.decision_id != decision_context.decision_id:
        raise UserSelectionValidationError("user_selection_decision_mismatch")

    if selection.source is UserSelectionSource.PRIMARY_RECOMMENDATION:
        if selection.selected_catalog_key != decision_context.primary_catalog_key:
            raise UserSelectionValidationError(
                "selected_target_not_primary_recommendation"
            )
    elif selection.source is UserSelectionSource.ALTERNATIVE:
        if (
            selection.selected_catalog_key
            not in decision_context.exposed_alternative_catalog_keys
        ):
            raise UserSelectionValidationError(
                "selected_target_not_exposed_alternative"
            )
    elif selection.source is UserSelectionSource.OTHER_EVALUATED_TARGET:
        if (
            selection.selected_catalog_key
            not in decision_context.explicitly_evaluated_catalog_keys
        ):
            raise UserSelectionValidationError(
                "selected_target_not_explicitly_evaluated"
            )

    return selection
