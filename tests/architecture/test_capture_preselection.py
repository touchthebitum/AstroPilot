"""Reserve session tasks before selecting among candidate sky windows."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from copy import deepcopy
import pytest
import astro_score
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode as Mode
from decision.night_productivity.night_conditions_provider import NightConditionsProvider
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.mission.night_planner import acquisition_availability
from decision.services.session_availability_windowing import evaluate_physical_productive_window

ZONE=ZoneInfo('Europe/Zurich')
def stamp(hour,minute=0):return datetime(2026,11,13,hour,minute,tzinfo=ZONE)
def candidate(start,end,score):
    count=int((end-start).total_seconds()//3600)+1
    return {'start':start,'end':end,'score':score,'clouds':0,'humidity':50,'wind':3,
        'seeing':1.5,'visibility':40000,'moon_penalty':0,'moon_impact':'low','moon_sep':180,
        'target_altitude':70,'sqm':21,'details':[{'moon':0} for _ in range(count)],
        'hourly_lunar_evidence':[{'time':start+timedelta(hours=i),'moon':0} for i in range(count)]}
class Sky:
    def __init__(self,windows):self.windows=windows
    def best_windows(self,**kwargs):assert kwargs['limit'] is None;return self.windows
    def estimate_seeing(self,*args):return 1.5

def evaluate(monkeypatch,tmp_path,windows,availability):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(NightConditionsProvider,'altitude',lambda hour,context:70)
    hours={}
    for window in windows:
        t=window['start']
        while t<window['end']:
            hours[t]={'time':t,'cloud_cover':0,'relative_humidity_2m':50,'wind_speed_10m':3,
                'temperature_2m':10,'visibility':40000};t+=timedelta(minutes=15)
    for window in windows:
        window['hourly_lunar_evidence']=[{'time':h['time'],'moon':0} for h in hours.values() if window['start']<=h['time']<window['end']]
    profile={'active_equipment':'samyang_183','available_equipment':['samyang_183'],
        'preferences':{'bortle':4},'projects':{'IC1805':{'hours':0,'target_hours':3,
        'imaging_field_id':'sh2-190','acquisition_intent_targets':[{'acquisition_intent_id':'sh2-190_ha','target_hours':3}],
        'acquisition_intent_progress':[{'acquisition_intent_id':'sh2-190_ha','acquired_duration_manual':0}]}}}
    before=deepcopy(profile)
    result=astro_score.evaluate_object('IC1805',Sky(windows),list(hours.values()),0,
        SimpleNamespace(name='FICTITIOUS',observer=object()),46.88812,6.55137,4,'deep_sky',profile,availability=availability)
    assert profile==before and result is not None
    assessment=ProductiveWindowAssessment.build(target='IC1805',context=result['decision_context'],
        mission_input=astro_score.build_mission_input(result,profile=profile,for_intent_selection=True))
    return result,evaluate_physical_productive_window(assessment,acquisition_availability(availability))

@pytest.mark.parametrize('mode',[Mode.FIXED_WINDOW,Mode.START_AND_DURATION])
def test_later_candidate_covers_sixty_five_minutes_after_tasks(monkeypatch,tmp_path,mode):
    params={'start':stamp(22),'preparation_minutes':20,'flats_minutes':5}
    params.update({'end':stamp(23,30)} if mode is Mode.FIXED_WINDOW else {'duration':timedelta(minutes=90)})
    result,selected=evaluate(monkeypatch,tmp_path,[candidate(stamp(21),stamp(23),99),candidate(stamp(22),stamp(23)+timedelta(hours=1),98)],SessionAvailability(mode,**params))
    assert result['window']['start']==stamp(22)
    assert selected.window is not None
    assert selected.window.window_start==stamp(22,20) and selected.window.window_end==stamp(23,25)

def test_long_evening_does_not_stop_at_candidate_that_loses_preparation(monkeypatch,tmp_path):
    availability=SessionAvailability(Mode.FIXED_WINDOW,start=stamp(20),end=stamp(23),preparation_minutes=20,flats_minutes=5)
    result,selected=evaluate(monkeypatch,tmp_path,[candidate(stamp(19),stamp(21),99),candidate(stamp(20),stamp(22),98)],availability)
    assert result['window']['start']==stamp(20)
    assert selected.window is not None and (selected.window.window_end-selected.window.window_start).total_seconds()==100*60

def test_short_window_still_refuses_thirty_five_minutes(monkeypatch,tmp_path):
    availability=SessionAvailability(Mode.FIXED_WINDOW,start=stamp(22),end=stamp(23),preparation_minutes=20,flats_minutes=5)
    _,selected=evaluate(monkeypatch,tmp_path,[candidate(stamp(21),stamp(23),99),candidate(stamp(22),stamp(23)+timedelta(hours=1),98)],availability)
    assert selected.window is None and selected.refusal.best_productive_window_minutes==35
    assert selected.refusal.required_continuous_minutes==60

def test_until_reserves_flats_before_candidate_selection(monkeypatch,tmp_path):
    availability=SessionAvailability(Mode.UNTIL,end=stamp(23,30),preparation_minutes=20,flats_minutes=5)
    result,selected=evaluate(monkeypatch,tmp_path,[candidate(stamp(22,30),stamp(23,30),99),candidate(stamp(21,30),stamp(23,30),98)],availability)
    assert result['window']['start']==stamp(21,30)
    assert selected.window is not None and selected.window.window_end==stamp(23,25)

def test_duration_can_find_unique_window_after_reserving_tasks(monkeypatch,tmp_path):
    availability=SessionAvailability(Mode.DURATION,duration=timedelta(minutes=90),preparation_minutes=20,flats_minutes=5)
    result,selected=evaluate(monkeypatch,tmp_path,[candidate(stamp(21),stamp(22,30),99),candidate(stamp(22),stamp(23,5),98)],availability)
    assert result['window']['start']==stamp(22)
    assert selected.window is not None and (selected.window.window_end-selected.window.window_start).total_seconds()==65*60
