"""Safety regressions for the test kit, on disposable files only."""
import unittest,tempfile,json,zipfile,os
from pathlib import Path
from unittest.mock import patch,Mock
import controller as c

class Safety(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.case=self.root/'case';self.case.mkdir()
 def tearDown(self):self.tmp.cleanup()
 def test_inherited_product_paths_are_cleared(self):
  with patch.dict(os.environ,{'ASTROPILOT_DATA_DIR':'FORBIDDEN','ASTROPILOT_GUARDIAN_ATTESTATION_PATH':'FORBIDDEN','NIGHTMERIT_FOREIGN':'FORBIDDEN','HTTPS_PROXY':'FORBIDDEN'}):
   app=c.App(self.root,self.case,Mock(env={'HTTPS_PROXY':'http://127.0.0.1:1'}));env=app.env()
   self.assertNotIn('ASTROPILOT_GUARDIAN_ATTESTATION_PATH',env);self.assertNotIn('NIGHTMERIT_FOREIGN',env)
   self.assertEqual(env['ASTROPILOT_DATA_DIR'],str(self.case/'data'));self.assertEqual(env['HTTPS_PROXY'],'http://127.0.0.1:1')
   for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP'):self.assertTrue(Path(env[key]).is_relative_to(self.case))
 def test_foreign_listener_is_never_started_or_stopped(self):
  app=c.App(self.root,self.case,Mock());app.owners=lambda:{12345}
  with patch('subprocess.Popen') as run:
   with self.assertRaisesRegex(RuntimeError,'occupé'):app.start()
   app.stop();run.assert_not_called()
 def test_manifest_rejects_tamper_and_escape(self):
  p=self.root/'sample';p.write_bytes(b'original');c.write(self.root/'manifest.json',{'source_sha':c.SHA,'files':{'sample':{'sha256':c.digest(p)}}});c.verify(self.root)
  p.write_bytes(b'changed')
  with self.assertRaisesRegex(RuntimeError,'modifié'):c.verify(self.root)
  c.write(self.root/'manifest.json',{'source_sha':c.SHA,'files':{'../outside':{'sha256':'no'}}})
  with self.assertRaisesRegex(RuntimeError,'hors'):c.verify(self.root)
 def fake(self):
  x=c.Controller.__new__(c.Controller);x.kit=self.root;x.case=self.case;x.lab=True;x.state={'phase':'running','user_confirmations':{}};x.error=None;x.exported=None;x.app=Mock();x.app.child.pid=123;x.app.owners.return_value={123};x.app.identity={'build':'108e531'}
  (self.case/'data').mkdir();(self.case/'data/profile.json').write_text('{"public":true}')
  x.last_progress={};x.last_sessions=[{'execution':{'execution_id':'existing'},'credit':{'evidence_ids':['existing-evidence']}}];x.inspect=lambda:{'ready':True};return x
 def test_replay_cannot_declare_success_for_new_credit(self):
  x=self.fake()
  with patch.object(c,'request',side_effect=lambda method,path,body=None:{'profile_revision':1} if method=='GET' else {'status':'applied'}):
   with self.assertRaisesRegex(RuntimeError,'conservé'):x.restart(True)
  self.assertEqual(x.state['phase'],'running')
 def test_replay_cannot_declare_success_when_bytes_change(self):
  x=self.fake()
  def query(method,path,body=None):
   if method=='GET':return {'profile_revision':1}
   (self.case/'data/profile.json').write_text('{"changed":true}');return {'status':'already_applied'}
  with patch.object(c,'request',side_effect=query):
   with self.assertRaisesRegex(RuntimeError,'conservé'):x.restart(True)
  self.assertEqual(x.state['phase'],'running')
 def test_export_without_visual_confirmation_is_incomplete_and_excludes_keys(self):
  x=self.fake();(self.case/'fixture.key').write_text('TEST-KEY');(self.case/'data/user_profile.json').write_text('{"synthetic":true}')
  (self.case/'browser-profile').mkdir();(self.case/'browser-profile/state').write_text('private browser state')
  output=x.export(False,incomplete=True)
  with zipfile.ZipFile(output) as z:
   self.assertEqual(json.loads(z.read('qualification.json'))['verdict'],'NOT_VALIDATED')
   self.assertFalse(any('profile' in n or n.endswith('.key') for n in z.namelist()))
if __name__=='__main__':unittest.main()
