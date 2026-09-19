import pytest

from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.services.setup_filter_capabilities_resolver import (
    SetupFilterCapabilitiesResolutionError,
    SetupFilterCapabilitiesResolver,
)


def _capabilities(
    equipment_id: str = "samyang_183",
) -> SetupFilterCapabilities:
    return SetupFilterCapabilities(equipment_id, ("Ha", "OIII"))


def test_resolves_equipment_id_exactly():
    capabilities = _capabilities()
    resolver = SetupFilterCapabilitiesResolver([capabilities])

    assert resolver.resolve("samyang_183") is capabilities


@pytest.mark.parametrize("equipment_id", ["unknown", "", "  ", None, 42])
def test_rejects_unknown_empty_or_non_string_equipment_id(equipment_id):
    resolver = SetupFilterCapabilitiesResolver([_capabilities()])

    with pytest.raises(SetupFilterCapabilitiesResolutionError):
        resolver.resolve(equipment_id)


@pytest.mark.parametrize("equipment_id", [" samyang_183 ", "SAMYANG_183"])
def test_does_not_normalize_equipment_id(equipment_id):
    resolver = SetupFilterCapabilitiesResolver([_capabilities()])

    with pytest.raises(SetupFilterCapabilitiesResolutionError):
        resolver.resolve(equipment_id)


def test_rejects_duplicate_equipment_definitions():
    with pytest.raises(
        SetupFilterCapabilitiesResolutionError,
        match="duplicate equipment_id",
    ):
        SetupFilterCapabilitiesResolver(
            [_capabilities(), _capabilities()]
        )


def test_rejects_wrong_type_in_collection():
    with pytest.raises(TypeError, match="SetupFilterCapabilities"):
        SetupFilterCapabilitiesResolver([object()])


def test_rejects_non_collection_input():
    with pytest.raises(TypeError, match="definitions must be a collection"):
        SetupFilterCapabilitiesResolver(iter(()))


def test_source_collection_mutation_does_not_change_resolver():
    original = _capabilities()
    definitions = [original]
    resolver = SetupFilterCapabilitiesResolver(definitions)

    definitions.clear()
    definitions.append(_capabilities("replacement"))

    assert resolver.resolve("samyang_183") is original
    with pytest.raises(SetupFilterCapabilitiesResolutionError):
        resolver.resolve("replacement")
