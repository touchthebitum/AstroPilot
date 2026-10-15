"""Interrupted real installer/bundle operations; public fixture, disposable targets only."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import qualify as u

SHA='dad6e438b8ba0f5ce52d59457ce503e030911d80'
OUT=u.OUT
ROWS=[]
BASE_SENTINELS=dict(u.SENTINELS)

def record(row):
    ROWS.append(row)
    (OUT/'interrupted-qualification.json').write_text(json.dumps({'result':'RUNNING','product_sha':SHA,'os':platform.platform(),'rows':ROWS},indent=2)+'\n')

def verify(case,exe,sha,before,label):
    u.ACTIVE=case
    identities=[]
    for boot in range(2):
        with u.Server(exe,case,sha,'1.0.0b8') as server:
            identities.append(server.identity)
            u.check_credits()
            if sha==SHA:u.check_assets()
        assert u.authority(case/'data')==before,('authority changed',label,boot)
    record({'case':case.name,'stage':label,'result':'PASS','runtime_identity':identities,
        'boots':2,'replays_per_intent_per_boot':3,'ha_seconds':5400,'oiii_seconds':900,
        'authority_unchanged':True})

def installer_args(candidate,case,log):
    return [str(candidate),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS','/TASKS=',f'/LOG={log}']

def windows_interrupt(case,threshold,previous_inventory):
    # A private job object contains only this child and its descendants.
    # Closing/terminating it cannot affect other installers or an existing app.
    from ctypes import wintypes
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];k.CreateJobObjectW.restype=wintypes.HANDLE
    k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];k.AssignProcessToJobObject.restype=wintypes.BOOL
    k.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT];k.TerminateJobObject.restype=wintypes.BOOL
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    job=k.CreateJobObjectW(None,None);assert job
    log=case/'interrupted-install.log'
    child=subprocess.Popen(installer_args(u.CURRENT,case,log),env=u.environment(case))
    assigned=k.AssignProcessToJobObject(job,wintypes.HANDLE(int(child._handle)))
    if not assigned:
        child.kill();child.wait();raise ctypes.WinError(ctypes.get_last_error())
    reached=False;observed='';started=time.monotonic()
    try:
        while time.monotonic()-started<120:
            if child.poll() is not None:raise AssertionError('Installer finished before interruption checkpoint')
            if log.exists():
                observed=log.read_text(encoding='utf-8-sig',errors='replace')
                count=observed.count('Successfully installed the file.')
                trigger=('Installing the file.' in observed) if threshold==0 else count>=threshold
                if trigger:
                    assert 'Installation process succeeded.' not in observed
                    assert k.TerminateJobObject(job,99)
                    child.wait(timeout=30);reached=True;break
            time.sleep(.002)
    finally:
        if child.poll() is None:k.TerminateJobObject(job,99);child.wait(timeout=30)
        k.CloseHandle(job)
    assert reached
    target=case/'Applications/AstroPilot'
    expected=u.bundle_inventory(u.payload_root());actual=u.bundle_inventory(target)
    matching=sum(actual.get(k)==v for k,v in expected.items())
    assert matching<len(expected),('Interruption did not leave incomplete payload',matching)
    # A hard-killed Inno process can leave an unpublished uninstall temporary.
    # Record only files newly created by this interrupted installer, never delete
    # them or broaden the product cleanup. Repair must preserve these exact bytes.
    orphans={}
    for key,value in actual.items():
        if key not in expected and key not in BASE_SENTINELS and re.fullmatch(r'is-[A-Za-z0-9]+\.tmp',Path(key).name):
            assert key not in previous_inventory,'Unexpected pre-existing temporary'
            p=target/key;content=p.read_bytes();orphans[key]={'sha256':u.digest(p),'size':len(content)}
            u.SENTINELS[key]=content
    record({'case':case.name,'stage':'interrupted','result':'PASS','method':'TerminateJobObject owned installer tree',
        'installer_created_orphans_preserved':orphans,
        'checkpoint_successful_copy_count':observed.count('Successfully installed the file.'),
        'requested_copy_threshold':threshold,'installer_returncode':child.returncode,
        'observed_before_success':True,'payload_matching_files':matching,'payload_files':len(expected),
        'payload_incomplete':True,'interrupted_log_sha256':u.digest(log)})

def mac_copy_interrupt(case,inplace):
    target=case/'Applications/AstroPilot.app'
    destination=target if inplace else case/'Applications/incoming.app'
    baseline=u.bundle_inventory(target)
    out=(case/'ditto-interrupted.log').open('wb')
    child=subprocess.Popen(['/usr/bin/ditto',str(u.CURRENT),str(destination)],stdout=out,stderr=out,env=u.environment(case))
    reached=False;started=time.monotonic();changed=[]
    try:
        while time.monotonic()-started<60:
            assert child.poll() is None,'ditto completed before checkpoint'
            # The large frozen archive is copied before the whole bundle is ready.
            archive=destination/'Contents/Resources/base_library.zip'
            candidates=[destination/'Contents/MacOS/AstroPilot',archive]
            if inplace:
                changed=[p.relative_to(destination).as_posix() for p in candidates if p.is_file() and baseline.get(p.relative_to(destination).as_posix())!={'sha256':u.digest(p)}]
                trigger=bool(changed)
            else:trigger=any(p.exists() for p in candidates)
            if trigger:child.kill();child.wait(timeout=30);reached=True;break
            time.sleep(.001)
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=30)
        out.close()
    assert reached
    expected=u.bundle_inventory(u.CURRENT);actual=u.bundle_inventory(destination)
    matching=sum(actual.get(k)==v for k,v in expected.items())
    assert actual!=expected,'Copy completed despite interruption'
    if not inplace:assert u.bundle_inventory(target)==baseline
    else:assert actual!=baseline,'No replacement happened before interruption'
    record({'case':case.name,'stage':'interrupted','result':'PASS','method':'SIGKILL owned ditto process',
        'returncode':child.returncode,'copy_destination':'active_bundle' if inplace else 'staging_bundle',
        'current_matching_entries':matching,'current_entries':len(expected),'copy_incomplete':True,
        'active_bundle_unchanged':not inplace,'observed_changed_paths':changed})
    if not inplace:shutil.rmtree(destination)

def mac_promotion_gap(case):
    target=case/'Applications/AstroPilot.app';incoming=case/'Applications/incoming.app';old=case/'Applications/previous-gap.app'
    subprocess.run(['/usr/bin/ditto',str(u.CURRENT),str(incoming)],check=True)
    assert u.bundle_inventory(incoming)==u.bundle_inventory(u.CURRENT)
    marker=case/'promotion-marker'
    code="from pathlib import Path; import sys,time; Path(sys.argv[1]).rename(sys.argv[2]); Path(sys.argv[3]).write_text('old renamed; new not promoted'); time.sleep(120)"
    child=subprocess.Popen([sys.executable,'-c',code,str(target),str(old),str(marker)],env=u.environment(case))
    try:
        for _ in range(1000):
            if marker.exists():break
            assert child.poll() is None;time.sleep(.005)
        assert marker.exists();child.kill();child.wait(timeout=20)
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=20)
    assert not target.exists() and old.exists() and incoming.exists()
    # Explicit recovery of this local two-rename procedure, not an app updater.
    incoming.rename(target)
    subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(target)],check=True)
    record({'case':case.name,'stage':'interrupted','result':'PASS','method':'SIGKILL owned promotion controller',
        'observed_gap':True,'previous_bundle_preserved':True,'complete_staging_promoted_for_recovery':True})
    return target/'Contents/MacOS/AstroPilot'

def previous_restore(case,before):
    target=case/'Applications'/('AstroPilot' if u.WINDOWS else 'AstroPilot.app')
    if u.WINDOWS:
        subprocess.run(installer_args(u.MODERN,case,case/'downgrade.log'),env=u.environment(case),check=True,timeout=240)
        exe=target/'AstroPilot.exe'
    else:
        displaced=case/'current-before-rollback.app';target.rename(displaced)
        subprocess.run(['/usr/bin/ditto',str(u.MODERN),str(target)],check=True)
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(target)],check=True)
        exe=target/'Contents/MacOS/AstroPilot'
    verify(case,exe,u.MODERN_SHA,before,'previous_version_replay')
    # Inventory rollback separately: Inno overlays do not promise uninstall cleanup.
    record({'case':case.name,'stage':'previous_version_inventory','files':len(u.bundle_inventory(target)),
        'result':'OBSERVED','rollback_scope':'beta8 previous only, no compatibility promise for beta7'})
    # Repair back to approved current; old backup name must not collide on Mac.
    if not u.WINDOWS and (case/'previous-bundle.app').exists():
        (case/'previous-bundle.app').rename(case/'earlier-interrupted-bundle.app')
    exe=u.install(u.CURRENT,case,upgrade=True)
    verify(case,exe,SHA,before,'current_after_rollback_repair')

def main():
    assert u.SHA==SHA
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=u.SOURCE,text=True).strip()==SHA
    OUT.mkdir(parents=True,exist_ok=False)
    scenarios=[('early_copy',0),('middle_copy',100),('late_copy',800)] if u.WINDOWS else [('staging_copy',None),('inplace_copy',None),('promotion_gap',None)]
    for label,threshold in scenarios:
        u.SENTINELS.clear();u.SENTINELS.update(BASE_SENTINELS)
        case=OUT/label;case.mkdir();(case/'QUALIFICATION_ONLY').write_text('PUBLIC SYNTHETIC INTERRUPTED UPGRADE');(case/'data').mkdir();u.ACTIVE=case
        u.seed_modern(case);exe=u.install(u.MODERN,case)
        with u.Server(exe,case,u.MODERN_SHA,'1.0.0b8'):
            u.create_credits();u.check_credits()
        before=u.authority(case/'data');shutil.copytree(case/'data',case/'frozen-data')
        program=case/'Applications'/('AstroPilot' if u.WINDOWS else 'AstroPilot.app')
        frozen_program=u.bundle_inventory(program)
        if u.WINDOWS:windows_interrupt(case,threshold,frozen_program)
        elif label=='promotion_gap':exe=mac_promotion_gap(case)
        else:mac_copy_interrupt(case,label=='inplace_copy')
        assert u.authority(case/'data')==before,'Interruption changed data'
        if not (not u.WINDOWS and label=='promotion_gap'):exe=u.install(u.CURRENT,case,upgrade=True)
        verify(case,exe,SHA,before,'current_repaired')
        assert u.authority(case/'frozen-data')==before
        if label==scenarios[-1][0]:previous_restore(case,before)
        assert u.authority(case/'frozen-data')==before
    proof={'result':'PASS','product_sha':SHA,'previous_sha':u.MODERN_SHA,'os':platform.platform(),'rows':ROWS,
        'real_frozen_runtimes':True,'private_data_used':False,'authority_sources_unchanged':True,
        'new_credit_after_upgrade':False,'physical_power_loss':False,'installed_into_real_user_system':False,
        'mac_promotion_is_lab_procedure_not_product_updater':not u.WINDOWS}
    (OUT/'interrupted-qualification.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:v for k,v in proof.items() if k!='rows'}))

if __name__=='__main__':main()
