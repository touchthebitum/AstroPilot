from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.imaging_field import (
    AcquisitionIntent,
    CelestialObjectDefinition,
    ImagingFieldComponent,
    ImagingFieldDefinition,
)
from decision.services.legacy_imaging_field_resolver import (
    LegacyImagingFieldResolver,
)


def _component(component_id: str = "synthetic-nebula") -> ImagingFieldComponent:
    return ImagingFieldComponent(celestial_object_id=component_id)


def _intent(
    intent_id: str = "synthetic-nebula_ha",
    component_ids: tuple[str, ...] = ("synthetic-nebula",),
) -> AcquisitionIntent:
    return AcquisitionIntent(
        acquisition_intent_id=intent_id,
        filter_type="Ha",
        primary_component_ids=component_ids,
    )


def test_simple_imaging_field_is_valid_and_immutable():
    celestial_object = CelestialObjectDefinition(
        celestial_object_id="synthetic-nebula",
        canonical_name="Synthetic Nebula",
        object_type="nebula",
        object_subtype="emission",
    )
    field = ImagingFieldDefinition(
        imaging_field_id="synthetic-nebula",
        display_name="Synthetic Nebula",
        components=(_component(),),
        acquisition_intents=(_intent(),),
    )

    assert celestial_object.celestial_object_id == (
        field.components[0].celestial_object_id
    )
    assert field.acquisition_intents == (_intent(),)
    with pytest.raises(FrozenInstanceError):
        field.display_name = "Changed"


def test_composite_imaging_field_is_valid():
    field = ImagingFieldDefinition(
        imaging_field_id="synthetic-composite",
        display_name="Synthetic Composite",
        components=(
            _component("synthetic-nebula"),
            _component("synthetic-remnant"),
        ),
        acquisition_intents=(
            _intent("synthetic-nebula_ha", ("synthetic-nebula",)),
            AcquisitionIntent(
                acquisition_intent_id="synthetic-remnant_oiii",
                filter_type="OIII",
                primary_component_ids=("synthetic-remnant",),
            ),
        ),
    )

    assert len(field.components) == 2
    assert len(field.acquisition_intents) == 2


def test_duplicate_component_is_rejected():
    with pytest.raises(ValueError, match="duplicate celestial_object_id"):
        ImagingFieldDefinition(
            imaging_field_id="synthetic-field",
            display_name="Synthetic Field",
            components=(_component(), _component()),
            acquisition_intents=(),
        )


def test_duplicate_acquisition_intent_id_is_rejected():
    with pytest.raises(ValueError, match="duplicate acquisition_intent_id"):
        ImagingFieldDefinition(
            imaging_field_id="synthetic-field",
            display_name="Synthetic Field",
            components=(_component(),),
            acquisition_intents=(_intent(), _intent()),
        )


def test_intent_with_missing_component_reference_is_rejected():
    with pytest.raises(ValueError, match="unknown primary component"):
        ImagingFieldDefinition(
            imaging_field_id="synthetic-field",
            display_name="Synthetic Field",
            components=(_component(),),
            acquisition_intents=(
                _intent(component_ids=("absent-component",)),
            ),
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CelestialObjectDefinition("", "Object", "nebula"),
        lambda: ImagingFieldComponent("  "),
        lambda: AcquisitionIntent("", "Ha", ("component",)),
        lambda: ImagingFieldDefinition("", "Field", (_component(),), ()),
    ],
)
def test_empty_identifiers_are_rejected(factory):
    with pytest.raises(ValueError, match="must not be empty"):
        factory()


def test_empty_filter_type_is_rejected():
    with pytest.raises(ValueError, match="filter_type must not be empty"):
        AcquisitionIntent("intent", "  ", ("component",))


def test_intent_without_primary_components_is_rejected():
    with pytest.raises(ValueError, match="primary_component_ids must not be empty"):
        AcquisitionIntent("intent", "Ha", ())


def test_intent_with_duplicate_primary_component_is_rejected():
    with pytest.raises(ValueError, match="must not contain duplicates"):
        AcquisitionIntent(
            "intent",
            "Ha",
            ("component", "component"),
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AcquisitionIntent("intent", "Ha", ["component"]),
        lambda: ImagingFieldDefinition(
            "field",
            "Field",
            [_component()],
            (),
        ),
        lambda: ImagingFieldDefinition(
            "field",
            "Field",
            (_component(),),
            [_intent()],
        ),
    ],
)
def test_mutable_domain_collections_are_rejected(factory):
    with pytest.raises(TypeError, match="must be a tuple"):
        factory()


def test_legacy_adapter_builds_a_simple_field_from_synthetic_catalog_data():
    field = LegacyImagingFieldResolver.resolve(
        catalog_key="SyntheticTarget",
        catalog_entry={
            "name": "Synthetic Target",
            "type": "nebula",
            "subtype": "emission",
        },
    )

    assert field == ImagingFieldDefinition(
        imaging_field_id="SyntheticTarget",
        display_name="Synthetic Target",
        components=(
            ImagingFieldComponent(celestial_object_id="SyntheticTarget"),
        ),
        acquisition_intents=(),
    )


def test_legacy_adapter_identity_is_deterministic():
    catalog_entry = {"name": "Synthetic Target", "type": "galaxy"}

    first = LegacyImagingFieldResolver.resolve(
        catalog_key="SyntheticTarget",
        catalog_entry=catalog_entry,
    )
    second = LegacyImagingFieldResolver.resolve(
        catalog_key="SyntheticTarget",
        catalog_entry=dict(catalog_entry),
    )

    assert first.imaging_field_id == second.imaging_field_id
    assert first.components == second.components


def test_display_name_does_not_define_legacy_identity():
    first = LegacyImagingFieldResolver.resolve(
        catalog_key="SyntheticTarget",
        catalog_entry={"name": "First Label", "type": "nebula"},
    )
    renamed = LegacyImagingFieldResolver.resolve(
        catalog_key="SyntheticTarget",
        catalog_entry={"name": "Renamed Label", "type": "nebula"},
    )

    assert first.display_name != renamed.display_name
    assert first.imaging_field_id == renamed.imaging_field_id
    assert first.components == renamed.components


def test_domain_references_use_stable_ids_instead_of_display_names():
    component_fields = {field.name for field in fields(ImagingFieldComponent)}
    intent_fields = {field.name for field in fields(AcquisitionIntent)}

    assert "display_name" not in component_fields
    assert "celestial_object_id" in component_fields
    assert "display_name" not in intent_fields
    assert "primary_component_ids" in intent_fields


@pytest.mark.parametrize(
    ("catalog_key", "catalog_entry", "expected_message"),
    [
        ("", {"name": "Target", "type": "nebula"}, "catalog_key"),
        ("Target", {"type": "nebula"}, "name"),
        ("Target", {"name": "Target"}, "type"),
    ],
)
def test_legacy_adapter_fails_closed_on_incomplete_identity_data(
    catalog_key,
    catalog_entry,
    expected_message,
):
    with pytest.raises(ValueError, match=expected_message):
        LegacyImagingFieldResolver.resolve(
            catalog_key=catalog_key,
            catalog_entry=catalog_entry,
        )
