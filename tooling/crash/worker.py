"""Test-only suspension points; parent kills this process, no graceful cleanup."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

import session_seed as seed

data = Path(sys.argv[1]).resolve()
command = json.loads(sys.argv[2])
stage = command.pop('crash_stage', None)
marker = data.parent/'suspended.json'

def suspend(point, status=None):
    if stage != point:
        return
    record = {'stage':point,'pid':os.getpid(),'boot_id':seed.BOOT_ID,'status':status}
    pending = marker.with_suffix('.tmp')
    with pending.open('w',encoding='utf-8') as f:
        json.dump(record,f);f.flush();os.fsync(f.fileno())
    pending.replace(marker)
    threading.Event().wait(180)
    raise AssertionError('Parent did not kill the suspended process')

if stage in ('before_replace','after_replace'):
    original_replace = Path.replace
    def replace(path,target):
        if Path(target) == data/'user_profile.json':
            suspend('before_replace')
            result = original_replace(path,target)
            suspend('after_replace')
            return result
        return original_replace(path,target)
    Path.replace = replace
elif stage == 'partial_temp':
    original_temporary = tempfile.NamedTemporaryFile
    class PartialWriter:
        def __init__(self, handle): self.handle=handle
        def __getattr__(self,name): return getattr(self.handle,name)
        def __enter__(self): return self
        def __exit__(self,*args): return self.handle.__exit__(*args)
        def write(self,document):
            self.handle.write(document[:len(document)//2])
            self.handle.flush();os.fsync(self.handle.fileno())
            suspend('partial_temp')
    def temporary(*args,**kwargs):
        handle=original_temporary(*args,**kwargs)
        if Path(kwargs.get('dir','')) == data and kwargs.get('prefix') == '.user_profile.':
            return PartialWriter(handle)
        return handle
    tempfile.NamedTemporaryFile = temporary
elif stage == 'replay_after_load':
    sys.path.insert(0,str(seed.ROOT))
    from astropilot.execution_lineage_store import FileExecutionLineageStore
    original_load = FileExecutionLineageStore.load_execution
    def load(self,execution_id):
        result=original_load(self,execution_id)
        suspend('replay_after_load')
        return result
    FileExecutionLineageStore.load_execution = load

result=seed.worker(data,command)
suspend('after_response',result['body'].get('status'))
suspend('replay_response',result['body'].get('status'))
print(json.dumps(result))
