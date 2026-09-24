import pytest

from decision.models.imaging_field import (
    AcquisitionIntent,
    CelestialObjectDefinition,
    ImagingFieldComponent,
    ImagingFieldDefinition,
)
from decision.models.project_acquisition_intent_target import (
    ProjectAcquisitionIntentTarget,
)
from decision.services.imaging_field_resolver import ImagingFieldResolver
from decision.services.project_acquisition_intent_targets import (
    ProjectAcquisitionIntentTargetsError,
    resolve_project_acquisition_intent_targets,
)


def resolver() -> ImagingFieldResolver:
    objects = (
        CelestialObjectDefinition("component-a", "A", "nebula"),
        CelestialObjectDefinition("component-b", "B", "nebula"),
    )
    fields = (
        ImagingFieldDefinition(
            imaging_field_id="field-a",
            display_name="Field A",
            components=(ImagingFieldComponent("component-a"),),
            acquisition_intents=(
                AcquisitionIntent(
                    acquisition_intent_id="shared-filter-a",
                    filter_type="OIII",
                    primary_component_ids=("component-a",),
                    label="OIII · Component A",
                ),
            ),
        ),
        ImagingFieldDefinition(
            imaging_field_id="field-b",
            display_name="Field B",
            components=(ImagingFieldComponent("component-b"),),
            acquisition_intents=(
                AcquisitionIntent(
                    acquisition_intent_id="shared-filter-b",
                    filter_type="OIII",
                    primary_component_ids=("component-b",),
                    label="OIII · Component B",
                ),
            ),
        ),
    )
    return ImagingFieldResolver(fields, objects)


def target(intent_id="shared-filter-a", hours=5.0):
    return {
        "acquisition_intent_id": intent_id,
        "target_hours": hours,
    }


def test_returns_an_immutable_typed_snapshot_for_valid_targets():
    resolved = resolve_project_acquisition_intent_targets(
        {
            "imaging_field_id": "field-a",
            "acquisition_intent_targets": [target()],
        },
        resolver(),
    )

    assert resolved == (
        ProjectAcquisitionIntentTarget("shared-filter-a", 5.0),
    )


def test_legacy_project_without_targets_or_field_remains_valid():
    assert resolve_project_acquisition_intent_targets({}, resolver()) == ()


def test_rejects_an_intent_owned_by_another_field_despite_same_filter():
    with pytest.raises(
        ProjectAcquisitionIntentTargetsError,
        match="does not belong",
    ):
        resolve_project_acquisition_intent_targets(
            {
                "imaging_field_id": "field-a",
                "acquisition_intent_targets": [target("shared-filter-b")],
            },
            resolver(),
        )


@pytest.mark.parametrize(
    "targets",
    [
        [target(), target()],
        [target("")],
        [target(42)],
        [target(hours="5")],
        [target(hours=float("nan"))],
        [target(hours=float("inf"))],
        [target(hours=0)],
        [target(hours=-1)],
    ],
)
def test_rejects_invalid_target_values(targets):
    with pytest.raises(ProjectAcquisitionIntentTargetsError):
        resolve_project_acquisition_intent_targets(
            {
                "imaging_field_id": "field-a",
                "acquisition_intent_targets": targets,
            },
            resolver(),
        )


def test_targets_never_infer_an_intent_from_filter_type():
    with pytest.raises(ProjectAcquisitionIntentTargetsError):
        resolve_project_acquisition_intent_targets(
            {
                "imaging_field_id": "field-a",
                "acquisition_intent_targets": [
                    {
                        "filter_type": "OIII",
                        "target_hours": 5,
                    }
                ],
            },
            resolver(),
        )


def test_targets_require_an_explicit_imaging_field_even_when_empty():
    with pytest.raises(
        ProjectAcquisitionIntentTargetsError,
        match="require imaging_field_id",
    ):
        resolve_project_acquisition_intent_targets(
            {"acquisition_intent_targets": []},
            resolver(),
        )
