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