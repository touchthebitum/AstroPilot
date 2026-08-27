from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from decision.night_productivity.night_window_builder import NightWindowBuilder
from decision.night_productivity.night_window_merger import NightWindowMerger


def _slice(start, end, productivity, **overrides):
    values = {
        "start_hour": start,
        "end_hour": end,
        "productivity_score": productivity,
        "target_altitude": 48.126,
        "cloud_cover": 17.26,
        "moon_penalty": 0.136,
        "seeing": 2.345,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _timeline(*slices):
    return SimpleNamespace(slices=list(slices))


def test_builder_maps_each_slice_in_order_with_stable_rounding():
    timeline = _timeline(
        _slice(0.0, 0.25, 0.70),
        _slice(0.25, 0.5, 0.699),
    )

    windows = NightWindowBuilder.build(object(), timeline)

    assert [window.start_hour for window in windows] == [0.0, 0.25]
    assert [window.end_hour for window in windows] == [0.25, 0.5]
    assert windows[0].altitude == 48.13
    assert windows[0].cloud_cover == 17.3
    assert windows[0].moon_penalty == 0.14
    assert windows[0].seeing == 2.345


def test_builder_treats_the_productivity_threshold_as_inclusive():
    windows = NightWindowBuilder.build(
        None,
        _timeline(
            _slice(0.0, 0.25, 0.70),
            _slice(0.25, 0.5, 0.699),
        ),
    )

    assert windows[0].productive is True
    assert windows[0].reason == "Créneau exploitable"
    assert windows[1].productive is False
    assert windows[1].reason == "Créneau dégradé"


def test_builder_defaults_missing_moon_penalty_to_zero():
    night_slice = _slice(0.0, 0.25, 0.8)
    del night_slice.moon_penalty

    window = NightWindowBuilder.build(None, _timeline(night_slice))[0]

    assert window.moon_penalty == 0.0


def test_builder_returns_an_empty_list_for_an_empty_timeline():
    assert NightWindowBuilder.build(None, _timeline()) == []


def test_merger_groups_productive_sequences_and_splits_on_degraded_slices():
    timeline = _timeline(
        _slice(0.0, 0.25, 0.75),
        _slice(0.25, 0.5, 0.85),
        _slice(0.5, 0.75, 0.69),
        _slice(0.75, 1.0, 0.70),
    )

    windows = NightWindowMerger.merge(timeline)

    assert [(window.start_hour, window.end_hour) for window in windows] == [
        (0.0, 0.5),
        (0.75, 1.0),
    ]
    assert all(window.productive for window in windows)
    assert all(
        window.reason == "Fenêtre productive fusionnée"
        for window in windows
    )


def test_merger_uses_the_requested_threshold_inclusively():
    timeline = _timeline(
        _slice(0.0, 0.25, 0.8),
        _slice(0.25, 0.5, 0.79),
    )

    windows = NightWindowMerger.merge(timeline, threshold=0.8)

    assert len(windows) == 1
    assert windows[0].start_hour == 0.0
    assert windows[0].end_hour == 0.25


def test_merger_averages_and_rounds_all_window_metrics():
    timeline = _timeline(
        _slice(
            1.0,
            1.25,
            0.7111,
            target_altitude=40.111,
            cloud_cover=10.04,
            moon_penalty=0.111,
            seeing=1.111,
        ),
        _slice(
            1.25,
            1.5,
            0.8222,
            target_altitude=50.222,
            cloud_cover=20.16,
            moon_penalty=0.222,
            seeing=2.222,
        ),
    )

    window = NightWindowMerger.merge(timeline)[0]

    assert window.productivity == 0.767
    assert window.altitude == 45.17
    assert window.cloud_cover == 15.1
    assert window.moon_penalty == 0.17
    assert window.seeing == 1.67


def test_window_building_and_merging_do_not_mutate_source_slices():
    slices = [
        _slice(0.0, 0.25, 0.75),
        _slice(0.25, 0.5, 0.85),
    ]
    originals = [vars(night_slice).copy() for night_slice in slices]
    timeline = _timeline(*slices)

    built = NightWindowBuilder.build(None, timeline)
    merged = NightWindowMerger.merge(timeline)

    assert [vars(night_slice) for night_slice in slices] == originals
    with pytest.raises(FrozenInstanceError):
        built[0].productive = False
    with pytest.raises(FrozenInstanceError):
        merged[0].productive = False
