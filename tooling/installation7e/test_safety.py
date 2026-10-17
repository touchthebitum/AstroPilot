import unittest,tempfile,json,os
from pathlib import Path
from unittest.mock import patch,Mock
import controller as c

class Safety(unittest.TestCase):
 def test_windows_host_install_refused(self):
  with patch.object(c.os,'name','nt'),patch.dict(c.os.environ,{'USERNAME':'ordinary-user','GITHUB_ACTIONS':'','RUNNER_ENVIRONMENT':''},clear=True):
   with self.assertRaisesRegex(RuntimeError,'Windows Sandbox'):c.windows_allowed()
 def test_external_delete_refused(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'case';root.mkdir()
   with self.assertRaises(RuntimeError):c.inside(root.parent/'real',root)
   with self.assertRaises(RuntimeError):c.inside(root,root)
   self.assertEqual(c.inside(root/'installation',root),(root/'installation').resolve())
 def test_symlink_outside_refused(self):
  if os.name=='nt':return
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'case';root.mkdir();(root/'escape').symlink_to(root.parent,target_is_directory=True)
   with self.assertRaises(RuntimeError):c.inside(root/'escape/real',root)
 def test_existing_data_never_reseeded(self):
  with tempfile.TemporaryDirectory() as d:
   x=c.Installation.__new__(c.Installation);x.case=Path(d);x.state={'phase':'new'};(x.case/'data').mkdir();p=x.case/'data/existing.json';p.write_text('keep')
   with self.assertRaisesRegex(RuntimeError,'existe déjà'):x.start()
   self.assertEqual(p.read_text(),'keep')
 def test_running_test_never_reseeded(self):
  x=c.Installation.__new__(c.Installation);x.state={'phase':'replayed'}
  with self.assertRaisesRegex(RuntimeError,'recréez'):x.start()
 def test_resume_rejects_unmarked_copy(self):
  with tempfile.TemporaryDirectory() as d,patch.object(c,'windows_allowed'):
   with self.assertRaisesRegex(RuntimeError,'reprise'):c.resume(Path(d),Path(d),False)
 def test_environment_isolated(self):
  with tempfile.TemporaryDirectory() as d:
   app=c.c.App(Path(d),Path(d)/'case',Mock(env={}))
   with patch.dict(os.environ,{'ASTROPILOT_DATA_DIR':'real','NIGHTMERIT_FOREIGN':'real','ASTROPILOT_GUARDIAN_ATTESTATION_PATH':'real'}):env=app.env()
   self.assertNotIn('NIGHTMERIT_FOREIGN',env);self.assertNotIn('ASTROPILOT_GUARDIAN_ATTESTATION_PATH',env);self.assertEqual(env['ASTROPILOT_DATA_DIR'],str(Path(d)/'case/data'))
 def test_export_does_not_claim_physical_confirmation(self):
  source=(Path(__file__).with_name('base_controller.py')).read_text()
  self.assertIn("'PASS_LAB' if valid and self.lab",source)
  self.assertIn("'laboratory automation, not physical user proof'",source)
 def test_sandbox_maps_only_results_writable(self):
  source=Path(__file__).with_name('launch-sandbox.ps1').read_text();self.assertEqual(source.count('<ReadOnly>false</ReadOnly>'),1);self.assertIn('<SandboxFolder>C:\\NightMeritResults</SandboxFolder>',source);self.assertIn('<Networking>Disable</Networking>',source);self.assertNotIn('ExecutionPolicy',source)
if __name__=='__main__':unittest.main()
