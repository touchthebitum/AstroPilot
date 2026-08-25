from __future__ import annotations


class SessionRecordingService:
    def __init__(self, record_session):
        self.record_session = record_session

    def record(
        self,
        *,
        project_name: str,
        hours: float,
        date: str,
        filter_type: str | None = None,
    ) -> None:
        self.record_session(
            project_name,
            hours,
            date,
            filter_type=filter_type,
        )