from decision.portfolio.project_filter_progress import (
    ProjectFilterProgress,
)
import pytest


def test_filter_progress_aggregates_matching_sessions():
    sessions = [
        {
            "date": "2026-08-20",
            "object": "IC1396",
            "hours": 2.0,
            "filter_type": "Ha",
        },
        {
            "date": "2026-08-21",
            "object": "IC1396",
            "hours": 1.5,
            "filter_type": "Ha",
        },
        {
            "date": "2026-08-21",
            "object": "IC1396",
            "hours": 1.0,
            "filter_type": "OIII",
        },
    ]

    result = ProjectFilterProgress.evaluate(
        project_name="IC1396",
        filter_type="Ha",
        target_hours=6.0,
        sessions=sessions,
    )

    assert result.acquired_hours == 3.5
    assert result.target_hours == 6.0
    assert result.remaining_hours == 2.5
    assert result.progress == 58.3


def test_filter_progress_ignores_other_projects():
    sessions = [
        {
            "date": "2026-08-20",
            "object": "IC1396",
            "hours": 2.0,
            "filter_type": "Ha",
        },
        {
            "date": "2026-08-20",
            "object": "Sh2-129",
            "hours": 5.0,
            "filter_type": "Ha",
        },
    ]

    acquired = ProjectFilterProgress.acquired_hours(
        project_name="IC1396",
        filter_type="Ha",
        sessions=sessions,
    )

    assert acquired == 2.0


def test_legacy_sessions_without_filter_are_not_attributed():
    sessions = [
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 3.0,
        },
    ]

    acquired = ProjectFilterProgress.acquired_hours(
        project_name="M31",
        filter_type="LRGB",
        sessions=sessions,
    )

    assert acquired == 0.0


def test_filter_progress_caps_progress_at_one_hundred_percent():
    sessions = [
        {
            "date": "2026-08-20",
            "object": "IC1396",
            "hours": 7.0,
            "filter_type": "Ha",
        },
    ]

    result = ProjectFilterProgress.evaluate(
        project_name="IC1396",
        filter_type="Ha",
        target_hours=6.0,
        sessions=sessions,
    )

    assert result.acquired_hours == 7.0
    assert result.remaining_hours == 0.0
    assert result.progress == 100.0

def test_project_filter_progress_evaluates_all_configured_filters():
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
            "hours": 3.5,
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

    assert progress["Ha"].acquired_hours == 3.5
    assert progress["Ha"].remaining_hours == 2.5

    assert progress["OIII"].acquired_hours == 1.0
    assert progress["OIII"].remaining_hours == 4.0

    assert progress["SII"].acquired_hours == 0.0
    assert progress["SII"].remaining_hours == 4.0

def test_project_filter_progress_returns_empty_without_filter_targets():
    progress = ProjectFilterProgress.evaluate_project(
        project_name="M31",
        project={
            "target_hours": 20.0,
        },
        sessions=[],
    )

    assert progress == {}

def test_project_filter_progress_rejects_inconsistent_targets():
    project = {
        "target_hours": 15.0,
        "filter_targets": {
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 2.0,
        },
    }

    with pytest.raises(
        ValueError,
        match="must match target_hours",
    ):
        ProjectFilterProgress.evaluate_project(
            project_name="IC1396",
            project=project,
            sessions=[],
        )

def test_legacy_sessions_are_counted_as_unassigned_hours():
    sessions = [
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 1.0,
        },
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 2.0,
        },
        {
            "date": "2026-08-20",
            "object": "M31",
            "hours": 1.5,
            "filter_type": "LRGB",
        },
    ]

    unassigned = ProjectFilterProgress.unassigned_hours(
        project_name="M31",
        sessions=sessions,
    )

    assert unassigned == 3.0

def test_other_project_legacy_sessions_are_not_unassigned():
    sessions = [
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 3.0,
        },
        {
            "date": "2026-06-14",
            "object": "IC1396",
            "hours": 5.0,
        },
    ]

    unassigned = ProjectFilterProgress.unassigned_hours(
        project_name="M31",
        sessions=sessions,
    )

    assert unassigned == 3.0

def test_project_filter_progress_summary_matches_legacy_history():
    project = {
        "hours": 3.0,
        "target_hours": 20.0,
    }

    sessions = [
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 1.0,
        },
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 2.0,
        },
    ]

    summary = ProjectFilterProgress.summarize(
        project_name="M31",
        project=project,
        sessions=sessions,
    )

    assert summary.global_hours == 3.0
    assert summary.filtered_hours == 0.0
    assert summary.unassigned_hours == 3.0
    assert summary.accounted_hours == 3.0
    assert summary.difference == 0.0


def test_project_filter_progress_summary_detects_unexplained_hours():
    project = {
        "hours": 5.0,
        "target_hours": 20.0,
    }

    sessions = [
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 3.0,
        },
    ]

    summary = ProjectFilterProgress.summarize(
        project_name="M31",
        project=project,
        sessions=sessions,
    )

    assert summary.accounted_hours == 3.0
    assert summary.difference == 2.0

def test_single_filter_project_applies_legacy_hours_to_remaining_need():
    project = {
        "hours": 3.0,
        "target_hours": 20.0,
        "filter_targets": {
            "LRGB": 20.0,
        },
    }

    sessions = [
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 1.0,
        },
        {
            "date": "2026-06-14",
            "object": "M31",
            "hours": 2.0,
        },
    ]

    remaining = ProjectFilterProgress.effective_remaining_hours(
        project_name="M31",
        project=project,
        sessions=sessions,
    )

    assert remaining == {
        "LRGB": 17.0,
    }

def test_multi_filter_project_does_not_distribute_legacy_hours():
    project = {
        "hours": 3.0,
        "target_hours": 15.0,
        "filter_targets": {
            "Ha": 6.0,
            "OIII": 5.0,
            "SII": 4.0,
        },
    }

    sessions = [
        {
            "date": "2026-06-14",
            "object": "IC1396",
            "hours": 3.0,
        },
    ]

    remaining = ProjectFilterProgress.effective_remaining_hours(
        project_name="IC1396",
        project=project,
        sessions=sessions,
    )

    assert remaining == {
        "Ha": 6.0,
        "OIII": 5.0,
        "SII": 4.0,
    }
