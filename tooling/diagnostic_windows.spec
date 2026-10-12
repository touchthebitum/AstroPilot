# Diagnostic-only wrapper. Product spec and modules remain byte-for-byte at approved SHA.
import os
from pathlib import Path
original_analysis=Analysis
hook=Path(os.environ['DIAGNOSTIC_RUNTIME_HOOK']).resolve()
def Analysis(*args,**kwargs):
    kwargs['runtime_hooks']=[*kwargs.get('runtime_hooks',[]),str(hook)]
    return original_analysis(*args,**kwargs)
SPECPATH=os.environ['DIAGNOSTIC_SOURCE_ROOT']
original_spec=Path(SPECPATH)/'AstroPilot-windows.spec'
exec(compile(original_spec.read_text(encoding='utf-8'),str(original_spec),'exec'))
