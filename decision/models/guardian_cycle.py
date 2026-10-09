"""Immutable result of a caller-driven Guardian cycle; no execution authority."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from decision.models.guardian import GuardianAction, GuardianAssessment


class GuardianCycleStatus(Enum):
    ASSESSED = 'ASSESSED'
    ERROR = 'ERROR'


@dataclass(frozen=True)
class GuardianCycleResult:
    status: GuardianCycleStatus
    logical_time: datetime
    assessment: GuardianAssessment | None
    errors: tuple[str, ...] = ()
    version: str = 'guardian-periodic-v1'

    @property
    def decision_eligible(self) -> bool:
        return (self.status is GuardianCycleStatus.ASSESSED
                and self.assessment is not None and self.assessment.decision_eligible)

    @property
    def recommended_action(self) -> GuardianAction:
        if self.status is GuardianCycleStatus.ERROR or self.assessment is None:
            return GuardianAction.EMERGENCY_STOP
        return self.assessment.action
