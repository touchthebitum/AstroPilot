"""Scientific identity, nominal geometry and fail-closed material matching."""
from copy import deepcopy
from dataclasses import replace
from math import atan, degrees

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.catalog import CATALOG
from astropilot.equipment_catalog import EQUIPMENT_PROFILES
from astropilot.target_catalogue import (
    SOURCES, TARGETS, canonical_target, equipment_catalogue,
    filter_match, framing_match, sensor_geometry,
)

HA = "baader_ha_highspeed_6_5nm"
OIII = "baader_oiii_highspeed_6_5nm"


def test_samyang_full_sensor_geometry_uses_pixel_array_not_rounded_millimetres():
    geometry = sensor_geometry(EQUIPMENT_PROFILES["samyang_183"])
    assert geometry["sensor_width_mm"] == pytest.approx(13.1904)
    assert geometry["sensor_height_mm"] == pytest.approx(8.8128)
    assert geometry["field_width_deg"] == pytest.approx(5.59373237)
    assert geometry["field_height_deg"] == pytest.approx(3.73894108)
    assert geometry["sampling_arcsec_per_pixel"] == pytest.approx(3.66692989)


def test_focal_length_scales_field_and_sampling_without_changing_working_aperture():
    equipment = deepcopy(EQUIPMENT_PROFILES["samyang_183"])
    equipment["focal_length_mm"] = 270
    g = sensor_geometry(equipment)
    assert g["field_width_deg"] == pytest.approx(degrees(2 * atan(13.1904 / 540)))
    assert g["sampling_arcsec_per_pixel"] == pytest.approx(1.83346494)
    assert equipment["f_ratio"] == 2.8  # no inferred alteration of aperture ring


@pytest.mark.parametrize("key,value", [
    ("focal_length_mm", 0), ("focal_length_mm", float("nan")),
    ("pixel_size_um", True), ("pixel_size_um", float("inf")),
    ("sensor_width_px", 12.5), ("sensor_height_px", -1),
    ("sensor_height_px", None), ("pixel_size_um", "2.4"),
    ("sensor_width_mm", 23.5), ("sensor_height_mm", False),
])
def test_bad_or_inconsistent_equipment_never_gets_a_nominal_fit(key, value):
    equipment = {**EQUIPMENT_PROFILES["samyang_183"], key: value}
    geometry = sensor_geometry(equipment)
    assert geometry["status"] in {"unknown", "inconsistent"}
    assert framing_match(canonical_target("NorthAmerica"), geometry)["status"] == "unknown"


def test_long_axis_alone_does_not_establish_framing_and_unknown_extent_stays_unknown():
    geometry = sensor_geometry(EQUIPMENT_PROFILES["samyang_183"])
    wide_target = replace(canonical_target("NorthAmerica"), extent_arcmin=250)
    assert 250 < geometry["field_width_deg"] * 60
    assert framing_match(wide_target, geometry)["status"] == "requires_framing_check"
    assert framing_match(canonical_target("M45"), geometry)["status"] == "unknown"
    assert framing_match(canonical_target("Ou4"), geometry)["status"] == "unknown"
    assert framing_match(canonical_target("M57"), geometry)["status"] == "small_in_field"
    assert framing_match(canonical_target("IC1396"), geometry)["status"] == "nominal_fit"


@pytest.mark.parametrize("ratio,expected", [(1.79, "outside_documented_range"),
    (1.8, "documented_match"), (2.8, "documented_match"), (3.4, "documented_match"),
    (3.41, "outside_documented_range"), (5.6, "outside_documented_range"),
    (None, "unknown"), (True, "unknown"), (float("nan"), "unknown")])
def test_exact_highspeed_filter_range_is_applied_to_working_f_ratio(ratio, expected):
    equipment = {**EQUIPMENT_PROFILES["samyang_183"], "f_ratio": ratio}
    assert filter_match(canonical_target("NorthAmerica"), equipment, HA)["status"] == expected


def test_no_generic_narrowband_or_unidentified_lrgb_ownership_is_inferred():
    equipment = EQUIPMENT_PROFILES["samyang_183"]
    assert filter_match(canonical_target("M45"), equipment, HA)["status"] == "not_primary_choice"
    assert filter_match(canonical_target("M31"), equipment, "Astronomik LRGB")["status"] == "unknown"
    assert filter_match(canonical_target("Ou4"), equipment, HA)["status"] == "not_primary_choice"
    assert filter_match(canonical_target("Ou4"), equipment, OIII)["status"] == "documented_match"
    color = {**equipment, "monochrome": False}
    assert filter_match(canonical_target("NorthAmerica"), color, HA)["status"] == "unknown"


def test_documented_lrgb_product_is_not_an_invented_transmission_profile_or_confirmed_ownership():
    result = equipment_catalogue(profile={}, equipment_id="samyang_183")
    family = result["reference_filter_families"][0]
    assert family["manufacturer_product_id"] == "10220125"
    assert family["ownership"] == "not_confirmed_by_this_catalogue"
    assert family["transmission_model"] is None
    assert not family["mission_profile_available"]
    assert filter_match(canonical_target("M31"), EQUIPMENT_PROFILES["samyang_183"], family["id"])["status"] == "unknown"


def test_all_legacy_keys_are_covered_without_duplicate_targets_or_migrating_projects():
    assert len(TARGETS) == 20
    assert len({item.key for item in TARGETS}) == len(TARGETS)
    aliases = [alias for item in TARGETS for alias in (item.key, *item.aliases)]
    assert len(aliases) == len(set(aliases))
    assert all(canonical_target(key) is not None for key in CATALOG)
    assert canonical_target("Heart") is canonical_target("IC1805")
    assert canonical_target("Soul") is canonical_target("IC1848")
    assert canonical_target("NGC1432") is None  # not the whole Pleiades
    for target in TARGETS:
        assert target.extent_source in SOURCES
        assert set(target.supporting_sources) <= SOURCES.keys()
        assert target.scope


def test_catalogue_is_read_only_and_does_not_claim_all_references_have_mission_routes():
    profile = {"projects": {"Heart": {"hours": 7, "target_hours": 15}}, "sessions": [{"id": "real"}]}
    before = deepcopy(profile)
    result = equipment_catalogue(profile=profile, equipment_id="samyang_183")
    assert profile == before
    assert all(not item["confirmed_filters"] for item in result["targets"])
    by_key = {item["key"]: item for item in result["targets"]}
    assert by_key["Ou4"]["project_routes"] == [{"imaging_field_id": "sh2-129_ou4", "acquisition_intent_id": "ou4_oiii"}]
    assert not by_key["IC1805"]["project_supported"]
    assert not {"mission", "decision_id", "target_hours"} & result.keys()


def test_custom_geometry_is_used_and_response_edits_do_not_mutate_the_source_catalogue():
    custom = {**EQUIPMENT_PROFILES["samyang_183"], "focal_length_mm": 270}
    profile = {"equipment_definitions": {"my_setup": custom}}
    result = equipment_catalogue(profile=profile, equipment_id="my_setup")
    assert result["geometry"]["field_width_deg"] < 3
    result["sources"]["baader"]["title"] = "changed"
    again = equipment_catalogue(profile=profile, equipment_id="samyang_183")
    assert again["sources"]["baader"]["title"] != "changed"
    assert not any(item["confirmed_filters"] for item in again["targets"])


def test_catalogue_api_requires_resolved_equipment_and_does_not_need_weather_or_write(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    def no_weather(*args):
        pytest.fail("Reference catalogue must not fetch weather")
    client = TestClient(create_app(profile_provider=lambda: {}, weather_provider=no_weather))
    assert client.get("/v1/target-catalogue").status_code == 422
    assert client.get("/v1/target-catalogue?equipment=unknown").status_code == 422
    response = client.get("/v1/target-catalogue?equipment=samyang_183")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert len(response.json()["targets"]) == 20
    assert not list(tmp_path.rglob("*.json"))


def test_unreadable_profile_does_not_get_an_invented_equipment_default():
    client = TestClient(create_app(profile_provider=lambda: None))
    assert client.get("/v1/target-catalogue?equipment=samyang_183").status_code == 503
