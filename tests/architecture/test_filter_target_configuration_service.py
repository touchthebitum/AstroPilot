import pytest

from decision.services.filter_target_configuration_service import (
    FilterTargetConfigurationService,
)


def _profile():
    return {
        "projects": {
            "IC1396": {
                "hours": 0.0,
                "target_hours": 15.0,
                "importance": 8,
            }
        }
    }


def test_configuration_service_persists_valid_filter_targets():
    profile = _profile()
    saved = {}

    service = FilterTargetConfigurationService(
        load_profile=lambda: profile,
        save_profile=lambda value: saved.setdefault(
            "profile",
            value,
        ),
    )

    result = service.configure(
        project_name="IC1396",
        filter_targets={
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 4.0,
        },
    )

    assert result == {
        "Ha": 6.0,
        "OIII": 5.0,
        "SII": 4.0,
    }

    assert saved["profile"]["projects"]["IC1396"][
        "filter_targets"
    ] == result


def test_configuration_service_rejects_unknown_project():
    profile = _profile()

    service = FilterTargetConfigurationService(
        load_profile=lambda: profile,
        save_profile=lambda value: None,
    )

    with pytest.raises(
        ValueError,
        match="Unknown project",
    ):
        service.configure(
            project_name="UNKNOWN",
            filter_targets={
                "Ha": 15.0,
            },
        )


def test_configuration_service_rejects_negative_hours():
    profile = _profile()

    service = FilterTargetConfigurationService(
        load_profile=lambda: profile,
        save_profile=lambda value: None,
    )

    with pytest.raises(
        ValueError,
        match="non-negative",
    ):
        service.configure(
            project_name="IC1396",
            filter_targets={
                "Ha": -1.0,
                "OIII": 8.0,
                "SII": 8.0,
            },
        )


def test_configuration_service_rejects_inconsistent_total():
    profile = _profile()
    saved = {"called": False}

    def save_profile(value):
        saved["called"] = True

    service = FilterTargetConfigurationService(
        load_profile=lambda: profile,
        save_profile=save_profile,
    )

    with pytest.raises(
        ValueError,
        match="must match target_hours",
    ):
        service.configure(
            project_name="IC1396",
            filter_targets={
                "Ha": 6.0,
                "OIII": 5.0,
                "SII": 2.0,
            },
        )

    assert saved["called"] is False
    assert "filter_targets" not in profile["projects"]["IC1396"]