from dataclasses import replace
from datetime import datetime, timezone, timedelta
import pytest
from decision.models.guardian import GuardianObservation, GuardianEvidence, GuardianPolicy, GuardianRiskLevel as R, GuardianAction as A
from decision.services.guardian_service import assess_guardian

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)
def obs(**changes):
    values = dict(rain_active=False, rain_eta_minutes=None, wind_kmh=0., gust_kmh=0., humidity_percent=40., dew_spread_c=10.)
    values.update(changes)
    return GuardianObservation(**{k: GuardianEvidence(v, 'provider', 'OBSERVATION', NOW) for k,v in values.items()})
def assess(o, **kw):
    return assess_guardian(o, now=NOW, session_active=True, **kw)

@pytest.mark.parametrize('changes', [dict(rain_active=True), dict(rain_eta_minutes=15), dict(wind_kmh=35), dict(gust_kmh=40)])
def test_critical(changes):
    a=assess(obs(**changes)); assert (a.risk_level,a.action)==(R.CRITICAL,A.STOP_SESSION)
@pytest.mark.parametrize('spread,level', [(5,R.WATCH),(3,R.WARNING),(1,R.CRITICAL)])
def test_dew(spread,level): assert assess(obs(dew_spread_c=spread)).risk_level==level
@pytest.mark.parametrize('channel', list(obs().__dataclass_fields__))
@pytest.mark.parametrize('rain', [False,True])
def test_removal_never_improves(channel,rain):
    o=obs(rain_active=rain); a=assess(o); b=assess(replace(o,**{channel:None}))
    assert b.risk_level==R.UNKNOWN and b.action>=a.action and b.risk_level>=a.risk_level
@pytest.mark.parametrize('change',[dict(timestamp=NOW-timedelta(seconds=901)),dict(timestamp=NOW+timedelta(seconds=1)),dict(provenance='LEGACY'),dict(source=''),dict(value=float('nan'))])
def test_untrusted(change):
    o=obs(); a=assess(replace(o,wind_kmh=replace(o.wind_kmh,**change)))
    assert a.risk_level==R.UNKNOWN and not a.evidence_complete and not a.decision_eligible

def test_stricter_and_combined_and_deterministic():
    o=obs(wind_kmh=24)
    assert assess(o,policy=GuardianPolicy(wind_watch=10,wind_warning=20,wind_critical=30)).action>=assess(o).action
    assert assess(obs(rain_active=True,wind_kmh=40)).action>=assess(obs(rain_active=True)).action
    assert assess(o)==assess(o)
def test_inactive_and_safe():
    a=assess_guardian(obs(),now=NOW,session_active=False)
    assert a.risk_level==R.SAFE and a.hardware_action is None and not a.session_active

def test_policy_validation():
    with pytest.raises(ValueError): GuardianPolicy(wind_warning=50)

@pytest.mark.parametrize('channel,value', [('wind_kmh',-1),('gust_kmh',True),('humidity_percent',101),('rain_active',1),('rain_eta_minutes',-1)])
def test_invalid_values_fail_closed(channel,value):
    assert assess(obs(**{channel:value})).risk_level==R.UNKNOWN

def test_exact_freshness_and_naive_time():
    o=obs()
    assert assess(replace(o,wind_kmh=replace(o.wind_kmh,timestamp=NOW-timedelta(seconds=900)))).evidence_complete
    assert assess(replace(o,wind_kmh=replace(o.wind_kmh,timestamp=NOW.replace(tzinfo=None)))).risk_level==R.UNKNOWN
    with pytest.raises(ValueError): assess_guardian(o,now=NOW.replace(tzinfo=None),session_active=True)

def test_critical_reason_survives_missing_evidence():
    a=assess(replace(obs(rain_active=True),gust_kmh=None))
    assert 'rain_active:CRITICAL' in a.reasons
    assert a.source_evidence[0][1].timestamp==NOW
    assert a.policy.version=='guardian-v1'

@pytest.mark.parametrize('channel,prefix,values', [('wind_kmh','wind',[0,15,25,35,50]),('gust_kmh','gust',[0,20,30,40,50]),('humidity_percent','humidity',[40,85,90,95,100]),('dew_spread_c','dew',[-1,1,3,5,10])])
def test_tightened_thresholds_monotonic(channel,prefix,values):
    p=GuardianPolicy()
    factor=1.1 if prefix=='dew' else .9
    strict=replace(p,**{prefix+'_'+s:getattr(p,prefix+'_'+s)*factor for s in ('watch','warning','critical')})
    for value in values:
        assert assess(obs(**{channel:value}),policy=strict).action>=assess(obs(**{channel:value}),policy=p).action

@pytest.mark.parametrize('channel',list(obs().__dataclass_fields__))
def test_stale_channel_never_safe(channel):
    o=obs()
    assert assess(replace(o,**{channel:replace(getattr(o,channel),timestamp=NOW-timedelta(seconds=901))})).risk_level==R.UNKNOWN

@pytest.mark.parametrize('provenance',['LEGACY','UNKNOWN',''])
def test_provenance_never_authorizes_safe(provenance):
    o=obs()
    assert assess(replace(o,rain_active=replace(o.rain_active,provenance=provenance))).risk_level==R.UNKNOWN

def test_inactive_critical_remains_diagnostic():
    a=assess_guardian(obs(rain_active=True),now=NOW,session_active=False)
    assert a.risk_level==R.CRITICAL and a.action==A.STOP_SESSION
    assert a.hardware_action is None and not a.session_active

def test_stricter_rain_and_freshness():
    o=obs(rain_eta_minutes=20)
    assert assess(o,policy=GuardianPolicy(rain_imminent_minutes=30)).action>=assess(o).action
    o=obs()
    o=replace(o,wind_kmh=replace(o.wind_kmh,timestamp=NOW-timedelta(seconds=300)))
    assert assess(o,policy=GuardianPolicy(max_age_seconds=60)).action>=assess(o).action

def test_rain_eta_counts_down_from_source_timestamp():
    o=obs(rain_eta_minutes=20)
    o=replace(o,rain_eta_minutes=replace(o.rain_eta_minutes,timestamp=NOW-timedelta(minutes=10)))
    assert assess(o).risk_level==R.CRITICAL
