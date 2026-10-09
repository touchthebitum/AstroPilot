"""Immutable Guardian v1 inputs and recommendations; no execution authority."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
import math


class GuardianRiskLevel(IntEnum):
    SAFE = 0
    WATCH = 1
    WARNING = 2
    CRITICAL = 3
    UNKNOWN = 4


class GuardianAction(IntEnum):
    CONTINUE = 0
    MONITOR = 1
    PREPARE_STOP = 2
    STOP_SESSION = 3
    EMERGENCY_STOP = 4


class GuardianSessionState(Enum):
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'
    UNKNOWN = 'UNKNOWN'


class GuardianActionApplicability(Enum):
    APPLICABLE = 'APPLICABLE'
    NOT_APPLICABLE = 'NOT_APPLICABLE'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class GuardianSessionContext:
    session_active: bool
    observed_at: datetime
    session_id: str | None = None
    version: str = 'guardian-session-v1'


@dataclass(frozen=True)
class GuardianEvidence:
    value: bool | float | None
    source: str
    provenance: str
    timestamp: datetime


@dataclass(frozen=True)
class GuardianObservation:
    rain_active: GuardianEvidence | None = None
    rain_eta_minutes: GuardianEvidence | None = None
    wind_kmh: GuardianEvidence | None = None
    gust_kmh: GuardianEvidence | None = None
    humidity_percent: GuardianEvidence | None = None
    dew_spread_c: GuardianEvidence | None = None


@dataclass(frozen=True)
class GuardianPolicy:
    version: str = 'guardian-v1'
    max_age_seconds: float = 900
    rain_imminent_minutes: float = 15
    wind_watch: float = 15
    wind_warning: float = 25
    wind_critical: float = 35
    gust_watch: float = 20
    gust_warning: float = 30
    gust_critical: float = 40
    humidity_watch: float = 85
    humidity_warning: float = 90
    humidity_critical: float = 95
    dew_watch: float = 5
    dew_warning: float = 3
    dew_critical: float = 1

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError('Policy version is required')
        for name in self.__dataclass_fields__:
            if name == 'version':
                continue
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'Invalid threshold: {name}')
        for channel in ('wind', 'gust', 'humidity'):
            if not getattr(self, channel+'_watch') <= getattr(self, channel+'_warning') <= getattr(self, channel+'_critical'):
                raise ValueError('Thresholds must be ordered')
        if not self.dew_critical <= self.dew_warning <= self.dew_watch or self.humidity_critical > 100:
            raise ValueError('Invalid dew/humidity thresholds')


@dataclass(frozen=True)
class GuardianAssessment:
    risk_level: GuardianRiskLevel
    action: GuardianAction
    reasons: tuple[str, ...]
    evidence_complete: bool
    decision_eligible: bool
    policy: GuardianPolicy
    assessed_at: datetime
    source_evidence: tuple[tuple[str, GuardianEvidence | None], ...]
    session_active: bool | None
    session_context: GuardianSessionContext | None
    session_state: GuardianSessionState
    action_applicability: GuardianActionApplicability
    session_reasons: tuple[str, ...]
    hardware_action: None = None

    @property
    def operationally_applicable(self) -> bool:
        return self.action_applicability is GuardianActionApplicability.APPLICABLE
