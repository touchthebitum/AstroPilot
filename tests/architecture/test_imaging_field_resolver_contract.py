import pytest

from decision.models.imaging_field import (
    AcquisitionIntent,
    CelestialObjectDefinition,
    ImagingFieldComponent,
    ImagingFieldDefinition,
)
from decision.services.imaging_field_resolver import (
    ImagingFieldResolutionError,
    ImagingFieldResolver,
)
from decision.services.legacy_imaging_field_resolver import (
    LegacyImagingFieldResolver,
)


def _celestial_object(
    object_id: str,
    canonical_name: str | None = None,
) -> CelestialObjectDefinition:
    return CelestialObjectDefinition(
        celestial_object_id=object_id,
        canonical_name=canonical_name or object_id,
        object_type="nebula",
    )


def _field(
    field_id: str = "synthetic-field",
    component_ids: tuple[str, ...] = ("synthetic-object",),
    display_name: str = "Synthetic Field",
    acquisition_intents: tuple[AcquisitionIntent, ...] = (),
) -> ImagingFieldDefinition:
    return ImagingFieldDefinition(
        imaging_field_id=field_id,
        display_name=display_name,
        components=tuple(
            ImagingFieldComponent(celestial_object_id=component_id)
            for component_id in component_ids
        ),
        acquisition_intents=acquisition_intents,
    )


def test_resolves_known_imaging_field():
    field = _field()
    resolver = ImagingFieldResolver(
        [field],
        [_celestial_object("synthetic-object")],
    )

    assert resolver.resolve("synthetic-field") is field


def test_resolves_celestial_objects_independently():
    first = _celestial_object("first-object")
    second = _celestial_object("second-object")
    resolver = ImagingFieldResolver(
        [_field(component_ids=("first-object", "second-object"))],
        [first, second],
    )

    assert resolver.resolve_object("first-object") is first
    assert resolver.resolve_object("second-object") is second


def test_resolves_composite_field_with_two_components_and_intents():
    field = _field(
        component_ids=("first-object", "second-object"),
        acquisition_intents=(
            AcquisitionIntent("first-ha", "Ha", ("first-object",)),
            AcquisitionIntent("second-oiii", "OIII", ("second-object",)),
        ),
    )
    resolver = ImagingFieldResolver(
        [field],
        [
            _celestial_object("first-object"),
            _celestial_object("second-object"),
        ],
    )

    resolved = resolver.resolve("synthetic-field")

    assert len(resolved.components) == 2
    assert resolved.acquisition_intents == field.acquisition_intents


@pytest.mark.parametrize("field_id", ["unknown-field", "", 42])
def test_rejects_unknown_or_invalid_imaging_field_id(field_id):
    resolver = ImagingFieldResolver([], [])

    with pytest.raises(ImagingFieldResolutionError):
        resolver.resolve(field_id)


@pytest.mark.parametrize("object_id", ["unknown-object", "  ", 42])
def test_rejects_unknown_or_invalid_celestial_object_id(object_id):
    resolver = ImagingFieldResolver([], [])

    with pytest.raises(ImagingFieldResolutionError):
        resolver.resolve_object(object_id)


@pytest.mark.parametrize(
    "field_id",
    [" synthetic-field ", "SYNTHETIC-FIELD"],
)
def test_does_not_normalize_imaging_field_ids(field_id):
    resolver = ImagingFieldResolver(
        [_field()],
        [_celestial_object("synthetic-object")],
    )

    with pytest.raises(ImagingFieldResolutionError):
        resolver.resolve(field_id)


@pytest.mark.parametrize(
    "object_id",
    [" synthetic-object ", "SYNTHETIC-OBJECT"],
)
def test_does_not_normalize_celestial_object_ids(object_id):
    resolver = ImagingFieldResolver(
        [_field()],
        [_celestial_object("synthetic-object")],
    )

    with pytest.raises(ImagingFieldResolutionError):
        resolver.resolve_object(object_id)


@pytest.mark.parametrize(
    "component_ids",
    [
        ("missing-object", "known-object"),
        ("known-object", "missing-object"),
    ],
)
def test_construction_rejects_any_missing_component(component_ids):
    with pytest.raises(
        ImagingFieldResolutionError,
        match="missing-object",
    ):
        ImagingFieldResolver(
            [_field(component_ids=component_ids)],
            [_celestial_object("known-object")],
        )


def test_construction_rejects_duplicate_imaging_field_ids():
    with pytest.raises(
        ImagingFieldResolutionError,
        match="duplicate imaging_field_id",
    ):
        ImagingFieldResolver(
            [_field(), _field(display_name="Renamed Field")],
            [_celestial_object("synthetic-object")],
        )


def test_construction_rejects_duplicate_celestial_object_ids():
    with pytest.raises(
        ImagingFieldResolutionError,
        match="duplicate celestial_object_id",
    ):
        ImagingFieldResolver(
            [],
            [
                _celestial_object("same-object", "First Name"),
                _celestial_object("same-object", "Second Name"),
            ],
        )


@pytest.mark.parametrize(
    ("imaging_fields", "celestial_objects", "expected_message"),
    [
        ([object()], [], "ImagingFieldDefinition"),
        ([], [object()], "CelestialObjectDefinition"),
        (iter(()), [], "imaging_fields must be a collection"),
        ([], iter(()), "celestial_objects must be a collection"),
    ],
)
def test_construction_rejects_wrong_types(
    imaging_fields,
    celestial_objects,
    expected_message,
):
    with pytest.raises(TypeError, match=expected_message):
        ImagingFieldResolver(imaging_fields, celestial_objects)


def test_renaming_labels_does_not_change_identity():
    original = _field(display_name="Original Field Label")
    renamed = _field(display_name="Renamed Field Label")
    original_object = _celestial_object(
        "synthetic-object",
        "Original Object Label",
    )
    renamed_object = _celestial_object(
        "synthetic-object",
        "Renamed Object Label",
    )

    original_resolver = ImagingFieldResolver([original], [original_object])
    renamed_resolver = ImagingFieldResolver([renamed], [renamed_object])

    assert original_resolver.resolve("synthetic-field").imaging_field_id == (
        renamed_resolver.resolve("synthetic-field").imaging_field_id
    )
    assert original_resolver.resolve_object(
        "synthetic-object"
    ).celestial_object_id == renamed_resolver.resolve_object(
        "synthetic-object"
    ).celestial_object_id


def test_source_collection_mutation_does_not_change_resolver():
    fields = [_field()]
    objects = [_celestial_object("synthetic-object")]
    resolver = ImagingFieldResolver(fields, objects)

    fields.clear()
    fields.append(_field("replacement-field", ("replacement-object",)))
    objects.clear()
    objects.append(_celestial_object("replacement-object"))

    assert resolver.resolve("synthetic-field").imaging_field_id == (
        "synthetic-field"
    )
    assert resolver.resolve_object(
        "synthetic-object"
    ).celestial_object_id == "synthetic-object"
    with pytest.raises(ImagingFieldResolutionError):
        resolver.resolve("replacement-field")
    with pytest.raises(ImagingFieldResolutionError):
        resolver.resolve_object("replacement-object")


def test_legacy_resolver_keeps_its_single_object_behavior():
    field = LegacyImagingFieldResolver.resolve(
        catalog_key="SyntheticTarget",
        catalog_entry={
            "name": "Synthetic Target",
            "type": "nebula",
        },
    )

    assert field.imaging_field_id == "SyntheticTarget"
    assert field.components == (
        ImagingFieldComponent(celestial_object_id="SyntheticTarget"),
    )
    assert field.acquisition_intents == ()
