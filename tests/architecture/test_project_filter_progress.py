from decision.portfolio.project_filter_progress import (
    ProjectFilterProgress,
)


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