"""Refuse ambiguous process ownership; never signal a guessed PID."""
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
import sys
if sys.platform != "darwin":
    pytest.skip("Lanceur Mac : qualification native séparée", allow_module_level=True)
from astropilot.macos_kit_manager import KitManager,LaunchError,main

@pytest.fixture
def managed(tmp_path,monkeypatch):
    kit=tmp_path/'Kit';kit.mkdir();manager=KitManager(kit)
    manager.runtime.mkdir()
    info=kit.stat();record={'root_identity':[info.st_dev,info.st_ino],'pid':123,
        'process_start':'unique-start','session_id':'a'*64,'kit_directory':str(kit)}
    (manager.runtime/'process.json').write_text(json.dumps(record))
    monkeypatch.setattr(manager,'listener',lambda:123)
    monkeypatch.setattr(manager,'start_time',lambda pid:'unique-start')
    monkeypatch.setattr(manager,'read',lambda route:{'status':'managed','session_id':'a'*64,'service':'application','location_status':'available'})
    return manager,record


def test_moved_same_directory_is_owned_but_duplicated_directory_is_not(managed,tmp_path):
    manager,record=managed
    moved=tmp_path/'Moved';manager.root.rename(moved)
    renamed=KitManager(moved)
    renamed.listener=manager.listener;renamed.start_time=manager.start_time;renamed.read=manager.read
    assert renamed.owner()['moved']
    copy=tmp_path/'Copy';copy.mkdir();(copy/'runtime').mkdir();(copy/'runtime/process.json').write_text(json.dumps(record))
    duplicate=KitManager(copy);duplicate.listener=manager.listener;duplicate.start_time=manager.start_time;duplicate.read=manager.read
    with pytest.raises(LaunchError):duplicate.owner()


def test_reused_pid_is_rejected_before_any_http_read(managed):
    manager,_=managed;manager.start_time=lambda pid:'different-start';manager.read=Mock()
    with pytest.raises(LaunchError):manager.owner()
    manager.read.assert_not_called()


def test_other_session_nonce_is_rejected(managed):
    manager,_=managed;manager.read=lambda route:{'status':'managed','session_id':'b'*64,'service':'application'}
    with pytest.raises(LaunchError):manager.owner()


def test_pid_switch_before_stop_never_signals_foreign_process(managed,monkeypatch):
    manager,record=managed
    manager.owner=lambda:{'pid':123,'record':record};manager.listener=lambda:456
    kill=Mock();monkeypatch.setattr('os.kill',kill)
    with pytest.raises(LaunchError):manager.stop()
    kill.assert_not_called()


def test_start_of_moved_copy_has_actionable_error_without_launch(managed,monkeypatch):
    manager,_=managed
    manager.owner=lambda:{'moved':True}
    spawn=Mock();monkeypatch.setattr('subprocess.Popen',spawn)
    with pytest.raises(LaunchError,match='ARRETER-MES-PROJETS'):manager.start('application')
    spawn.assert_not_called()


def test_runtime_link_is_refused_without_lock_write(tmp_path):
    kit=tmp_path/'Kit';kit.mkdir();elsewhere=tmp_path/'Elsewhere';elsewhere.mkdir();(kit/'runtime').symlink_to(elsewhere,target_is_directory=True)
    with pytest.raises(LaunchError):
        with KitManager(kit).locked():pass
    assert not list(elsewhere.iterdir())


def test_profile_link_is_refused_before_start(tmp_path):
    kit=tmp_path/'Kit';kit.mkdir();(kit/'DONNEES-PERSONNELLES').symlink_to(tmp_path/'Other')
    with pytest.raises(LaunchError,match='lien'):KitManager(kit).validate_paths()

@pytest.mark.parametrize('settings',[[],{'port':True},{'port':8000},None])
def test_invalid_settings_produce_human_error_not_traceback(tmp_path,capsys,settings):
    (tmp_path/'KIT.json').write_text(json.dumps(settings))
    assert main(root=tmp_path,argv=['open'])==1
    output=capsys.readouterr().err
    assert output.startswith('NightMerit :') and 'Traceback' not in output


def test_stopped_copy_does_not_need_usable_session_record(tmp_path):
    manager=KitManager(tmp_path);manager.listener=lambda:None
    assert 'déjà arrêtée' in manager.stop()


def test_no_second_process_during_unfinished_assistant_transition(managed,monkeypatch):
    manager,_=managed;manager.owner=lambda:None;manager.pending_session=lambda:True
    clock=iter([0,16]);monkeypatch.setattr('time.monotonic',lambda:next(clock))
    spawn=Mock();monkeypatch.setattr('subprocess.Popen',spawn)
    with pytest.raises(LaunchError,match='seconde application'):manager.start('application')
    spawn.assert_not_called()


def test_no_false_stopped_message_during_transition(managed,monkeypatch):
    manager,_=managed;manager.owner=lambda:None;manager.pending_session=lambda:True
    clock=iter([0,16]);monkeypatch.setattr('time.monotonic',lambda:next(clock))
    kill=Mock();monkeypatch.setattr('os.kill',kill)
    with pytest.raises(LaunchError):manager.stop()
    kill.assert_not_called()


def test_first_unsaved_configuration_can_resume_without_deleting_runtime_key(tmp_path):
    manager=KitManager(tmp_path);manager.profile.mkdir(parents=True)
    key=manager.profile/'.outcome_history_cursor.key';key.write_bytes(b'keep existing runtime secret')
    manager.check_missing_profile()
    assert key.read_bytes()==b'keep existing runtime secret'
    assert not (manager.profile/'user_profile.json').exists()


def test_previously_known_profile_cannot_be_replaced_by_empty_configuration(managed):
    manager,record=managed
    record['known_profile']=True;(manager.runtime/'process.json').write_text(json.dumps(record))
    with pytest.raises(LaunchError,match='Aucun profil vide'):manager.check_missing_profile()
    assert not manager.profile.exists()


def test_unknown_data_without_profile_is_never_discarded(tmp_path):
    manager=KitManager(tmp_path);manager.profile.mkdir(parents=True);unknown=manager.profile/'unknown.json';unknown.write_bytes(b'{sentinel}')
    with pytest.raises(LaunchError):manager.check_missing_profile()
    assert unknown.read_bytes()==b'{sentinel}'


def test_disappeared_kit_directory_is_never_recreated(tmp_path,capsys):
    missing=tmp_path/'kit déplacé avant ouverture'
    assert main(root=missing,argv=['start-only'])==1
    assert not missing.exists()
    assert 'Traceback' not in capsys.readouterr().err


def test_declared_copy_type_is_passed_but_never_inherited(tmp_path,monkeypatch):
    monkeypatch.setenv('NIGHTMERIT_COPY_KIND','personal')
    for kind in ['fictitious','personal',None]:
        root=tmp_path/(kind or 'unknown');root.mkdir();manager=KitManager(root,copy_kind=kind)
        manager.runtime.mkdir()
        env=manager.environment({})
        assert env.get('NIGHTMERIT_COPY_KIND')==kind
    for invalid in ['wrong',{},[],True]:
        with pytest.raises(LaunchError,match='type de cette copie'):
            KitManager(tmp_path,copy_kind=invalid)


def test_separate_test_port_is_supported_without_enabling_default_port(tmp_path):
    manager=KitManager(tmp_path,port=18871,copy_kind='fictitious')
    assert manager.port==18871 and manager.base=='http://127.0.0.1:18871'
    with pytest.raises(LaunchError):KitManager(tmp_path,port=8000)
