"""Regressions from the native Windows private-kit backup trial."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / 'scripts/private_beta_windows/controller.ps1'


def browser_command():
    text = CONTROLLER.read_text(encoding='utf-8')
    return re.search(r"EnvironmentVariables\['BROWSER'\] = '([^']+)'", text).group(1)


def test_noop_browser_command_survives_python_webbrowser_parsing():
    # The previous unquoted Windows command lost its backslashes through shlex.
    import webbrowser
    args = shlex.split(browser_command())
    browser = webbrowser.GenericBrowser(args)
    assert browser.name == r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    assert browser.args == ['-NoProfile', '-NonInteractive', '-Command', 'exit 0 # %s']


@pytest.mark.skipif(os.name != 'nt', reason='Requires native Windows PowerShell')
def test_native_noop_returns_success_without_default_browser_fallback():
    import webbrowser
    browser = webbrowser.GenericBrowser(shlex.split(browser_command()))
    assert browser.open('http://127.0.0.1:8000/') is True


@pytest.mark.skipif(os.name != 'nt', reason='Requires native Windows PowerShell')
@pytest.mark.parametrize('transfer', [False, True])
def test_native_browser_configuration_keeps_downloads_outside_temporary_profile(tmp_path, transfer):
    text = CONTROLLER.read_text(encoding='utf-8')
    # Exercise the actual rendered browser configuration without starting a GUI.
    block = text.split(" $run.stage='launch_browser'; Write-Run", 1)[1].split(
        ' $script:browserProcess = Start-Process', 1)[0]
    assert shutil.which('powershell.exe')
    root = str(tmp_path / 'kit with spaces').replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
$browserInstallRoot = '{root}\\Program Files\\NightMeritPrivateBrowser'
$browserProfilesRoot = '{root}\\Local AppData\\NightMeritPrivateBrowserProfiles'
$results = '{root}\\RESULTATS'
$run = [ordered]@{{}}
$dataTransfer = ${str(transfer).lower()}
{block}
$preferencesValue = $null
if ($dataTransfer) {{ $preferencesValue = Get-Content -LiteralPath $preferences -Raw | ConvertFrom-Json }}
@{{chrome=$chrome;profile=$browserProfile;arguments=$arguments;preferences=$preferencesValue;results=$results}} | ConvertTo-Json -Depth 6 -Compress
"""
    # Match the launcher's fixed in-memory invocation. Do not change host
    # execution policy just to run generated test code from a temporary file.
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            check=True, capture_output=True, text=True, timeout=30)
    value = json.loads(result.stdout)
    assert value['chrome'].endswith(r'Program Files\NightMeritPrivateBrowser\chrome.exe')
    assert value['profile'].endswith('donnees' if transfer else 'normal')
    assert '--user-data-dir="' + value['profile'] + '"' in value['arguments']
    assert not any('no-sandbox' in arg for arg in value['arguments'])
    if transfer:
        expected = value['results'] + r'\SAUVEGARDES'
        assert value['preferences']['download'] == {'default_directory': expected, 'prompt_for_download': False}
        assert Path(expected).is_dir()
    else:
        assert value['preferences'] is None
