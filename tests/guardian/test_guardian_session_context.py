from dataclasses import replace
from datetime import timedelta
import pytest
from decision.models.guardian import (
    GuardianSessionContext, GuardianSessionState as S,
    GuardianActionApplicability as P, GuardianRiskLevel as R, GuardianAction as A,
)
from decision.services.guardian_service import assess_guardian
from test_guardian import NOW, obs


def evaluate(observation, context):
    return assess_guardian(observation, now=NOW, session_context=context)


def context(active, **kw):
    return GuardianSessionContext(session_active=active, observed_at=NOW, **kw)


@pytest.mark.parametrize('observation,level,action', [
    (obs(), R.SAFE, A.CONTINUE), (obs(wind_kmh=15), R.WATCH, A.MONITOR),
    (obs(wind_kmh=25), R.WARNING, A.PREPARE_STOP),
    (obs(rain_active=True), R.CRITICAL, A.STOP_SESSION),
    (replace(obs(rain_active=True), gust_kmh=None), R.UNKNOWN, A.EMERGENCY_STOP),
])
def test_session_changes_only_applicability(observation, level, action):
    active, inactive, missing = [evaluate(observation, c) for c in (context(True), context(False), None)]
    for result in (active, inactive, missing):
        assert (result.risk_level, result.action) == (level, action)
        assert result.reasons == active.reasons
        assert result.source_evidence == active.source_evidence
        assert result.evidence_complete == active.evidence_complete
        assert result.decision_eligible == active.decision_eligible
        assert result.hardware_action is None
    assert (active.session_state, active.action_applicability, active.operationally_applicable) == (S.ACTIVE, P.APPLICABLE, True)
    assert (inactive.session_state, inactive.action_applicability, inactive.operationally_applicable) == (S.INACTIVE, P.NOT_APPLICABLE, False)
    assert (missing.session_state, missing.action_applicability, missing.session_active, missing.operationally_applicable) == (S.UNKNOWN, P.UNKNOWN, None, False)


@pytest.mark.parametrize('changes', [dict(session_active=None), dict(session_active=1),
    dict(version='future'), dict(observed_at=NOW.replace(tzinfo=None)),
    dict(observed_at=NOW+timedelta(seconds=1)),
    dict(observed_at=NOW-timedelta(seconds=901)), dict(session_id=''), dict(session_id=42)])
def test_ambiguous_context_retains_decision(changes):
    c = replace(context(True), **changes)
    a = evaluate(obs(rain_active=True), c)
    assert (a.risk_level, a.action) == (R.CRITICAL, A.STOP_SESSION)
    assert a.session_state == S.UNKNOWN and a.action_applicability == P.UNKNOWN
    assert not a.operationally_applicable and a.session_context == c and a.session_reasons


def test_provenance_determinism_and_freshness_boundary():
    c = context(True, session_id='opaque-session')
    a = evaluate(obs(), c)
    assert a == evaluate(obs(), c) and a.session_context == c
    assert replace(a, session_context=context(True)) == evaluate(obs(), context(True))
    assert evaluate(obs(), replace(c, observed_at=NOW-timedelta(seconds=900))).session_state == S.ACTIVE


def test_absent_malformed_and_conflicting_interfaces():
    assert assess_guardian(obs(), now=NOW).session_state == S.UNKNOWN
    assert evaluate(obs(), object()).session_state == S.UNKNOWN
    for c in (None, context(True)):
        with pytest.raises(ValueError):
            assess_guardian(obs(), now=NOW, session_active=False, session_context=c)
    with pytest.raises(ValueError):
        assess_guardian(obs(), now=NOW, session_active=None)


def test_legacy_boolean_compatibility():
    for active in (True, False):
        assert assess_guardian(obs(), now=NOW, session_active=active) == evaluate(obs(), context(active))
