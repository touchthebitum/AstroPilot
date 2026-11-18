"""Durable local reminders must never write profile documents or travel in a ZIP."""
import hashlib,json,re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import astropilot.backup_check_receipt as receipts
from astropilot.profile_backup import snapshot,create_backup,inspect_backup,restore_empty,validate_documents
from astropilot.profile_transfer_app import create_transfer_app
from test_profile_backup import source


def checked():
    return {'filename':'Rosette-fictive.zip','checked_at_utc':'2026-11-16T12:00:00+00:00',
            'summary':{'projects':1,'sessions':0,'observations':0,'comparisons':0,'project_details':[
                {'project_id':'M42','filters':[],'recorded_total_seconds':0}]}}


def remember(root):
    return receipts.remember(root,snapshot(root),checked(),'a'*64)


def api(root):
    client=TestClient(create_transfer_app(directory=root,origin='http://testserver'))
    token=re.search(r'const token="([^"]+)"',client.get('/').text).group(1)
    return client,{'X-NightMerit-Transfer':token,'Origin':'http://testserver','X-NightMerit-File-Name':'Rosette-fictive.zip'}


def test_reopen_reads_durable_check_and_unchanged_data_without_self_invalidation(source):
    before=snapshot(source);assert receipts.read_status(source)=={'state':'none','record':None}
    assert remember(source);path=receipts.receipt_path(source);stored=path.read_bytes()
    assert path.parent==source.parent and path not in list(source.iterdir())
    for _ in range(2):
        client,_=api(source);state=client.get('/transfer/status').json()
        assert state['last_verified_backup']['state']=='current'
        assert state['last_verified_backup']['record']['filename']=='Rosette-fictive.zip'
        assert state['backup_activity']['last_check'] is None
    assert snapshot(source)==before and path.read_bytes()==stored


def test_content_change_is_outdated_even_without_revision_change(source):
    assert remember(source);path=receipts.receipt_path(source);stored=path.read_bytes()
    p=source/'user_profile.json';v=json.loads(p.read_text());v['projects']['M42']['target_hours']+=1;p.write_text(json.dumps(v))
    status=receipts.read_status(source);assert status['state']=='outdated'
    assert status['record']['checked_at_utc']==checked()['checked_at_utc']
    assert path.read_bytes()==stored


def test_technical_traces_and_touching_do_not_require_new_backup(source):
    assert remember(source)
    (source/'user_profile.json').touch();(source/'Logs').mkdir(exist_ok=True);(source/'Logs/trace.txt').write_text('technical')
    (source/'.outcome_history_cursor.key').write_text('technical');(source/'.new.lock').write_text('lock')
    assert receipts.read_status(source)['state']=='current'


@pytest.mark.parametrize('damage',['truncated','altered','oversized'])
def test_unreadable_reminder_never_claims_current_or_resets_profile(source,damage):
    assert remember(source);path=receipts.receipt_path(source);before=snapshot(source)
    if damage=='truncated':path.write_bytes(b'{')
    elif damage=='oversized':path.write_bytes(b'x'*(receipts.MAX_RECEIPT+1))
    else:
        value=json.loads(path.read_text());value['payload']['filename']='uncontrolled.zip';path.write_text(json.dumps(value))
    stored=path.read_bytes();assert receipts.read_status(source)=={'state':'unavailable','record':None}
    assert path.read_bytes()==stored and snapshot(source)==before


def test_linked_reminder_is_never_followed_or_overwritten(source,tmp_path):
    target=tmp_path/'keep.json';target.write_text('keep');receipts.receipt_path(source).symlink_to(target)
    assert receipts.read_status(source)['state']=='unavailable'
    with pytest.raises(ValueError):remember(source)
    assert target.read_text()=='keep'


def test_failed_atomic_write_preserves_previous_receipt_and_profile(source,monkeypatch):
    assert remember(source);path=receipts.receipt_path(source);stored=path.read_bytes();before=snapshot(source)
    def fail(*a):raise OSError('write denied')
    monkeypatch.setattr(receipts.os,'replace',fail)
    with pytest.raises(OSError):remember(source)
    assert path.read_bytes()==stored and snapshot(source)==before
    assert not list(path.parent.glob('.last-backup-check-*'))


def test_receipt_is_local_to_each_profile_and_not_exported_or_restored(source,tmp_path):
    assert remember(source);original=receipts.receipt_path(source).read_bytes()
    raw,_=create_backup(source,validator=validate_documents);files,_=inspect_backup(raw,validator=validate_documents)
    other=tmp_path/'new';restore_empty(other,files,validator=validate_documents)
    assert snapshot(other)==snapshot(source)
    assert receipts.receipt_path(source)!=receipts.receipt_path(other)
    assert receipts.read_status(other)=={'state':'none','record':None}
    assert remember(other) and receipts.read_status(other)['state']=='current'
    assert receipts.receipt_path(source).read_bytes()==original


def test_export_alone_does_not_update_saved_check_but_successful_check_does(source):
    client,h=api(source);before=snapshot(source)
    exported=client.post('/transfer/export',headers=h);assert exported.status_code==200
    assert receipts.read_status(source)['state']=='none'
    result=client.post('/transfer/check',content=exported.content,headers=h)
    assert result.status_code==200 and result.json()['history_saved'] is True
    assert receipts.read_status(source)['state']=='current' and snapshot(source)==before
    p=source/'user_profile.json';v=json.loads(p.read_text());v['projects']['M42']['target_hours']+=1;p.write_text(json.dumps(v))
    exported=client.post('/transfer/export',headers=h);assert exported.status_code==200
    assert receipts.read_status(source)['state']=='outdated'
    assert client.post('/transfer/check',content=exported.content,headers=h).json()['history_saved'] is True
    assert receipts.read_status(source)['state']=='current'


def test_store_failure_does_not_undo_archive_check_or_claim_memory(source,monkeypatch):
    client,h=api(source);raw=client.post('/transfer/export',headers=h).content;before=snapshot(source)
    def fail(*a):raise OSError('blocked')
    # Captured function invokes this publication primitive at request time.
    monkeypatch.setattr(receipts.os,'replace',fail)
    result=client.post('/transfer/check',content=raw,headers=h)
    assert result.status_code==200 and result.json()['verified'] is True and result.json()['history_saved'] is False
    assert receipts.read_status(source)['state']=='none' and snapshot(source)==before


def test_no_profile_is_created_to_record_a_check(tmp_path):
    root=tmp_path/'does-not-exist/profil';before=set(tmp_path.iterdir())
    assert receipts.remember(root,{},checked(),'a'*64) is False
    assert receipts.read_status(root)['state']=='none'
    assert set(tmp_path.iterdir())==before
