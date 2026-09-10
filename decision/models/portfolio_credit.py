"""Immutable proposed portfolio credit without portfolio or project mutation."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class PortfolioCredit:
    """Explicit usable integration credit linked to its supporting evidence."""

    credit_id: str
    execution_id: str
    evidence_ids: tuple[str, ...]
    usable_integration_duration: timedelta
    credited_at: datetime

    def __post_init__(self) -> None:
        for name in ("credit_id", "execution_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if not isinstance(self.evidence_ids, tuple):
            raise TypeError("evidence_ids_must_be_tuple")
        if not self.evidence_ids:
            raise ValueError("evidence_required")
        for evidence_id in self.evidence_ids:
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                raise ValueError("evidence_id_required")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("duplicate_evidence_id")
        if not isinstance(self.usable_integration_duration, timedelta):
            raise TypeError("usable_integration_duration_must_be_timedelta")
        if self.usable_integration_duration < timedelta(0):
            raise ValueError("usable_integration_duration_must_be_non_negative")
        if not isinstance(self.credited_at, datetime):
            raise TypeError("credited_at_must_be_datetime")
        if self.credited_at.tzinfo is None or self.credited_at.utcoffset() is None:
            raise ValueError("credited_at_timezone_required")
