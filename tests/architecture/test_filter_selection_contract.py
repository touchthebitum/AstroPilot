from decision.filtering.filter_selection_context import (
    FilterSelectionContext,
)
from decision.filtering.selected_filter import SelectedFilter


def test_filter_selection_context_preserves_inputs():
    ha = SelectedFilter(
        name="Baader Ha 6.5nm Highspeed",
        filter_type="Ha",
        bandwidth_nm=6.5,
        source="inventory",
    )

    oiii = SelectedFilter(
        name="Baader OIII 6.5nm Highspeed",
        filter_type="OIII",
        bandwidth_nm=6.5,
        source="inventory",
    )

    sii = SelectedFilter(
        name="Baader SII 6.5nm Highspeed",
        filter_type="SII",
        bandwidth_nm=6.5,
        source="inventory",
    )

    context = FilterSelectionContext(
        target_name="IC1396",
        target_type="nebula",
        target_subtype="emission",
        available_filters=(ha, oiii, sii),
        moon_penalty=0.8,
    )

    assert context.target_name == "IC1396"
    assert context.target_type == "nebula"
    assert context.target_subtype == "emission"

    assert context.available_filters == (
        ha,
        oiii,
        sii,
    )

    assert context.available_filters[0].filter_type == "Ha"
    assert context.available_filters[0].bandwidth_nm == 6.5
    assert context.moon_penalty == 0.8

def test_selected_filter_is_explicit_mission_state():
    selected = SelectedFilter(
        name="Baader Ha 6.5nm Highspeed",
        filter_type="Ha",
        bandwidth_nm=6.5,
    )

    assert selected.name == "Baader Ha 6.5nm Highspeed"
    assert selected.filter_type == "Ha"
    assert selected.bandwidth_nm == 6.5