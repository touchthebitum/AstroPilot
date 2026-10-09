"""Contract-first tests: live assertions and rain uncertainty cannot imply safety."""
from dataclasses import replace
from datetime import timedelta
import pytest
from decision.models.guardian import GuardianSessionState as S, GuardianRiskLevel as R
from decision.models.guardian_live_session import GuardianLiveSessionEvidence
from decision.models.guardian_rain import GuardianRainUncertainty, GuardianRainInterval, GuardianRainEtaStatus as E
from decision.services.guardian_service import assess_guardian
from test_guardian import NOW, obs


def live(state=S.ACTIVE, **kw):
    return GuardianLiveSessionEvidence(state, NOW, 'caller_session_heartbeat_v1', 'CALLER_ASSERTED', **kw)


def rain(status=E.MISSING, value=None, **kw):
    return GuardianRainUncertainty(value, 'open_meteo_current_v1', 'FORECAST', NOW,
                                   eta_status=status, **kw)


def assess(o, c=None):
    return assess_guardian(o, now=NOW, session_context=c)


@pytest.mark.parametrize('state', list(S))
def test_fresh_explicit_session(state):
    a = assess(obs(), live(state, session_id='session-1'))
    assert a.session_state is state
    assert a.action_applicability.name == {S.ACTIVE:'APPLICABLE', S.INACTIVE:'NOT_APPLICABLE', S.UNKNOWN:'UNKNOWN'}[state]
    assert a.session_context == live(state, session_id='session-1')


@pytest.mark.parametrize('changes', [
    {'observed_at': NOW-timedelta(seconds=901)}, {'observed_at': NOW+timedelta(seconds=1)},
    {'observed_at': 'invalid'}, {'observed_at': NOW.replace(tzinfo=None)},
    {'source': 'guardian_host'}, {'source': 'tonight'}, {'source': []},
    {'provenance': 'FORECAST'}, {'version': 'v2'}, {'state': True}, {'session_id': ''},
])
def test_invalid_session_is_unknown(changes):
    assert assess(obs(), replace(live(), **changes)).session_state is S.UNKNOWN


def test_session_boundary_and_missing():
    assert assess(obs(), replace(live(), observed_at=NOW-timedelta(seconds=900))).session_state is S.ACTIVE
    assert assess(obs()).session_state is S.UNKNOWN


@pytest.mark.parametrize('o', [obs(), obs(rain_active=True), replace(obs(), rain_eta_minutes=None)])
def test_session_never_changes_environment(o):
    results = [assess(o, live(s)) for s in S] + [assess(o)]
    assert len({(a.risk_level,a.action,a.reasons,a.evidence_complete) for a in results}) == 1
    assert all(a.hardware_action is None for a in results)


def test_current_rain_and_missing_eta():
    assert assess(obs(rain_active=True)).risk_level is R.CRITICAL
    for active in (False, True):
        a = assess(replace(obs(rain_active=active), rain_eta_minutes=rain()))
        assert a.risk_level is R.UNKNOWN and not a.evidence_complete
        assert 'rain_eta_minutes:missing_invalid_untrusted_or_stale' in a.reasons
        assert a.source_evidence[1][1].eta_status is E.MISSING
        if active:
            assert 'rain_active:CRITICAL' in a.reasons


@pytest.mark.parametrize('mm,prob', [(None,100),(2,None),(0,0)])
def test_interval_probability_never_becomes_eta(mm,prob):
    sample = GuardianRainInterval(NOW, NOW+timedelta(hours=1), mm, prob)
    evidence = replace(rain(intervals=(sample,)), source='open_meteo_intervals_v1')
    a = assess(replace(obs(), rain_eta_minutes=evidence))
    assert evidence.value is None and a.risk_level is R.UNKNOWN
    assert assess(replace(obs(), rain_eta_minutes=None)).action >= a.action


def test_exact_onset_requires_capability():
    onset = replace(rain(E.ONSET_CAPABLE, 10), source='caller_onset_v1')
    assert assess(replace(obs(), rain_eta_minutes=onset)).risk_level is R.CRITICAL
    assert assess(replace(obs(), rain_eta_minutes=replace(onset,value=60))).risk_level is R.SAFE
    for evidence in (replace(onset,source='open_meteo_intervals_v1'),
                     replace(onset,value=None), replace(onset,eta_status=E.MISSING)):
        assert assess(replace(obs(), rain_eta_minutes=evidence)).risk_level is R.UNKNOWN


@pytest.mark.parametrize('changes', [
    {'timestamp':NOW+timedelta(seconds=1)}, {'timestamp':NOW-timedelta(seconds=901)},
    {'timestamp':'broken'}, {'timestamp':NOW.replace(tzinfo=None)},
    {'source':'unknown'}, {'source':[]}, {'provenance':'LEGACY'},
    {'version':'v2'}, {'eta_status':'ONSET_CAPABLE'}, {'intervals':None},
])
def test_invalid_rain_contract(changes):
    onset = replace(replace(rain(E.ONSET_CAPABLE,60),source='caller_onset_v1'), **changes)
    assert assess(replace(obs(),rain_eta_minutes=onset)).risk_level is R.UNKNOWN


@pytest.mark.parametrize('changes', [
    {'start':'bad'}, {'end':NOW}, {'rain_mm':True}, {'rain_mm':-1},
    {'probability_percent':101}, {'probability_percent':float('nan')},
    {'start':NOW.replace(tzinfo=None)}, {'rain_mm':None,'probability_percent':None},
])
def test_invalid_interval_fails_closed(changes):
    sample = replace(GuardianRainInterval(NOW,NOW+timedelta(hours=1),1,50),**changes)
    onset = replace(rain(E.ONSET_CAPABLE,60,intervals=(sample,)),source='caller_onset_v1')
    assert assess(replace(obs(),rain_eta_minutes=onset)).risk_level is R.UNKNOWN


def test_uncertainty_removal_never_improves():
    onset = replace(rain(E.ONSET_CAPABLE,60),source='caller_onset_v1')
    for evidence in (rain(), onset, replace(onset,value=10)):
        o = replace(obs(),rain_eta_minutes=evidence)
        assert assess(replace(o,rain_eta_minutes=None)).action >= assess(o).action


def test_interval_order_and_observation_freshness():
    sample = GuardianRainInterval(NOW+timedelta(minutes=30),NOW+timedelta(hours=1),1,50)
    onset = replace(rain(E.ONSET_CAPABLE,60,intervals=(sample,)),source='caller_onset_v1')
    assert assess(replace(obs(),rain_eta_minutes=onset)).risk_level is R.SAFE
    assert assess(replace(obs(),rain_eta_minutes=replace(onset,intervals=(sample,sample)))).risk_level is R.UNKNOWN


@pytest.mark.parametrize('state', list(S))
def test_periodic_runner_accepts_live_evidence(state):
    from decision.runners.guardian_periodic_runner import GuardianPeriodicRunner
    from decision.runners.guardian_runner import GuardianRunner
    runner = GuardianPeriodicRunner(evidence_provider=lambda _: obs(),
        session_context_provider=lambda _: live(state), guardian_runner=GuardianRunner())
    result = runner.run_cycle(logical_time=NOW)
    assert result.errors == ()
    assert result.assessment.session_state is state


@pytest.mark.parametrize('mm,prob', [(0,0),(100,100)])
def test_interval_signals_do_not_add_an_escalation_rule(mm,prob):
    sample = GuardianRainInterval(NOW,NOW+timedelta(hours=1),mm,prob)
    onset = replace(rain(E.ONSET_CAPABLE,60,intervals=(sample,)),source='caller_onset_v1')
    a = assess(replace(obs(),rain_eta_minutes=onset))
    assert a.risk_level is R.SAFE


def test_production_adapter_keeps_uncertainty_visible():
    from astropilot.guardian_live_evidence import ProductionGuardianWeatherAdapter
    from test_guardian_live_evidence import payload
    for active in (0,1):
        doc = payload(); doc['current']['rain'] = active
        o = ProductionGuardianWeatherAdapter(46,7,transport=lambda **_:doc)(NOW)
        assert isinstance(o.rain_eta_minutes,GuardianRainUncertainty)
        assert o.rain_eta_minutes.eta_status is E.MISSING
        assert o.rain_eta_minutes.source == 'open_meteo_current_v1'
        a = assess(o)
        assert a.risk_level is R.UNKNOWN
        assert assess(replace(o,rain_eta_minutes=None)).action >= a.action
        if active:
            assert 'rain_active:CRITICAL' in a.reasons
