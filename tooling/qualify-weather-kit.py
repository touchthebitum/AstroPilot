"""Native Windows qualification using only a synthetic profile."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
WORK=Path(os.environ['RUNNER_TEMP'])/'pr380-weather-qualification'
WORK.mkdir()
kit=WORK/'kit';kit.mkdir()
for name in ('test-meteo.py','weather_fixture.py','Create-test-certificates.ps1','windows_job.py','kit_safety.py'):
    shutil.copy2(ROOT/name,kit/name)
artifact_root=Path(os.environ['PR380_ARCHIVE_ROOT'])
archive=next(artifact_root.rglob('AstroPilot-1.0.0b8-windows-x86_64-portable.zip'))
provenance=json.loads(next(artifact_root.rglob('provenance.json')).read_text())
assert provenance['source_sha']=='331093b523673ac267d491f127584921dce096a7'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==os.environ['KIT_EXPECTED_PORTABLE_SHA']
with zipfile.ZipFile(archive) as z:
    binary=hashlib.sha256(z.read('AstroPilot/AstroPilot.exe')).hexdigest()
shutil.copy2(archive,kit/'AstroPilot-PR380-331093b-portable.zip')
profile={'location':{'name':'Synthetic qualification Madrid','latitude':40.4,'longitude':-3.7},
    'preferences':{'bortle':4},'active_equipment':'samyang_183','available_equipment':['samyang_183'],
    'sessions':[],'profile_revision':1,
    'projects':{'Sh2-129':{'hours':0,'target_hours':12,'imaging_field_id':'sh2-129_ou4',
        'acquisition_intent_targets':[{'acquisition_intent_id':i,'target_hours':6} for i in ('sh2-129_ha','ou4_oiii')],
        'acquisition_intent_progress':[{'acquisition_intent_id':i,'acquired_duration_manual':0} for i in ('sh2-129_ha','ou4_oiii')]}}}
content=json.dumps(profile).encode()
config=kit/'Configuration-Mac-reference.zip'
with zipfile.ZipFile(config,'w') as z: z.writestr('user_profile.json',content)
(kit/'Manifest-configuration-Mac.json').write_text(json.dumps({'user_profile.json':hashlib.sha256(content).hexdigest()}))
(kit/'Kit-provenance.json').write_text(json.dumps({'source_sha':provenance['source_sha'],
    'portable_zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'binary_sha256':binary,'mac_reference_zip_sha256':hashlib.sha256(config.read_bytes()).hexdigest()}))
result=subprocess.run([sys.executable,str(kit/'test-meteo.py')],text=True,capture_output=True,timeout=900)
(WORK/'qualification-console.txt').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
comparisons=list(kit.glob('resultats-meteo-*/comparison.json'))
assert len(comparisons)==1,(result.returncode,result.stdout,result.stderr)
report=json.loads(comparisons[0].read_text())
shutil.copy2(comparisons[0],WORK/'qualification-comparison.json')
assert result.returncode==0 and report['overall_result']=='PASS',report
assert report['reference_unchanged'] and report['simulated_weather']
assert len(report['cases'])==5
for case in report['cases']:
    assert case['failure_valid'] and case['recovery_valid'] and case['distinct_ids']
    assert case['profile_copy_unchanged'] and not case['legacy_inventory_created']
    assert case['single_call_per_phase'] and not case['fixture_errors']
    assert case['binary_stopped'] and case['port_released'] and case['fixture_stopped']
archive=kit/(comparisons[0].parent.name+'.zip')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert not any('user_profile' in name or 'certificats' in name or name.endswith('.pem') or name.endswith('.key') for name in z.namelist())
shutil.copy2(archive,WORK/'qualification-results.zip')
(WORK/'qualification.json').write_text(json.dumps({'passed':True,'source_sha':provenance['source_sha'],
    'simulated_only':True,'profile':'synthetic only','real_user_data_accessed':False,
    'scenarios':[{k:c[k] for k in ('scenario','result','failure_valid','recovery_valid','single_call_per_phase','binary_stopped','fixture_stopped','port_released')} for c in report['cases']],
    'no_credentials_or_profile_in_export':True},indent=2))
print('Five native binary error/recovery scenarios PASS; process isolation and exports checked.')
