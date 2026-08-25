from decision.filtering.filter_selection_context import (
    FilterSelectionContext,
)
from decision.filtering.filter_selection_engine import (
    FilterSelectionEngine,
)
from decision.filtering.selected_filter import SelectedFilter
from decision.filtering.target_semantics_resolver import (
    TargetSemanticsResolver,
)
from decision.portfolio.project_filter_progress import (
    ProjectFilterProgress,
)


def _inventory():
    return (
        SelectedFilter(
            name="Baader Ha 6.5nm Highspeed",
            filter_type="Ha",
            bandwidth_nm=6.5,
            source="inventory",
        ),
        SelectedFilter(
            name="Baader OIII 6.5nm Highspeed",
            filter_type="OIII",
            bandwidth_nm=6.5,
            source="inventory",
        ),
        SelectedFilter(
            name="Baader SII 6.5nm Highspeed",
            filter_type="SII",
            bandwidth_nm=6.5,
            source="inventory",
        ),
        SelectedFilter(
            name="LRGB 1.25",
            filter_type="LRGB",
            bandwidth_nm=None,
            source="inventory",
        ),
    )


def test_ic1396_semantics_select_ha():
    target_type, target_subtype = (
        TargetSemanticsResolver.resolve(
            target_name="IC1396",
            catalog_data={
                "type": "nebula",
            },
        )
    )

    selected = FilterSelectionEngine.select(
        FilterSelectionContext(
            target_name="IC1396",
            target_type=target_type,
            target_subtype=target_subtype,
            available_filters=_inventory(),
            moon_penalty=0.8,
        )
    )

    assert selected is not None
    assert selected.filter_type == "Ha"
    assert selected.name == "Baader Ha 6.5nm Highspeed"


def test_m31_semantics_select_lrgb():
    target_type, target_subtype = (
        TargetSemanticsResolver.resolve(
            target_name="M31",
            catalog_data={
                "type": "galaxy",
            },
        )
    )

    selected = FilterSelectionEngine.select(
        FilterSelectionContext(
            target_name="M31",
            target_type=target_type,
            target_subtype=target_subtype,
            available_filters=_inventory(),
            moon_penalty=0.2,
        )
    )

    assert selected is not None
    assert selected.filter_type == "LRGB"
    assert selected.name == "LRGB 1.25"

def test_filter_progress_and_moon_drive_ic1396_filter_selection():
    project = {
        "target_hours": 15.0,
        "filter_targets": {
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 4.0,
        },
    }

    sessions = [
        {
            "date": "2026-08-20",
            "object": "IC1396",
            "hours": 6.0,
            "filter_type": "Ha",
        },
        {
            "date": "2026-08-21",
            "object": "IC1396",
            "hours": 1.0,
            "filter_type": "OIII",
        },
    ]

    progress = ProjectFilterProgress.evaluate_project(
        project_name="IC1396",
        project=project,
        sessions=sessions,
    )

    remaining = {
        filter_type: value.remaining_hours
        for filter_type, value in progress.items()
    }

    target_type, target_subtype = (
        TargetSemanticsResolver.resolve(
            target_name="IC1396",
            catalog_data={
                "type": "nebula",
            },
        )
    )

    weak_moon = FilterSelectionEngine.select(
        FilterSelectionContext(
            target_name="IC1396",
            target_type=target_type,
            target_subtype=target_subtype,
            available_filters=_inventory(),
            moon_penalty=0.2,
            remaining_hours_by_filter=remaining,
        )
    )

    strong_moon = FilterSelectionEngine.select(
        FilterSelectionContext(
            target_name="IC1396",
            target_type=target_type,
            target_subtype=target_subtype,
            available_filters=_inventory(),
            moon_penalty=0.8,
            remaining_hours_by_filter=remaining,
        )
    )

    assert weak_moon is not None
    assert strong_moon is not None

    assert weak_moon.filter_type == "OIII"
    assert strong_moon.filter_type == "SII"