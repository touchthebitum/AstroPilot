"""One explicit logical cycle, with injected acquisition and no scheduling."""
from datetime import datetime
from typing import Callable
from decision.models.guardian import (
    GuardianAssessment, GuardianObservation, GuardianSessionContext,
)
from decision.models.guardian_cycle import GuardianCycleResult, GuardianCycleStatus
from decision.runners.guardian_runner import GuardianRunner


class GuardianPeriodicRunner:
    def __init__(self, *, evidence_provider: Callable[[datetime], GuardianObservation],
                 session_context_provider: Callable[[datetime], GuardianSessionContext | None],
                 guardian_runner: GuardianRunner):
        self._evidence_provider = evidence_provider
        self._session_context_provider = session_context_provider
        self._guardian_runner = guardian_runner

    def run_cycle(self, *, logical_time: datetime) -> GuardianCycleResult:
        if not isinstance(logical_time, datetime) or logical_time.utcoffset() is None:
            raise ValueError('logical_time must be timezone aware')
        errors = []
        observation = None
        context = None
        assessment = None
        try:
            observation = self._evidence_provider(logical_time)
            if not isinstance(observation, GuardianObservation):
                raise TypeError('Invalid observation')
        except Exception:
            observation = None
            errors.append('evidence_provider_error')
        try:
            context = self._session_context_provider(logical_time)
            if context is not None and not isinstance(context, GuardianSessionContext):
                raise TypeError('Invalid session context')
        except Exception:
            context = None
            errors.append('session_provider_error')
        if observation is not None:
            try:
                assessment = self._guardian_runner.evaluate(
                    observation, now=logical_time, session_context=context)
                if not isinstance(assessment, GuardianAssessment):
                    raise TypeError('Invalid assessment')
            except Exception:
                assessment = None
                errors.append('evaluation_error')
        return GuardianCycleResult(
            status=GuardianCycleStatus.ERROR if errors else GuardianCycleStatus.ASSESSED,
            logical_time=logical_time, assessment=assessment, errors=tuple(errors),
        )
