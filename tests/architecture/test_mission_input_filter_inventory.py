from datetime import timedelta

import pytest

import astro_score
from decision.definitions.production_setup_filter_capabilities import (
    build_production_setup_filter_capabilities_resolver,
)
from decision.filtering.selected_filter import SelectedFilter


def _intent_evaluation(frozen_time):
    return {
        "catalog_key": "Sh2-129",
        "imaging_field_id": "sh2-129_ou4",
        "selected_acquisition_intent_id": "sh2-129_ha",
        "window": {
            "start": frozen_time,
            "end": frozen_time + timedelta(hours=2),
            "moon_penalty": 0.2,
        },
        "remaining_hours": 2.0,
    }


def test_mission_input_allows_empty_filter_inventory(
    monkeypatch,
    frozen_time,
):
    monkeypatch.setattr(
        astro_score.FilterInventoryLoader,
        "load",
        lambda: (),
    )

    mission_input = astro_score.build_mission_input(
        {
            "catalog_key": "IC1396",
            "window": {
                "start": frozen_time,
                "end": frozen_time + timedelta(hours=2),
                "moon_penalty": 0.2,
            },
            "remaining_hours": 2.0,
        }
    )

    assert mission_input.selected_filter is None


OIII = SelectedFilter("OIII", "OIII")
HA = SelectedFilter("H-alpha", "Ha")


@pytest.mark.parametrize(
    ("inventory", "expected_filter"),
    [((), None), ((OIII,), None), ((OIII, HA), HA)],
    ids=["absent", "oiii-only", "mixed"],
)
def test_legacy_inventory_only_enriches_eligible_ha_intent(
    monkeypatch,
    frozen_time,
    inventory,
    expected_filter,
):
    monkeypatch.setattr(
        astro_score.FilterInventoryLoader,
        "load",
        lambda: inventory,
    )

    mission_input = astro_score.build_mission_input(
        _intent_evaluation(frozen_time),
        profile={"active_equipment": "samyang_183"},
    )

    capabilities = build_production_setup_filter_capabilities_resolver().resolve(
        "samyang_183"
    )
    assert "Ha" in capabilities.available_filter_types
    assert mission_input.selected_filter is expected_filter
    assert mission_input.imaging_field_id == "sh2-129_ou4"
    assert mission_input.acquisition_intent_id == "sh2-129_ha"
