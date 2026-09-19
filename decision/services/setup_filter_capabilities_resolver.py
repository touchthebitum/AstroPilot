from collections.abc import Collection

from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)


class SetupFilterCapabilitiesResolutionError(ValueError):
    """Raised when setup filter capabilities cannot be resolved safely."""


class SetupFilterCapabilitiesResolver:
    """Resolve immutable setup filter capabilities by exact equipment ID."""

    def __init__(
        self,
        definitions: Collection[SetupFilterCapabilities],
    ) -> None:
        if not isinstance(definitions, Collection):
            raise TypeError("definitions must be a collection")

        snapshot = tuple(definitions)
        self._definitions_by_equipment_id = self._index(snapshot)

    @staticmethod
    def _index(
        definitions: tuple[SetupFilterCapabilities, ...],
    ) -> dict[str, SetupFilterCapabilities]:
        index: dict[str, SetupFilterCapabilities] = {}
        for definition in definitions:
            if not isinstance(definition, SetupFilterCapabilities):
                raise TypeError(
                    "definitions must contain SetupFilterCapabilities values"
                )
            if definition.equipment_id in index:
                raise SetupFilterCapabilitiesResolutionError(
                    f"duplicate equipment_id: {definition.equipment_id}"
                )
            index[definition.equipment_id] = definition
        return index

    def resolve(self, equipment_id: str) -> SetupFilterCapabilities:
        if not isinstance(equipment_id, str) or not equipment_id.strip():
            raise SetupFilterCapabilitiesResolutionError(
                "equipment_id must be a non-empty string"
            )
        try:
            return self._definitions_by_equipment_id[equipment_id]
        except KeyError as error:
            raise SetupFilterCapabilitiesResolutionError(
                f"unknown equipment_id: {equipment_id}"
            ) from error
