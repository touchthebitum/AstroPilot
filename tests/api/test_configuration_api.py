import json

import pytest
from fastapi.testclient import TestClient

import astropilot.app as app_module
from astropilot.app import create_app
from astropilot.user_profile import (
    load_user_profile,
    resolve_equipment_definition,
    save_user_profile,
)


def custom_equipment_payload():
    return {
        "optics_manufacturer": "Askar",
        "optics_model": "FRA300",
        "focal_length_mm": 300,
        "aperture_mm": 60,
        "f_ratio": 5,
        "camera_manufacturer": "ZWO",
        "camera_model": "ASI533MM",
        "pixel_size_um": 3.76,
        "sensor_width_px": 3008,
        "sensor_height_px": 3008,
        "monochrome": True,
    }


def configuration_payload(*, equipment=None, projects=None, revision=None):
    payload = {
        "site": {
            "name": "  La Chaux-de-Fonds  ",
            "latitude": 47.1035,
            "longitude": 6.8328,
            "bortle": 4,
        },
        "equipment": equipment or {"preset_id": "samyang_183"},
        "projects": {} if projects is None else projects,
    }
    if revision is not None:
        payload["expected_revision"] = revision
    return payload


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    return TestClient(create_app())


def test_missing_profile_reports_first_run_without_filesystem_details(client):
    response = client.get("/v1/configuration")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["profile_revision"] is None
    assert payload["site"] is None
    assert payload["active_equipment_id"] is None
    assert payload["available_equipment"] == []
    assert payload["projects"] == {}
    assert all(choice["name"] for choice in payload["preset_equipment"])
    assert "ASTROPILOT_DATA_DIR" not in response.text
    assert "user_profile.json" not in response.text


def test_get_projects_safe_preset_profile_and_omits_internal_state(
    client,
    tmp_path,
):
    response = client.put("/v1/configuration", json=configuration_payload())
    assert response.status_code == 200
    profile = load_user_profile()
    profile["sessions"] = [{"date": "2026-09-01", "object": "M31", "hours": 1}]
    profile["portfolio_credit_applications"] = {"credit-secret": {}}
    (tmp_path / "user_profile.json").write_text(
        json.dumps(profile),
        encoding="utf-8",
    )

    response = client.get("/v1/configuration")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["site"] == {
        "name": "La Chaux-de-Fonds",
        "latitude": 47.1035,
        "longitude": 6.8328,
        "bortle": 4,
    }
    assert payload["active_equipment_id"] == "samyang_183"
    assert payload["available_equipment"][0]["kind"] == "preset"
    assert "sessions" not in payload
    assert "portfolio_credit_applications" not in payload
    assert "credit-secret" not in response.text


def test_first_run_preset_with_zero_projects_is_canonical(client):
    response = client.put("/v1/configuration", json=configuration_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["profile_revision"] == 1
    assert payload["projects"] == {}
    profile = load_user_profile()
    assert profile["location"]["name"] == "La Chaux-de-Fonds"
    assert profile["preferences"]["bortle"] == 4
    assert profile["active_equipment"] == "samyang_183"
    assert profile["available_equipment"] == ["samyang_183"]
    assert "equipment_definitions" not in profile
    assert profile["projects"] == {}


def test_custom_equipment_round_trips_and_resolves(client):
    response = client.put(
        "/v1/configuration",
        json=configuration_payload(
            equipment={"custom": custom_equipment_payload()},
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    equipment_id = payload["active_equipment_id"]
    assert equipment_id == "custom"
    assert payload["available_equipment"] == [
        {
            "id": "custom",
            "name": "Askar FRA300 + ZWO ASI533MM",
            "kind": "custom",
            **custom_equipment_payload(),
        }
    ]
    resolved = resolve_equipment_definition(load_user_profile(), equipment_id)
    assert resolved["sensor_width_mm"] == pytest.approx(11.31008)
    assert client.get("/v1/configuration").json() == payload


def test_valid_simple_project_round_trips_without_fabricated_fields(client):
    project = {"target_hours": 10, "hours": 0, "importance": 8}

    response = client.put(
        "/v1/configuration",
        json=configuration_payload(projects={"M31": project}),
    )

    assert response.status_code == 200
    assert response.json()["projects"] == {"M31": project}
    assert load_user_profile()["projects"] == {"M31": project}


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda payload: payload["site"].update(name="   "),
            "configuration_invalid_site",
        ),
        (
            lambda payload: payload["site"].update(bortle=10),
            "configuration_invalid_bortle",
        ),
        (
            lambda payload: payload["equipment"].update(
                preset_id="missing-internal-id"
            ),
            "configuration_invalid_equipment",
        ),
        (
            lambda payload: payload.update(
                equipment={"custom": {**custom_equipment_payload(), "f_ratio": 0}}
            ),
            "configuration_invalid_custom_equipment",
        ),
        (
            lambda payload: payload.update(
                projects={"M31": {"target_hours": 1, "hours": 2}}
            ),
            "configuration_invalid_project",
        ),
        (
            lambda payload: payload.update(
                projects={"UNKNOWN": {"target_hours": 1, "hours": 0}}
            ),
            "configuration_invalid_project",
        ),
    ],
)
def test_invalid_configuration_fails_closed_without_partial_profile(
    client,
    tmp_path,
    mutate,
    expected_code,
):
    payload = configuration_payload()
    mutate(payload)

    response = client.put("/v1/configuration", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == expected_code
    assert not (tmp_path / "user_profile.json").exists()
    assert "ASTROPILOT_DATA_DIR" not in response.text
    assert str(tmp_path) not in response.text
    assert "Traceback" not in response.text


def test_corrupt_profile_fails_closed_without_path_disclosure(client, tmp_path):
    (tmp_path / "user_profile.json").write_text("{broken", encoding="utf-8")

    response = client.get("/v1/configuration")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "configuration_corrupt",
            "message": "The saved configuration is invalid.",
        }
    }
    assert str(tmp_path) not in response.text


def test_correct_revision_updates_once_and_stale_revision_preserves_newer_state(
    client,
):
    created = client.put(
        "/v1/configuration",
        json=configuration_payload(),
    ).json()
    update = configuration_payload(revision=created["profile_revision"])
    update["site"]["name"] = "Mont Sujet"

    updated_response = client.put("/v1/configuration", json=update)

    assert updated_response.status_code == 200
    assert updated_response.json()["profile_revision"] == 2
    stale = configuration_payload(revision=1)
    stale["site"]["name"] = "Stale writer"
    stale_response = client.put("/v1/configuration", json=stale)
    assert stale_response.status_code == 409
    assert stale_response.json()["detail"]["code"] == (
        "configuration_revision_conflict"
    )
    persisted = load_user_profile()
    assert persisted["profile_revision"] == 2
    assert persisted["location"]["name"] == "Mont Sujet"


def test_update_preserves_non_ui_profile_state(client):
    created = client.put(
        "/v1/configuration",
        json=configuration_payload(
            projects={"M31": {"target_hours": 10, "hours": 1}},
        ),
    ).json()
    profile = load_user_profile()
    profile["sessions"] = [
        {"date": "2026-09-01", "object": "M31", "hours": 1}
    ]
    profile["portfolio_credit_applications"] = {}
    profile["decision_weights"] = {"altitude": 1.0}
    persisted = save_user_profile(
        profile,
        expected_revision=created["profile_revision"],
    )
    update = configuration_payload(
        projects={"M31": {"target_hours": 10, "hours": 1}},
        revision=persisted["profile_revision"],
    )
    update["site"]["name"] = "Mont Sujet"

    response = client.put("/v1/configuration", json=update)

    assert response.status_code == 200
    updated = load_user_profile()
    assert updated["sessions"] == profile["sessions"]
    assert updated["portfolio_credit_applications"] == {}
    assert updated["decision_weights"] == {"altitude": 1.0}


def test_persistence_failure_has_safe_controlled_error(
    client,
    monkeypatch,
):
    def unavailable(*args, **kwargs):
        raise OSError("private storage detail")

    monkeypatch.setattr(
        app_module,
        "create_or_replace_user_configuration",
        unavailable,
    )

    response = client.put("/v1/configuration", json=configuration_payload())

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "configuration_persistence_error",
            "message": "The configuration could not be saved.",
        }
    }
    assert "private storage detail" not in response.text


def test_existing_profile_requires_expected_revision(client):
    assert client.put(
        "/v1/configuration",
        json=configuration_payload(),
    ).status_code == 200

    response = client.put("/v1/configuration", json=configuration_payload())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == (
        "configuration_revision_conflict"
    )


def test_rejected_update_does_not_increment_revision(client):
    created = client.put(
        "/v1/configuration",
        json=configuration_payload(),
    ).json()
    invalid = configuration_payload(revision=created["profile_revision"])
    invalid["projects"] = {"M31": {"target_hours": 1, "hours": 2}}

    response = client.put("/v1/configuration", json=invalid)

    assert response.status_code == 422
    assert load_user_profile()["profile_revision"] == 1
