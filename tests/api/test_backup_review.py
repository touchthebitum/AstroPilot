"""Read-only checks of selected ZIPs; real validators on fictitious profiles."""
import json,re
from urllib.parse import quote
from fastapi.testclient import TestClient
from astropilot.profile_backup import create_backup,inspect_backup_for_review,snapshot
from astropilot.profile_transfer_app import create_transfer_app
from test_profile_backup import source


def client(root):
    api=TestClient(create_transfer_app(directory=root,origin='http://testserver'))
    token=re.search(r'const token="([^"]+)"',api.get('/').text).group(1)
    return api,{'X-NightMerit-Transfer':token,'Origin':'http://testserver','X-NightMerit-File-Name':quote('Sauvegarde été Rosette.zip')}


def test_export_receipt_and_selected_file_check_are_distinct_and_read_only(source):
    api,h=client(source);before=snapshot(source)
    result=api.post('/transfer/export',headers=h);assert result.status_code==200
    receipt=api.get('/transfer/status').json()['backup_activity']
    assert receipt['last_check'] is None
    assert receipt['last_export']['filename'] in result.headers['Content-Disposition']
    assert receipt['last_export']['requested_at_utc']==result.headers['X-NightMerit-Export-Requested-At']
    checked=api.post('/transfer/check',content=result.content,headers=h);assert checked.status_code==200,checked.text
    info=checked.json();assert info['verified'] is True and info['matches_last_export'] is True
    assert info['filename']=='Sauvegarde été Rosette.zip' and info['summary']['created_at_utc']
    assert info['summary']['project_details'][0]['project_id']=='M42'
    assert 'confirmation' not in info and snapshot(source)==before
    assert api.get('/transfer/status').json()['backup_activity']['last_check']==info
    denied=api.post('/transfer/restore',json={'confirm':True,'confirmation':'never-created-by-check'},headers=h)
    assert denied.status_code==409 and snapshot(source)==before
    again=api.post('/transfer/check',content=result.content,headers=h)
    assert again.json()['summary']==info['summary'] and snapshot(source)==before


def test_other_valid_file_is_not_confused_with_last_download_and_failure_clears_check(source):
    api,h=client(source);first=api.post('/transfer/export',headers=h).content
    alternate,_=create_backup(source);assert first!=alternate
    checked=api.post('/transfer/check',content=alternate,headers=h)
    assert checked.status_code==200 and checked.json()['matches_last_export'] is False
    invalid=api.post('/transfer/check',content=alternate[:30],headers=h);assert invalid.status_code==409
    assert api.get('/transfer/status').json()['backup_activity']['last_check'] is None
    api.post('/transfer/check',content=first,headers=h)
    api.post('/transfer/export',headers=h)
    assert api.get('/transfer/status').json()['backup_activity']['last_check'] is None


def test_check_does_not_publish_profile_or_consume_restore_confirmation(source,tmp_path):
    raw,_=create_backup(source);destination=tmp_path/'empty';api,h=client(destination)
    preview=api.post('/transfer/preview',content=raw,headers=h);assert preview.status_code==200
    assert not destination.exists()
    checked=api.post('/transfer/check',content=raw,headers=h)
    assert checked.status_code==200 and checked.json()['matches_last_export'] is None
    assert not destination.exists() and api.get('/transfer/status').json()['can_restore']
    restored=api.post('/transfer/restore',json={'confirm':True,'confirmation':preview.json()['confirmation']},headers=h)
    assert restored.status_code==200 and snapshot(destination)==snapshot(source)
    before=snapshot(destination)
    repeated=api.post('/transfer/restore',json={'confirm':True,'confirmation':preview.json()['confirmation']},headers=h)
    assert repeated.status_code==409 and snapshot(destination)==before


def test_no_check_without_assistant_token(source):
    api,_=client(source);before=snapshot(source)
    assert api.post('/transfer/check',content=b'not a zip').status_code==403
    assert snapshot(source)==before


def test_default_backup_summary_contract_is_preserved_but_review_adds_details(source):
    raw,summary=create_backup(source)
    assert set(summary)=={'projects','sessions','observations','comparisons'}
    files,review=inspect_backup_for_review(raw)
    assert files==snapshot(source) and review['projects']==summary['projects']
    assert review['project_details'][0]['project_id']=='M42'
    assert 'created_at_utc' in review


def test_review_lists_retired_projects_without_reactivating_them(source,monkeypatch):
    from astropilot.app import create_app
    api=TestClient(create_app());revision=json.loads((source/'user_profile.json').read_text())['profile_revision']
    deleted=api.request('DELETE','/v1/projects/M42',json={'expected_revision':revision,'confirmed':True})
    assert deleted.status_code==200
    before=snapshot(source);raw,_=create_backup(source);_,review=inspect_backup_for_review(raw)
    assert review['projects']==1 and review['project_details'][0]['archived'] is True
    assert review['project_details'][0]['project_id']=='M42' and snapshot(source)==before
