import pytest

from astro_score import (
    parse_filter_target_assignments,
)
from types import SimpleNamespace

import astro_score

def test_filter_target_cli_parses_assignments():
    result = parse_filter_target_assignments(
        [
            "Ha=6",
            "OIII=5",
            "SII=4",
        ]
    )

    assert result == {
        "Ha": 6.0,
        "OIII": 5.0,
        "SII": 4.0,
    }


def test_filter_target_cli_accepts_decimal_hours():
    result = parse_filter_target_assignments(
        [
            "Ha=5.5",
        ]
    )

    assert result == {
        "Ha": 5.5,
    }


def test_filter_target_cli_rejects_missing_equals():
    with pytest.raises(
        ValueError,
        match="Invalid filter target",
    ):
        parse_filter_target_assignments(
            ["Ha"]
        )


def test_filter_target_cli_rejects_invalid_hours():
    with pytest.raises(
        ValueError,
        match="Invalid filter hours",
    ):
        parse_filter_target_assignments(
            ["Ha=abc"]
        )

def test_filter_target_cli_show_returns_before_weather(
    monkeypatch,
    capsys,
):
    class FakeService:
        def __init__(self, **kwargs):
            pass

        def describe(self, *, project_name):
            assert project_name == "IC1396"

            return SimpleNamespace(
                project_name="IC1396",
                target_hours=15.0,
                filter_targets={
                    "Ha": 6.0,
                    "OIII": 5.0,
                    "SII": 4.0,
                },
                configured=True,
            )

    monkeypatch.setattr(
        astro_score,
        "FilterTargetConfigurationService",
        FakeService,
    )

    monkeypatch.setattr(
        astro_score,
        "get_active_equipment",
        lambda: "samyang_183",
    )

    monkeypatch.setattr(
        astro_score,
        "load_user_profile",
        lambda: {},
    )

    monkeypatch.setattr(
        astro_score,
        "fetch_weather",
        lambda *args, **kwargs: pytest.fail(
            "weather must not be called"
        ),
    )

    result = astro_score.main(
        [
            "--filter-targets-show",
            "IC1396",
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "Projet : IC1396" in output
    assert "Cible totale : 15.0 h" in output
    assert "Ha: 6.0 h" in output


def test_filter_target_cli_set_returns_before_weather(
    monkeypatch,
    capsys,
):
    captured = {}

    class FakeService:
        def __init__(self, **kwargs):
            pass

        def configure(
            self,
            *,
            project_name,
            filter_targets,
        ):
            captured["project_name"] = project_name
            captured["filter_targets"] = filter_targets

            return SimpleNamespace(
                filter_targets=filter_targets,
            )

    monkeypatch.setattr(
        astro_score,
        "FilterTargetConfigurationService",
        FakeService,
    )

    monkeypatch.setattr(
        astro_score,
        "get_active_equipment",
        lambda: "samyang_183",
    )

    monkeypatch.setattr(
        astro_score,
        "load_user_profile",
        lambda: {},
    )

    monkeypatch.setattr(
        astro_score,
        "fetch_weather",
        lambda *args, **kwargs: pytest.fail(
            "weather must not be called"
        ),
    )

    result = astro_score.main(
        [
            "--filter-targets-set",
            "IC1396",
            "Ha=6",
            "OIII=5",
            "SII=4",
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert captured == {
        "project_name": "IC1396",
        "filter_targets": {
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 4.0,
        },
    }
    assert (
        "Objectifs par filtre configurés pour IC1396"
        in output
    )


def test_filter_target_cli_clear_returns_before_weather(
    monkeypatch,
    capsys,
):
    captured = {}

    class FakeService:
        def __init__(self, **kwargs):
            pass

        def clear(
            self,
            *,
            project_name,
        ):
            captured["project_name"] = project_name

    monkeypatch.setattr(
        astro_score,
        "FilterTargetConfigurationService",
        FakeService,
    )

    monkeypatch.setattr(
        astro_score,
        "get_active_equipment",
        lambda: "samyang_183",
    )

    monkeypatch.setattr(
        astro_score,
        "load_user_profile",
        lambda: {},
    )

    monkeypatch.setattr(
        astro_score,
        "fetch_weather",
        lambda *args, **kwargs: pytest.fail(
            "weather must not be called"
        ),
    )

    result = astro_score.main(
        [
            "--filter-targets-clear",
            "IC1396",
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert captured["project_name"] == "IC1396"
    assert (
        "Objectifs par filtre supprimés pour IC1396"
        in output
    )
