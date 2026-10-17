from pathlib import Path
import json,os,subprocess,sys,tempfile,time,unittest,zipfile
from durable_diagnostic import DurableDiagnostic,MAX_LOG_BYTES
class CrashDiagnostics(unittest.TestCase):
 def test_allowlist_and_no_false_pass(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);case=root/'case';case.mkdir();out=root/'out';out.mkdir()
   (case/'user_profile.json').write_text('DO NOT EXPORT');(case/'fixture.key').write_text('DO NOT EXPORT');(case/'application-stdout.log').write_text('public fixture')
   x=DurableDiagnostic(case,out,'sha',interval=60)
   try:
    with zipfile.ZipFile(x.archive) as z:
     self.assertEqual(set(z.namelist()),{'checkpoint.json','application-stdout.log'});q=json.loads(z.read('checkpoint.json'));self.assertEqual(q['verdict'],'DIAGNOSTIC_ONLY');self.assertFalse(q['qualification_validated'])
   finally:x.close()
 def test_log_size_is_bounded(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);case=root/'case';case.mkdir();out=root/'out';out.mkdir();(case/'browser.log').write_bytes(b'x'*(MAX_LOG_BYTES+500))
   x=DurableDiagnostic(case,out,'sha',interval=60)
   try:
    with zipfile.ZipFile(x.archive) as z:self.assertEqual(len(z.read('browser.log')),MAX_LOG_BYTES)
   finally:x.close()
 def test_broken_snapshot_preserves_previous_archive(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);case=root/'case';case.mkdir();out=root/'out';out.mkdir();x=DurableDiagnostic(case,out,'sha',interval=60)
   try:
    before=x.archive.read_bytes()
    with patch('durable_diagnostic.os.replace',side_effect=OSError('shared output lost')):x.note('install_previous')
    self.assertEqual(x.archive.read_bytes(),before);self.assertTrue(x.errors)
   finally:x.close()
 def test_killed_process_leaves_readable_last_checkpoint(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);case=root/'case';case.mkdir();out=root/'out';out.mkdir();(case/'previous-installation.log').write_text('installer started')
   code="from durable_diagnostic import DurableDiagnostic;import sys,time;x=DurableDiagnostic(sys.argv[1],sys.argv[2],'test-sha',interval=.1);x.note('install_previous');time.sleep(60)"
   child=subprocess.Popen([sys.executable,'-c',code,str(case),str(out)],cwd=Path(__file__).parent)
   try:
    deadline=time.monotonic()+15;ready=False
    while time.monotonic()<deadline:
     try:
      p=next(out.glob('*/diagnostic-partiel.zip'))
      with zipfile.ZipFile(p) as z:ready=json.loads(z.read('checkpoint.json'))['stage']=='install_previous'
      if ready:break
     except (StopIteration,zipfile.BadZipFile,OSError):pass
     time.sleep(.05)
    self.assertTrue(ready);child.kill();child.wait(timeout=10)
    with zipfile.ZipFile(p) as z:
     self.assertIsNone(z.testzip());self.assertEqual(json.loads(z.read('checkpoint.json'))['stage'],'install_previous');self.assertEqual(z.read('previous-installation.log'),b'installer started')
   finally:
    if child.poll() is None:child.kill();child.wait(timeout=10)
if __name__=='__main__':unittest.main()
