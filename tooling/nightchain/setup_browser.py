from pathlib import Path
import os,sys,json,hashlib,urllib.request,zipfile,subprocess
root=Path(os.environ['RUNNER_TEMP'])/'night-chain-browser-tool';root.mkdir()
version='155.0.8059.79';platform='win64' if os.name=='nt' else 'mac-arm64'
url=f'https://storage.googleapis.com/chrome-for-testing-public/{version}/{platform}/chrome-{platform}.zip'
a=root/'chrome.zip';urllib.request.urlretrieve(url,a)
with zipfile.ZipFile(a) as z:
 assert z.testzip() is None
 assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in z.namelist())
 if os.name=='nt':z.extractall(root)
if os.name!='nt':subprocess.run(['/usr/bin/ditto','-x','-k',str(a),str(root)],check=True)
exe=root/(f'chrome-{platform}/chrome.exe' if os.name=='nt' else f'chrome-{platform}/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')
assert exe.is_file(),exe
(root/'binary-path.txt').write_text(str(exe))
(root/'provenance.json').write_text(json.dumps({'version':version,'url':url,'archive_sha256':hashlib.sha256(a.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'browser_profile':'new isolated per case'},indent=2)+'\n')
print('Official Chrome for Testing',version,platform)
