"""Typed rain uncertainty in the required ETA channel, never an inferred onset."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from decision.models.guardian import GuardianEvidence


class GuardianRainEtaStatus(Enum):
    MISSING = 'MISSING'
    ONSET_CAPABLE = 'ONSET_CAPABLE'


@dataclass(frozen=True)
class GuardianRainInterval:
    start: datetime
    end: datetime
    rain_mm: float | None = None
    probability_percent: float | None = None


@dataclass(frozen=True)
class GuardianRainUncertainty(GuardianEvidence):
    eta_status: GuardianRainEtaStatus = GuardianRainEtaStatus.MISSING
    intervals: tuple[GuardianRainInterval, ...] = ()
    version: str = 'guardian-rain-uncertainty-v1'
