from decision.filtering.filter_selection_context import (
    FilterSelectionContext,
)
from decision.filtering.filter_selection_engine import (
    FilterSelectionEngine,
)
from decision.filtering.selected_filter import SelectedFilter


def test_emission_nebula_prefers_ha():
    context = FilterSelectionContext(
        target_name="IC1396",
        target_type="nebula",
        target_subtype="emission",
        available_filters=(
            _filter("Ha", "Baader Ha 6.5nm", 6.5),
            _filter("OIII", "Baader OIII 6.5nm", 6.5),
            _filter("SII", "Baader SII 6.5nm", 6.5),
        ),
        moon_penalty=0.2,
    )

    result = FilterSelectionEngine.select(context)

    assert result is not None
    assert result.filter_type == "Ha"
    assert result.name == "Baader Ha 6.5nm"
    assert result.bandwidth_nm == 6.5


def test_galaxy_prefers_lrgb():
    context = FilterSelectionContext(
        target_name="M31",
        target_type="galaxy",
        target_subtype="spiral",
        available_filters=(
            _filter("Ha"),
            _filter("LRGB", "LRGB 1.25"),
        ),
        moon_penalty=0.1,
    )

    result = FilterSelectionEngine.select(context)

    assert result is not None
    assert result.filter_type == "LRGB"


def test_selection_never_returns_unavailable_filter():
    context = FilterSelectionContext(
        target_name="IC1396",
        target_type="nebula",
        target_subtype="emission",
        available_filters=(
            _filter("OIII", "Baader OIII 6.5nm", 6.5),
        ),
        moon_penalty=0.8,
    )

    result = FilterSelectionEngine.select(context)

    assert result is not None
    assert result.filter_type == "OIII"


def test_empty_filter_inventory_returns_none():
    context = FilterSelectionContext(
        target_name="M31",
        target_type="galaxy",
        target_subtype="spiral",
        available_filters=(),
        moon_penalty=0.0,
    )

    assert FilterSelectionEngine.select(context) is None

def _filter(
    filter_type,
    name=None,
    bandwidth_nm=None,
):
    return SelectedFilter(
        name=name or filter_type,
        filter_type=filter_type,
        bandwidth_nm=bandwidth_nm,
        source="inventory",
    )