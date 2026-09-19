import copy

import pytest

from decision.definitions.production_imaging_fields import (
    IMAGING_FIELD_DEFINITIONS,
    build_production_imaging_field_resolver,
)
from decision.services.legacy_imaging_field_resolver import (
    LegacyImagingFieldResolver,
)
from decision.services.project_imaging_field_resolution import (
    ProjectImagingFieldResolutionError,
    resolve_project_imaging_field,
)


def test_legacy_project_without_reference_returns_none_without_mutation():
    project = {"hours": 0, "target_hours": 18, "importance": 9}
    original = copy.deepcopy(project)

    resolved = resolve_project_imaging_field(
        project,
        build_production_imaging_field_resolver(),
    )

    assert resolved is None
    assert project == original
    assert "imaging_field_id" not in project


def test_resolves_exact_production_composite_definition():
    resolved = resolve_project_imaging_field(
        {"imaging_field_id": "sh2-129_ou4"},
        build_production_imaging_field_resolver(),
    )

    assert resolved is IMAGING_FIELD_DEFINITIONS[0]
    assert tuple(
        component.celestial_object_id for component in resolved.components
    ) == ("sh2-129", "ou4")


@pytest.mark.parametrize(
    "invalid_reference",
    ["", "   ", 42, None, "unknown-field"],
)
def test_rejects_invalid_or_unknown_explicit_reference(invalid_reference):
    with pytest.raises(ProjectImagingFieldResolutionError):
        resolve_project_imaging_field(
            {"imaging_field_id": invalid_reference},
            build_production_imaging_field_resolver(),
        )


def test_unknown_explicit_reference_never_uses_legacy_fallback(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("legacy fallback must not be called")

    monkeypatch.setattr(LegacyImagingFieldResolver, "resolve", fail_if_called)

    with pytest.raises(ProjectImagingFieldResolutionError):
        resolve_project_imaging_field(
            {"imaging_field_id": "Sh2-129"},
            build_production_imaging_field_resolver(),
        )


@pytest.mark.parametrize(
    "invalid_reference",
    ["SH2-129_OU4", " sh2-129_ou4", "sh2-129_ou4 "],
)
def test_explicit_reference_is_exact_id_only(invalid_reference):
    with pytest.raises(ProjectImagingFieldResolutionError):
        resolve_project_imaging_field(
            {"imaging_field_id": invalid_reference},
            build_production_imaging_field_resolver(),
        )
