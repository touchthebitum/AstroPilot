from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)


FILTER_TYPES = ("Ha", "OIII", "SII", "L", "R", "G", "B")


def test_valid_setup_filter_capabilities_are_exact_and_immutable():
    capabilities = SetupFilterCapabilities("samyang_183", FILTER_TYPES)

    assert capabilities.equipment_id == "samyang_183"
    assert capabilities.available_filter_types == FILTER_TYPES
    assert tuple(field.name for field in fields(capabilities)) == (
        "equipment_id",
        "available_filter_types",
    )
    with pytest.raises(FrozenInstanceError):
        capabilities.equipment_id = "replacement"


@pytest.mark.parametrize("equipment_id", ["", "  "])
def test_empty_equipment_id_is_rejected(equipment_id):
    with pytest.raises(ValueError, match="equipment_id must not be empty"):
        SetupFilterCapabilities(equipment_id, FILTER_TYPES)


@pytest.mark.parametrize("equipment_id", [None, 42, object()])
def test_non_string_equipment_id_is_rejected(equipment_id):
    with pytest.raises(TypeError, match="equipment_id must be a string"):
        SetupFilterCapabilities(equipment_id, FILTER_TYPES)


def test_non_tuple_filter_types_are_rejected():
    with pytest.raises(TypeError, match="available_filter_types must be a tuple"):
        SetupFilterCapabilities("samyang_183", ["Ha"])


def test_empty_filter_types_are_rejected():
    with pytest.raises(ValueError, match="available_filter_types must not be empty"):
        SetupFilterCapabilities("samyang_183", ())


@pytest.mark.parametrize("filter_type", ["", "  "])
def test_empty_filter_type_is_rejected(filter_type):
    with pytest.raises(ValueError, match="filter_type must not be empty"):
        SetupFilterCapabilities("samyang_183", (filter_type,))


@pytest.mark.parametrize("filter_type", [None, 42, object()])
def test_non_string_filter_type_is_rejected(filter_type):
    with pytest.raises(TypeError, match="filter_type must be a string"):
        SetupFilterCapabilities("samyang_183", (filter_type,))


def test_duplicate_filter_type_is_rejected():
    with pytest.raises(ValueError, match="must not contain duplicates"):
        SetupFilterCapabilities("samyang_183", ("Ha", "Ha"))


def test_identifiers_are_not_trimmed_or_case_normalized():
    capabilities = SetupFilterCapabilities(
        " Samyang_183 ",
        ("Ha", "ha", " Ha "),
    )

    assert capabilities.equipment_id == " Samyang_183 "
    assert capabilities.available_filter_types == ("Ha", "ha", " Ha ")
