"""Deterministic, idempotent recording of accepted learning signals."""

from decision.models.learning_application import (
    LearningApplication,
    LearningApplicationOutcome,
    LearningApplicationResult,
)
from decision.models.learning_signal import LearningSignal


def apply_learning_signal(
    application: LearningApplication,
    signal: LearningSignal,
    applications_by_signal_id: dict[str, LearningApplication],
) -> LearningApplicationResult:
    """Record one application per signal without changing its source."""

    if type(application) is not LearningApplication:
        raise TypeError("application_must_be_learning_application")
    if type(signal) is not LearningSignal:
        raise TypeError("signal_must_be_learning_signal")
    if type(applications_by_signal_id) is not dict:
        raise TypeError("applications_by_signal_id_must_be_dict")
    if application.signal_id != signal.signal_id:
        raise ValueError("signal_id_mismatch")

    for recorded_signal_id, recorded_application in applications_by_signal_id.items():
        if (
            not isinstance(recorded_signal_id, str)
            or type(recorded_application) is not LearningApplication
            or recorded_application.signal_id != recorded_signal_id
        ):
            raise ValueError("application_state_inconsistent")

    prior_application = applications_by_signal_id.get(signal.signal_id)
    if prior_application is not None:
        return LearningApplicationResult(
            application=prior_application,
            outcome=LearningApplicationOutcome.ALREADY_APPLIED,
        )

    applications_by_signal_id[signal.signal_id] = application
    return LearningApplicationResult(
        application=application,
        outcome=LearningApplicationOutcome.APPLIED,
    )
