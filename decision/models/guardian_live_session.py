"""Versioned caller-attested acquisition heartbeat; no discovery or authority."""
from dataclasses import dataclass
from datetime import datetime
from decision.models.guardian import GuardianSessionState


@dataclass(frozen=True)
class GuardianLiveSessionEvidence:
    state: GuardianSessionState
    observed_at: datetime
    source: str
    provenance: str
    session_id: str | None = None
    version: str = 'guardian-live-session-v1'
