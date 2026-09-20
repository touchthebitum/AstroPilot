from collections.abc import Collection

from decision.models.equipment.filter_optical_profile import (
    FilterOpticalProfile,
)


class FilterOpticalProfileResolutionError(ValueError):
    """Raised when a filter optical profile cannot be resolved safely."""


class FilterOpticalProfileResolver:
    """Resolve concrete filter profiles by exact stable profile identity."""

    def __init__(
        self,
        definitions: Collection[FilterOpticalProfile],
    ) -> None:
        if not isinstance(definitions, Collection):
            raise TypeError("definitions must be a collection")

        snapshot = tuple(definitions)
        self._definitions_by_filter_profile_id = self._index(snapshot)

    @staticmethod
    def _index(
        definitions: tuple[FilterOpticalProfile, ...],
    ) -> dict[str, FilterOpticalProfile]:
        index: dict[str, FilterOpticalProfile] = {}
        for definition in definitions:
            if not isinstance(definition, FilterOpticalProfile):
                raise TypeError(
                    "definitions must contain FilterOpticalProfile values"
                )
            if definition.filter_profile_id in index:
                raise FilterOpticalProfileResolutionError(
                    "duplicate filter_profile_id: "
                    f"{definition.filter_profile_id}"
                )
            index[definition.filter_profile_id] = definition
        return index

    def resolve(self, filter_profile_id: str) -> FilterOpticalProfile:
        if (
            not isinstance(filter_profile_id, str)
            or not filter_profile_id.strip()
        ):
            raise FilterOpticalProfileResolutionError(
                "filter_profile_id must be a non-empty string"
            )
        try:
            return self._definitions_by_filter_profile_id[filter_profile_id]
        except KeyError as error:
            raise FilterOpticalProfileResolutionError(
                f"unknown filter_profile_id: {filter_profile_id}"
            ) from error
