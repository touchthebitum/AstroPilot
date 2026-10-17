"""Best-effort crash breadcrumbs in the explicitly mapped results directory only."""
from pathlib import Path
import json,os,secrets,threading,time,zipfile
from datetime import datetime,timezone
LOGS=('previous-installation.log','candidate-installation.log','uninstall.log','installer-output.log','application-stdout.log','application-stderr.log','controller.log','browser.log')
MAX_LOG_BYTES=256*1024
class DurableDiagnostic:
 def __init__(self,case,output_root,source_sha,interval=3):
  self.case=Path(case).resolve();self.root=Path(output_root).resolve();self.source_sha=source_sha;self.interval=interval
  if not self.root.is_dir():raise RuntimeError('Dossier de résultats mappé absent.')
  self.folder=self.root/('diagnostic-en-cours-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(6));self.folder.mkdir(exist_ok=False)
  self.archive=self.folder/'diagnostic-partiel.zip';self.stage='controller_initialisation';self.events=[];self.lock=threading.Lock();self.stop_event=threading.Event();self.errors=[]
  self.note(self.stage);self.thread=threading.Thread(target=self._watch,daemon=True);self.thread.start()
 def note(self,stage):
  with self.lock:
   self.stage=stage;self.events.append({'at_utc':datetime.now(timezone.utc).isoformat(),'stage':stage});self.events=self.events[-100:]
  self.snapshot()
 def snapshot(self):
  with self.lock:
   report={'schema_version':1,'kind':'sandbox_crash_breadcrumbs','verdict':'DIAGNOSTIC_ONLY','source_sha':self.source_sha,'at_utc':datetime.now(timezone.utc).isoformat(),'stage':self.stage,'stages':list(self.events),'real_profile_accessed':False,'qualification_validated':False,'max_bytes_per_log':MAX_LOG_BYTES}
   run=self.case/'run.json'
   if run.is_file() and not run.is_symlink():
    try:
     state=json.loads(run.read_text(encoding='utf-8'))
     report['test_state']={k:state[k] for k in ('phase','qualification','operations','automatic_installation_pass','canonical_bytes_unchanged') if k in state}
    except (OSError,ValueError) as e:report['state_read_error']=type(e).__name__
   temporary=self.folder/'diagnostic-partiel.tmp'
   try:
    with temporary.open('wb') as stream:
     with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
      z.writestr('checkpoint.json',json.dumps(report,indent=2,ensure_ascii=False))
      for name in LOGS:
       p=self.case/name
       if not p.is_file() or p.is_symlink() or p.resolve().parent!=self.case:continue
       try:
        with p.open('rb') as f:
         size=f.seek(0,2);f.seek(max(0,size-MAX_LOG_BYTES));raw=f.read(MAX_LOG_BYTES)
        z.writestr(name,raw)
       except OSError:pass
     stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,self.archive)
   except OSError as e:
    # Diagnostics must never change the product verdict or prevent a later export.
    self.errors.append(type(e).__name__)
 def _watch(self):
  while not self.stop_event.wait(self.interval):self.snapshot()
 def close(self):
  self.stop_event.set();self.thread.join(timeout=5);self.note('controller_stopping')
