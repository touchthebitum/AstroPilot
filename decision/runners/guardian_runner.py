"""Application boundary for a single, side-effect-free Guardian assessment."""
from datetime import datetime
from typing import Callable
from decision.models.guardian import (
    GuardianAssessment, GuardianObservation, GuardianPolicy, GuardianSessionContext,
)
from decision.models.guardian_live_session import GuardianLiveSessionEvidence
from decision.services.guardian_service import assess_guardian


class GuardianRunner:
    def __init__(self, *, policy: GuardianPolicy = GuardianPolicy(),
                 evaluator: Callable[..., GuardianAssessment] = assess_guardian):
        self._policy = policy
        self._evaluator = evaluator

    def evaluate(self, observation: GuardianObservation, *, now: datetime,
                 session_context: GuardianSessionContext | GuardianLiveSessionEvidence | None) -> GuardianAssessment:
        return self._evaluator(observation, now=now,
                               session_context=session_context, policy=self._policy)
