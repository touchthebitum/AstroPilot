import astro_score
from decision.filtering.selected_filter import SelectedFilter


def test_ic1396_target_analysis_uses_semantic_filter_selection(
    monkeypatch,
    capsys,
):
    inventory = (
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
    )

    monkeypatch.setattr(
        astro_score,
        "best_equipment_for_object",
        lambda _target_name: None,
    )
    monkeypatch.setattr(
        astro_score.FilterInventoryLoader,
        "load",
        lambda: inventory,
    )

    astro_score.show_target_object_analysis("IC1396")

    output = capsys.readouterr().out

    assert "Filtres conseillés : Baader Ha 6.5nm Highspeed" in output
    assert "Filtres conseillés : aucun" not in output
