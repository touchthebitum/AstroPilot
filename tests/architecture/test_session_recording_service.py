from decision.services.session_recording_service import (
    SessionRecordingService,
)


def test_session_recording_service_forwards_filter_type():
    captured = {}

    def record_session(
        project_name,
        hours,
        date,
        filter_type=None,
    ):
        captured["project_name"] = project_name
        captured["hours"] = hours
        captured["date"] = date
        captured["filter_type"] = filter_type

    service = SessionRecordingService(
        record_session=record_session,
    )

    service.record(
        project_name="IC1396",
        hours=2.5,
        date="2026-08-25",
        filter_type="Ha",
    )

    assert captured == {
        "project_name": "IC1396",
        "hours": 2.5,
        "date": "2026-08-25",
        "filter_type": "Ha",
    }


def test_session_recording_service_allows_legacy_session_without_filter():
    captured = {}

    def record_session(
        project_name,
        hours,
        date,
        filter_type=None,
    ):
        captured["filter_type"] = filter_type

    service = SessionRecordingService(
        record_session=record_session,
    )

    service.record(
        project_name="M31",
        hours=1.0,
        date="2026-08-25",
    )

    assert captured["filter_type"] is None