"""Fetch the official, pinned browser into a disposable tools directory."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

VERSION = '155.0.8059.79'
ARCHIVES = {
    ('win32', 'AMD64'): ('win64', '4966d9df2c8ed9be606ff0fc8877b2e800def164fbad63fed6a1d93222ad9dbf'),
    ('darwin', 'arm64'): ('mac-arm64', 'e141a7cbf948780bb7d381860bd5a7944c6736f79b9918b9826fccb199d28ea4'),
}

def install():
    target, expected = ARCHIVES[(sys.platform, platform.machine())]
    root = Path(tempfile.mkdtemp(prefix='night-chain-browser-', dir=os.environ.get('RUNNER_TEMP')))
    url = f'https://storage.googleapis.com/chrome-for-testing-public/{VERSION}/{target}/chrome-{target}.zip'
    archive = root / 'chrome.zip'
    deadline = time.monotonic() + 120
    with urllib.request.urlopen(url, timeout=30) as source, archive.open('wb') as destination:
        size = 0
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            assert size <= 512 * 1024 * 1024 and time.monotonic() < deadline, 'Browser download budget exceeded'
            destination.write(chunk)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert digest == expected, 'Browser archive digest mismatch'
    with zipfile.ZipFile(archive) as files:
        assert files.testzip() is None
        assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in files.namelist())
        if os.name == 'nt':
            files.extractall(root)
    if os.name != 'nt':
        subprocess.run(['/usr/bin/ditto', '-x', '-k', str(archive), str(root)], check=True, timeout=120)
    binary = root / f'chrome-{target}' / ('chrome.exe' if os.name == 'nt' else
                'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')
    assert binary.is_file()
    return binary, {
        'version': VERSION, 'platform': target, 'url': url, 'archive_sha256': digest,
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
    }
