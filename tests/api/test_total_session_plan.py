"""Total availability includes setup and flats; capture alone consumes capacity."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from astropilot.app import create_app
from decision.mission.night_planner import acquisition_availability, PREPARATION_TIME, FLATS_TIME
from decision.mission.mission_assembler import ProductiveWindowAssessment, _mission_timing_assessment
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode as Mode
from test_target_discovery import november_weather

START = datetime(2026, 11, 14, 2, tzinfo=timezone.utc)  # 03:00 Zurich


def test_setup_and_flat_reservations_match_persisted_task_offsets():
    from decision.mission.night_planner import NightPlanner
    tasks = NightPlanner.build(None)
    assert tasks[0].start == f'T-{int(PREPARATION_TIME.total_seconds()/60)} min'
    assert tasks[-1].end == f'Fin +{int(FLATS_TIME.total_seconds()/60)} min'


@pytest.mark.parametrize('duration', [30, 40, 90])
def test_short_total_availability_never_promotes_less_than_one_capture_hour(duration):
    assessment = ProductiveWindowAssessment(START, START+timedelta(hours=2), 2, 0,
        SimpleNamespace(windows=[SimpleNamespace(start_hour=0, end_hour=2, productivity=1, productive=True)]))
    window, refusal = _mission_timing_assessment(assessment, SessionAvailability(
        Mode.FIXED_WINDOW, start=START, end=START+timedelta(minutes=duration)))
    assert window is None
    assert refusal.required_continuous_minutes == 60


@pytest.mark.parametrize('mode', [Mode.FIXED_WINDOW, Mode.START_AND_DURATION, Mode.DURATION, Mode.UNTIL])
def test_reservation_is_elapsed_time_and_does_not_mutate_user_availability(mode):
    from zoneinfo import ZoneInfo
    start = datetime(2026, 10, 25, 1, 30, tzinfo=ZoneInfo('Europe/Zurich'))
    end = (start.astimezone(timezone.utc)+timedelta(hours=3)).astimezone(start.tzinfo)
    kwargs = {Mode.FIXED_WINDOW:dict(start=start,end=end), Mode.START_AND_DURATION:dict(start=start,duration=timedelta(hours=3)),
              Mode.DURATION:dict(duration=timedelta(hours=3)),Mode.UNTIL:dict(end=end)}[mode]
    original = SessionAvailability(mode, **kwargs)
    before = deepcopy(original)
    reserved = acquisition_availability(original)
    assert original == before
    if mode in (Mode.FIXED_WINDOW,Mode.START_AND_DURATION):
        assert reserved.start.astimezone(timezone.utc)-start.astimezone(timezone.utc)==timedelta(minutes=30)
        assert end.astimezone(timezone.utc)-reserved.end.astimezone(timezone.utc)==timedelta(minutes=10)
    elif mode is Mode.DURATION:
        assert reserved.duration == timedelta(hours=2,minutes=20)
    else:
        assert end.astimezone(timezone.utc)-reserved.end.astimezone(timezone.utc)==timedelta(minutes=10)


@pytest.mark.parametrize('kind', ['oiii','sii'])
@pytest.mark.parametrize('prep,flats,capture', [(30,10,80),(20,5,95),(45,15,60),(0,0,120),(50,20,None)])
def test_rosette_accepted_plan_reserves_custom_operations_inside_total(tmp_path,monkeypatch,kind,prep,flats,capture):
    import uuid
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path))
    ref = datetime(2026,11,10,18,tzinfo=timezone.utc)
    from astro_score import build_durable_tonight_application_service
    def factory():
        service = build_durable_tonight_application_service()
        service.clock = lambda: ref
        return service
    client = TestClient(create_app(service_factory=factory, weather_provider=lambda *args:november_weather(ref),clock=lambda:ref))
    project={'hours':0,'target_hours':3,'imaging_field_id':'rosette',
        'acquisition_intent_targets':[{'acquisition_intent_id':'rosette_'+kind,'target_hours':3}],
        'acquisition_intent_progress':[{'acquisition_intent_id':'rosette_'+kind,'acquired_duration_manual':0}]}
    response=client.put('/v1/configuration',json={'site':{'name':'FICTIF','latitude':46.888,'longitude':6.55,'bortle':4},
        'equipment':{'preset_id':'samyang_183'},'projects':{'Rosette':project}})
    assert response.status_code==200,response.text
    availability={'mode':'fixed_window','start':START.isoformat(),'end':(START+timedelta(hours=2)).isoformat()}
    if (prep,flats)!=(30,10): availability.update(preparation_minutes=prep,flats_minutes=flats)
    response=client.post('/v1/tonight',json={'availability':availability,'selected_project_id':'Rosette'})
    assert response.status_code==200,response.text
    decision=response.json()
    if capture is None:
        assert decision['status'] in {'no_mission','no_productive_window'},decision
        assert client.get('/v1/accepted-mission/current').json() is None
        return
    assert decision['status']=='available',decision
    response=client.post('/v1/decision-selections',json={'acceptance_request_id':str(uuid.uuid4()),
        'decision_id':decision['decision_id'],'source':'primary_recommendation','selected_catalog_key':'Rosette',
        'acquisition_intent_id':'rosette_'+kind,'selected_at':ref.isoformat()})
    assert response.status_code==200,response.text
    mission=response.json()['mission']
    assert datetime.fromisoformat(mission['window_start'])==START+timedelta(minutes=prep)
    assert datetime.fromisoformat(mission['window_end'])==START+timedelta(hours=2,minutes=-flats)
    assert mission['recommended_hours']==pytest.approx(capture/60)
    assert mission['expected_gain']==pytest.approx(round((capture/60)/3*100,2))
    assert mission['selected_filter']['filter_type']==kind.upper()
    assert client.get('/v1/configuration').json()['projects']['Rosette']['hours']==0


@pytest.mark.parametrize('bad', [-1,241,1.5,True,"20",None])
def test_operational_durations_fail_closed(tmp_path,monkeypatch,bad):
    from astropilot.app import SessionAvailabilityRequest
    with pytest.raises((ValueError,TypeError)):
        SessionAvailabilityRequest(mode="all_night",preparation_minutes=bad)
    with pytest.raises((ValueError,TypeError)):
        SessionAvailability(Mode.ALL_NIGHT,flats_minutes=bad)


def test_remaining_all_night_preserves_custom_operational_times():
    from decision.services.remaining_night_availability import remaining_night_availability
    from zoneinfo import ZoneInfo
    value=SessionAvailability(Mode.ALL_NIGHT,preparation_minutes=20,flats_minutes=5)
    result=remaining_night_availability(value,reference_time_utc=datetime(2026,11,10,18,tzinfo=timezone.utc),
        latitude=46.888,longitude=6.55,zone=ZoneInfo('Europe/Zurich'))
    assert (result.preparation_minutes,result.flats_minutes)==(20,5)
