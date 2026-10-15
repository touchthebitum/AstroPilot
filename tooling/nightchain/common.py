from pathlib import Path
import os,sys,json,hashlib
from datetime import datetime,timedelta,timezone
ROOT=Path(os.environ['PRODUCT_SOURCE']).resolve()
SHA='dad6e438b8ba0f5ce52d59457ce503e030911d80'
sys.path.insert(0,str(ROOT))
CASE=Path(os.environ['CASE_ROOT']).resolve()
assert (CASE/'QUALIFICATION_ONLY').is_file()
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','ASTROPILOT_DATA_DIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','MPLCONFIGDIR'):
 p=CASE/('data' if key=='ASTROPILOT_DATA_DIR' else key);p.mkdir(exist_ok=True);os.environ[key]=str(p)
from fastapi.testclient import TestClient
from astropilot.app import create_app
import astro_score
from decision.weather.weather_ingress import REQUIRED_HOURLY_UNITS,validate_weather_payload
REF=datetime.fromisoformat(os.environ.get('QUALIFICATION_CLOCK','2026-10-14T12:00:00+00:00'))
MODE=os.environ.get('WEATHER_MODE','clear')

def snapshot():
 start=REF.replace(hour=0,minute=0,second=0,microsecond=0);n=192
 payload={'latitude':46.888,'longitude':6.55,'elevation':837.,'timezone':'Europe/Zurich','utc_offset_seconds':7200,'hourly_units':{'time':'unixtime',**REQUIRED_HOURLY_UNITS},'hourly':{'time':[int((start+timedelta(hours=i)).timestamp()) for i in range(n)],'cloud_cover':[100. if MODE=='cloudy' else 0.]*n,'cloud_cover_low':[100. if MODE=='cloudy' else 0.]*n,'cloud_cover_mid':[0.]*n,'cloud_cover_high':[0.]*n,'precipitation':[0.]*n,'relative_humidity_2m':[40.]*n,'visibility':[40000.]*n,'wind_speed_10m':[3.]*n,'temperature_2m':[10.]*n}}
 (CASE/'weather-fixture.json').write_text(json.dumps(payload))
 return validate_weather_payload(payload,requested_latitude=46.888,requested_longitude=6.55,requested_timezone='Europe/Zurich',retrieved_at_utc=REF-timedelta(minutes=5))
WEATHER=snapshot()
def provider(*args):
 if MODE=='unavailable':return None  # Production fetch boundary represents unavailable weather as None.
 return WEATHER

def factory():
 service=astro_score.build_durable_tonight_application_service()
 service.clock=lambda:REF
 return service

def app():return create_app(service_factory=factory,weather_provider=provider,clock=lambda:REF,guardian_renewal_enabled=False)
def profile_hash():return hashlib.sha256((CASE/'data/user_profile.json').read_bytes()).hexdigest()
def seed(equipment='samyang_183'):
 with TestClient(app()) as c:
  r=c.put('/v1/configuration',json={'expected_revision':0,'site':{'name':'PUBLIC QUALIFICATION ONLY','latitude':46.888,'longitude':6.55,'bortle':4},'equipment':{'preset_id':equipment},'projects':{'Sh2-129':{'hours':0,'target_hours':20,'importance':9}}});assert r.status_code==200,r.json()
  r=c.put('/v1/projects/Sh2-129/progress',json={'expected_revision':r.json()['profile_revision'],'imaging_field_id':'sh2-129_ou4','acquisition_intent_progress':[{'acquisition_intent_id':x,'acquired_duration_manual':0} for x in ('sh2-129_ha','ou4_oiii')],'acquisition_intent_targets':[{'acquisition_intent_id':x,'target_hours':6} for x in ('sh2-129_ha','ou4_oiii')]});assert r.status_code==200,r.json()
 assert not (CASE/'data/user_filters.json').exists()

def mission_count():return len(list((CASE/'data/decision_lineage').glob('mission*/*.json'))) # supplemented by API list

def selection(body,intent,key):return {'acceptance_request_id':key,'decision_id':body['decision_id'],'source':'primary_recommendation','selected_catalog_key':body['catalog_key'],'acquisition_intent_id':intent,'selected_at':REF.isoformat()}
