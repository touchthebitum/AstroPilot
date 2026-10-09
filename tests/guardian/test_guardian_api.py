from dataclasses import FrozenInstanceError
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from astropilot.app import create_app
from decision.runners.guardian_runner import GuardianRunner
from decision.models.guardian import GuardianObservation
from decision.services.guardian_service import assess_guardian

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)

def payload(active=True):
    values = dict(rain_active=False, rain_eta_minutes=None, wind_kmh=0,
                  gust_kmh=0, humidity_percent=40, dew_spread_c=10)
    return dict(observations={k: dict(value=v, source='injected', provenance='OBSERVATION', timestamp=NOW.isoformat()) for k,v in values.items()},
                session_context=dict(session_active=active, observed_at=NOW.isoformat()))

def client(**kwargs):
    forbidden = Mock(side_effect=AssertionError('unrelated service called'))
    return TestClient(create_app(clock=lambda: NOW, service_factory=forbidden,
        weather_provider=forbidden, profile_provider=forbidden,
        alert_ledger_factory=forbidden, **kwargs))

def evaluate(p):
    r=client().post('/v1/guardian/evaluate', json=p)
    assert r.status_code == 200, r.text
    return r.json()

def test_runner_once_and_immutable():
    service=Mock(wraps=assess_guardian)
    result=GuardianRunner(evaluator=service).evaluate(GuardianObservation(), now=NOW, session_context=None)
    assert service.call_count == 1
    with pytest.raises(FrozenInstanceError): result.decision_eligible=True

def test_rain_and_session_independence():
    p=payload(); p['observations']['rain_active']['value']=True
    a=evaluate(p); p['session_context']['session_active']=False; b=evaluate(p)
    assert (a['risk_level'], a['recommended_action']) == ('CRITICAL','STOP_SESSION')
    assert a['risk_level']==b['risk_level'] and a['recommended_action']==b['recommended_action']
    assert (a['action_applicability'],b['action_applicability'])==('APPLICABLE','NOT_APPLICABLE')

@pytest.mark.parametrize('channel', list(payload()['observations']))
def test_removal_never_improves(channel):
    p=payload(); p['observations']['rain_active']['value']=True
    p['observations'].pop(channel); r=evaluate(p)
    assert (r['risk_level'],r['recommended_action'])==('UNKNOWN','EMERGENCY_STOP')
    assert not r['decision_eligible'] and not r['evidence_complete']

@pytest.mark.parametrize('seconds', [-901,1])
def test_stale_future(seconds):
    p=payload(); p['observations']['wind_kmh']['timestamp']=(NOW+timedelta(seconds=seconds)).isoformat()
    assert evaluate(p)['risk_level']=='UNKNOWN'
    p=payload(); p['session_context']['observed_at']=(NOW+timedelta(seconds=seconds)).isoformat()
    r=evaluate(p); assert r['session_state']=='UNKNOWN' and r['risk_level']=='SAFE'

@pytest.mark.parametrize('value', ['bad','2026-10-09T00:00:00'])
def test_bad_timestamp(value):
    p=payload(); p['observations']['wind_kmh']['timestamp']=value
    r=client().post('/v1/guardian/evaluate',json=p)
    assert r.status_code==422 and r.json()=={'detail':{'code':'invalid_guardian_request'}}

@pytest.mark.parametrize('level', ['root','observation','evidence','session'])
def test_extra_forbidden(level):
    p=payload(); target={'root':p,'observation':p['observations'],'evidence':p['observations']['wind_kmh'],'session':p['session_context']}[level]
    target['policy']={}; assert client().post('/v1/guardian/evaluate',json=p).status_code==422

@pytest.mark.parametrize('value', [True,'12',None])
def test_numeric_strict(value):
    p=payload(); p['observations']['wind_kmh']['value']=value
    assert client().post('/v1/guardian/evaluate',json=p).status_code==422

def test_projection_utc_and_unknown_session():
    p=payload(); p['session_context']=None; r=evaluate(p)
    assert r['session_state']=='UNKNOWN' and r['action_applicability']=='UNKNOWN'
    assert r['assessed_at']=='2026-10-09T00:00:00Z'
    assert set(r)=={'schema_version','policy_version','risk_level','recommended_action','session_state','action_applicability','decision_eligible','evidence_complete','reasons','session_reasons','assessed_at'}
    assert r['session_reasons']==['session_context:missing']
    assert client().get('/v1/guardian/evaluate').status_code==405

def test_internal_error_sanitized():
    runner=Mock(); runner.evaluate.side_effect=RuntimeError('sensitive')
    r=client(guardian_runner=runner).post('/v1/guardian/evaluate',json=payload())
    assert r.status_code==500 and r.json()=={'detail':{'code':'guardian_evaluation_failed'}}

def test_reasons_allowlist_rejects_internal_codes():
    from dataclasses import replace
    from astropilot.guardian_api import REASONS
    p=payload(); p['observations']={}
    r=evaluate(p); assert set(r['reasons']) <= REASONS
    runner=Mock(); runner.evaluate.return_value=replace(assess_guardian(GuardianObservation(),now=NOW), reasons=('internal:sensitive',))
    response=client(guardian_runner=runner).post('/v1/guardian/evaluate',json=payload())
    assert response.status_code==500 and 'sensitive' not in response.text

def test_offset_timestamp_and_invalid_range():
    p=payload(); p['observations']['wind_kmh']['timestamp']='2026-10-09T02:00:00+02:00'
    assert evaluate(p)['risk_level']=='SAFE'
    p['observations']['humidity_percent']['value']=101
    assert evaluate(p)['risk_level']=='UNKNOWN'

def test_schema_disallows_clock_override():
    p=payload(); p['now']=NOW.isoformat()
    assert client().post('/v1/guardian/evaluate',json=p).status_code==422

@pytest.mark.parametrize('value', [0, True])
def test_epoch_timestamp_rejected(value):
    p=payload(); p['session_context']['observed_at']=value
    assert client().post('/v1/guardian/evaluate',json=p).status_code==422

def test_api_calls_runner_once():
    runner=Mock(wraps=GuardianRunner())
    r=client(guardian_runner=runner).post('/v1/guardian/evaluate',json=payload())
    assert r.status_code==200 and runner.evaluate.call_count==1

def test_server_policy_is_explicit_and_not_request_scoped():
    from decision.models.guardian import GuardianPolicy
    p=payload(); p['observations']['wind_kmh']['value']=12
    runner=GuardianRunner(policy=GuardianPolicy(wind_watch=10))
    r=client(guardian_runner=runner).post('/v1/guardian/evaluate',json=p)
    assert r.status_code==200 and r.json()['risk_level']=='WATCH'
    assert evaluate(p)['risk_level']=='SAFE'

def test_no_io_during_evaluation(monkeypatch):
    import builtins
    import socket
    c=client()
    p=payload()
    forbidden=Mock(side_effect=AssertionError('I/O during evaluation'))
    monkeypatch.setattr(builtins,'open',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    r=c.post('/v1/guardian/evaluate',json=p)
    assert r.status_code==200
    forbidden.assert_not_called()
