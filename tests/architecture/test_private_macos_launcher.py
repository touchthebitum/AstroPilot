import importlib.util,json,os,tempfile,unittest
import pytest
pytest.importorskip("fcntl", reason="Mac launcher uses the native POSIX lock")
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('private_beta',Path(__file__).resolve().parents[2]/'scripts/private_beta_macos/launcher.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Safety(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'copy';self.root.mkdir()
 def tearDown(self):self.tmp.cleanup()
 def manifest(self,files):
  (self.root/'manifest.json').write_text(json.dumps({'source_sha':m.SHA,'files':files}))
 def test_environment_does_not_reuse_external_data_proxy_or_browser(self):
  with patch.dict(os.environ,{'ASTROPILOT_DATA_DIR':'/external/profile','FIELD_LAB_ROOT':'/external/nas','ASTROPILOT_CODESIGN_IDENTITY':'personal','HTTPS_PROXY':'http://external','REQUESTS_CA_BUNDLE':'/external/ca','BROWSER':'external'}):
   env=m.environment(self.root/'case',self.root/'BetaLauncher/BetaLauncher')
  self.assertEqual(env['ASTROPILOT_DATA_DIR'],str(self.root/'case/profil'))
  self.assertNotIn('FIELD_LAB_ROOT',env);self.assertNotIn('HTTPS_PROXY',env);self.assertNotIn('REQUESTS_CA_BUNDLE',env);self.assertNotIn('ASTROPILOT_CODESIGN_IDENTITY',env)
  self.assertIn('--ignore-browser',env['BROWSER'])
  for key in ('HOME','APPDATA','LOCALAPPDATA','TMPDIR','XDG_DATA_HOME'):self.assertTrue(Path(env[key]).is_relative_to(self.root))
 def test_headed_browser_uses_test_keychain_and_keeps_sandbox(self):
  args=m.browser_arguments(self.root/'Chrome',self.root/'case')
  self.assertIn('--use-mock-keychain',args)
  self.assertIn('--user-data-dir='+str(self.root/'case/navigateur'),args)
  self.assertFalse(any('no-sandbox' in arg or 'disable-setuid-sandbox' in arg or 'ignore-certificate-errors' in arg for arg in args))
 def test_changed_binary_is_refused(self):
  p=self.root/'binary';p.write_bytes(b'original');self.manifest({'binary':{'sha256':m.digest(p)}});p.write_bytes(b'changed')
  with self.assertRaisesRegex(RuntimeError,'modifié'):m.verify(self.root)
 def test_external_manifest_path_is_refused_without_changing_sentinel(self):
  sentinel=self.root.parent/'outside';sentinel.write_bytes(b'preserve');self.manifest({'../outside':{'sha256':m.digest(sentinel)}})
  with self.assertRaisesRegex(RuntimeError,'hors'):m.verify(self.root)
  self.assertEqual(sentinel.read_bytes(),b'preserve')
 def test_existing_listener_is_not_stopped_or_started_again(self):
  self.manifest({})
  with patch.object(m,'owners',return_value={12345}),patch.object(m.subprocess,'Popen') as spawn,patch.object(m,'terminate_owned') as terminate:
   with self.assertRaisesRegex(RuntimeError,'occupe'):m.start(self.root)
  spawn.assert_not_called()
  self.assertTrue(all(c.args==(None,) for c in terminate.call_args_list))
 def test_stop_does_not_contact_stale_or_foreign_owner(self):
  p=self.root/'DONNEES-BETA';p.mkdir();(p/'controle.json').write_text(json.dumps({'pid':123,'port':1234,'token':'own'}))
  with patch.object(m,'owners',return_value={456}),patch.object(m.OPENER,'open') as request:
   with self.assertRaisesRegex(RuntimeError,'aucun autre'):m.stop(self.root)
  request.assert_not_called()
if __name__=='__main__':unittest.main()


def test_rendered_mac_commands_are_separate_and_refuse_existing_directory(tmp_path):
 import runpy
 render=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/render_private_macos_launcher.py'))['render']
 output=render('a'*40,tmp_path/'copie été')
 assert '--data-transfer' in (output/'GERER-MES-DONNEES.command').read_text()
 assert '--data-transfer' not in (output/'DEMARRER-BETA.command').read_text()
 assert '--stop' in (output/'ARRETER-BETA.command').read_text()
 assert '__SOURCE_SHA__' not in (output/'launcher.py').read_text()
 before=(output/'launcher.py').read_bytes()
 with pytest.raises(FileExistsError):render('a'*40,output)
 assert (output/'launcher.py').read_bytes()==before


def test_stable_mac_versions_share_only_the_beta_profile_and_release_their_lease(tmp_path,monkeypatch):
 from types import SimpleNamespace
 import fcntl
 home=tmp_path/'home';home.mkdir();monkeypatch.setattr(m.Path,'home',lambda:home)
 monkeypatch.setattr(m,'DATA_MODE','stable');monkeypatch.setattr(m,'verify',lambda root:None)
 monkeypatch.setattr(m,'owners',lambda port:set())
 socket_stub=__import__('unittest.mock',fromlist=['MagicMock']).MagicMock()
 socket_stub.__enter__.return_value.connect_ex.return_value=1
 monkeypatch.setattr(m.socket,'socket',lambda *a,**k:socket_stub)
 calls=[]
 def prepare(args,**kw):
  calls.append((args,kw['env']['ASTROPILOT_DATA_DIR']))
  return SimpleNamespace(returncode=0,stderr='')
 monkeypatch.setattr(m.subprocess,'run',prepare)
 monkeypatch.setattr(m.subprocess,'Popen',__import__('unittest.mock',fromlist=['Mock']).Mock(side_effect=RuntimeError('sentinel')))
 for name,sha in [('version1','a'*40),('version2','b'*40)]:
  root=tmp_path/name;root.mkdir();monkeypatch.setattr(m,'SHA',sha)
  with pytest.raises(RuntimeError,match='sentinel'):m.start(root)
 assert calls[0][1]==calls[1][1]==str(home/'Library/Application Support/NightMerit/PrivateBeta/profil')
 assert calls[0][0][-2:]==['--prepare-stable-beta','a'*40]
 assert calls[1][0][-2:]==['--prepare-stable-beta','b'*40]
 # Neither old nor new application folder receives the shared profile.
 assert not (tmp_path/'version1/DONNEES-BETA/profil').exists()
 with (home/'Library/Application Support/NightMerit/PrivateBeta/.nightmerit-session.lock').open('a+b') as lease:
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)


def test_stable_mac_root_is_not_the_production_profile_and_refuses_aliases(tmp_path):
 root=m.stable_data_directory(tmp_path)
 assert root==tmp_path/'Library/Application Support/NightMerit/PrivateBeta'
 assert root!=tmp_path/'Library/Application Support/AstroPilot'
 bad=tmp_path/'redirected';bad.mkdir();(bad/'Library').symlink_to(tmp_path/'Library',target_is_directory=True)
 with pytest.raises(RuntimeError,match='lié'):m.stable_data_directory(bad)
