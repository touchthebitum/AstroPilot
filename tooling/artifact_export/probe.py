"""Public sentinels only. An intentional failing test stays a failing job."""
from pathlib import Path
import os,sys,json,hashlib,unittest,io,base64,zipfile,xml.etree.ElementTree as ET
root=Path(os.environ['RUNNER_TEMP'])/'export-probe';root.mkdir();mode=os.environ['PROBE_MODE'];label=os.environ['PROBE_OS'];sha=os.environ['CANDIDATE_SHA'];assert len(sha)==40
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME'):
 p=root/'environment'/key;p.mkdir(parents=True);os.environ[key]=str(p)
source=Path('candidate');pin='actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'
assert (source/'.github/workflows/tests.yml').read_text(encoding='utf-8').count(pin)==2
assert (source/'.github/workflows/beta8-windows-manual.yml').read_text(encoding='utf-8').count(pin)==1
proof=root/'night-chain-proof';proof.mkdir();(proof/'ha').mkdir();candidate=root/'dist/beta8-artifacts';candidate.mkdir(parents=True);meta=root/'metadata';meta.mkdir()
# Deliberate out-of-scope private-looking sentinels; never real data.
private=root/'not-for-export';private.mkdir();(private/'user_profile.json').write_text('PUBLIC EXCLUDED SENTINEL',encoding='utf-8');(private/'cursor.key').write_bytes(b'PUBLIC EXCLUDED KEY SENTINEL')
(proof/'.env').write_text('PUBLIC_HIDDEN_SENTINEL=must_not_upload',encoding='utf-8');(proof/'.hidden').mkdir();(proof/'.hidden/secret.txt').write_text('PUBLIC HIDDEN DIRECTORY SENTINEL',encoding='utf-8')
class PublicTest(unittest.TestCase):
 def test_export_path(self):self.assertEqual(mode,'success','Intentional public failure: verify export after test failure')
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PublicTest))
log=stream.getvalue();print(log,end='')
suite=ET.Element('testsuite',tests='1',failures=str(len(result.failures)),errors=str(len(result.errors)),skipped='0');case=ET.SubElement(suite,'testcase',name='public_export_sentinel',classname='public_isolated_export')
for _,trace in result.failures:ET.SubElement(case,'failure',message='intentional public failure').text=trace
xml=root/'profile-recovery.xml';ET.ElementTree(suite).write(xml,encoding='utf-8',xml_declaration=True)
(proof/'ha/browser.log').write_text(log+'\nCaméra Hα/OIII — journaux publics\n',encoding='utf-8');(proof/'ha/ui.txt').write_text('PUBLIC FIXTURE — Hα/OIII Caméra, pas une capture produit\n',encoding='utf-8')
(proof/'ha/ui.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
(proof/'ha/browser-result.json').write_text(json.dumps({'fixture_only':True,'actual_test_success':result.wasSuccessful(),'source_sha':sha}),encoding='utf-8')
(proof/'provenance.json').write_text(json.dumps({'source_sha':sha,'fixture_only':True,'os':sys.platform,'mode':mode}),encoding='utf-8')
(candidate/'PUBLIC-FIXTURE.txt').write_text('Artifact export contract only; NOT A DISTRIBUTABLE APPLICATION',encoding='utf-8')
with zipfile.ZipFile(candidate/'portable-fixture.zip','w') as z:z.writestr('PUBLIC-FIXTURE.txt','Public fixture, no executable or user data')
def record(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
(candidate/'SHA256SUMS.txt').write_text(''.join(record(p)['sha256']+'  '+p.name+'\n' for p in sorted(candidate.iterdir())),encoding='utf-8')
expected={'profile-recovery-'+label+'-'+mode:{'days':14,'files':{xml.name:record(xml)}},'night-confirmation-'+label+'-'+mode:{'days':14,'files':{p.relative_to(proof).as_posix():record(p) for p in proof.rglob('*') if p.is_file() and not any(x.startswith('.') for x in p.relative_to(proof).parts)}}}
if result.wasSuccessful():expected['candidate-fixture-'+label+'-'+mode]={'days':30,'files':{p.name:record(p) for p in candidate.iterdir()}}
(meta/'manifest.json').write_text(json.dumps({'source_sha':sha,'mode':mode,'os':label,'expected_test_success':result.wasSuccessful(),'expected_artifacts':expected,'private_sentinels_real_data':False,'upload_action_pin':pin,'no_signature_or_submission':True},indent=2),encoding='utf-8')
sys.exit(0 if result.wasSuccessful() else 1)
