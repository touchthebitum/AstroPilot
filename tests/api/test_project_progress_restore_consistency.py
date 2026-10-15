"""Restored profiles must not expose credits contradicted by persisted lineage."""
import json
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.execution_lineage_store import FileExecutionLineageStore
from astropilot.user_profile import load_user_profile, save_user_profile
from decision.services.durable_tonight_application_service import DurableTonightApplicationService
from test_execution_session_api import Acceptance, setup, create_completed, credit


def restored_api(directory):
    def service():
        return DurableTonightApplicationService(application_service=object(), evidence_store=object(),
            decision_id_factory=lambda:'unused',acceptance_service=Acceptance(),
            execution_lineage_store=FileExecutionLineageStore(directory/'execution_lineage'),
            profile_loader=load_user_profile,profile_saver=save_user_profile)
    return TestClient(create_app(service_factory=service))


@pytest.mark.parametrize('damage',['missing_execution','truncated_execution','missing_evidence','wrong_duration','wrong_intent'])
def test_restored_project_progress_refuses_invalid_credits_before_read_or_edit(tmp_path,monkeypatch,damage):
    original=tmp_path/'original'
    fresh=setup(original,monkeypatch)
    create_completed(fresh(),'execution-1',evidence_id='evidence-1')
    assert credit(fresh(),'execution-1','evidence-1',confirm=True).status_code==200
    source_profile=(original/'user_profile.json').read_bytes()
    restored=tmp_path/'restored';shutil.copytree(original,restored)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(restored))
    path=restored/'user_profile.json';execution=restored/'execution_lineage/execution-1.json'
    if damage=='missing_execution':execution.unlink()
    elif damage=='truncated_execution':execution.write_text('{')
    elif damage=='missing_evidence':
        document=json.loads(execution.read_text());document['evidence']=[];execution.write_text(json.dumps(document))
    else:
        profile=json.loads(path.read_text());entry=profile['intent_progress_credits']['execution-1']
        if damage=='wrong_duration':entry.update(usable_durations_us=[900_000_000],total_duration_us=900_000_000)
        else:entry['acquisition_intent_id']='ou4_oiii'
        path.write_text(json.dumps(profile))
    before=path.read_bytes();api=restored_api(restored)
    read=api.get('/v1/projects/Sh2-129/progress')
    assert read.status_code==503,read.text
    assert read.json()['detail']['code']=='project_credit_inconsistent'
    revision=json.loads(before)['profile_revision']
    edited=api.put('/v1/projects/Sh2-129/progress',json={'expected_revision':revision,
        'acquisition_intent_targets':[{'acquisition_intent_id':'sh2-129_ha','target_hours':3}]})
    assert edited.status_code==503 and edited.json()['detail']['code']=='project_credit_inconsistent'
    assert path.read_bytes()==before
    # Restore the exact authoritative files from the known-good snapshot.
    shutil.copyfile(original/'user_profile.json',path)
    shutil.copyfile(original/'execution_lineage/execution-1.json',execution)
    canonical=restored_api(restored).get('/v1/projects/Sh2-129/progress')
    assert canonical.status_code==200,canonical.text
    ha=next(x for x in canonical.json()['intent_progress_breakdown'] if x['acquisition_intent_id']=='sh2-129_ha')
    assert ha['effective_total_seconds']==5400
    saved=path.read_bytes()
    assert credit(restored_api(restored),'execution-1','evidence-1').json()['status']=='already_applied'
    assert path.read_bytes()==saved
    assert (original/'user_profile.json').read_bytes()==source_profile


def test_credits_in_other_project_do_not_block_uncredited_project(tmp_path,monkeypatch):
    fresh=setup(tmp_path,monkeypatch)
    create_completed(fresh(),'execution-1',evidence_id='evidence-1')
    assert credit(fresh(),'execution-1','evidence-1',confirm=True).status_code==200
    profile=load_user_profile();profile['projects']['M31']={'hours':0,'target_hours':4,'importance':5}
    save_user_profile(profile,expected_revision=profile['profile_revision'])
    (tmp_path/'execution_lineage/execution-1.json').unlink()
    response=fresh().get('/v1/projects/M31/progress')
    assert response.status_code==200,response.text
