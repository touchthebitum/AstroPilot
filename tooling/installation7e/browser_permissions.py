"""Prepare only the kit's verified browser files for Windows sandbox access."""
import os
from pathlib import Path, PureWindowsPath
import stat
import subprocess
import sys


def browser_environment(parent, *, platform=sys.platform):
    env = {k: v for k, v in parent.items()
           if not k.startswith(('ASTROPILOT_', 'NIGHTMERIT_', 'FIELD_LAB_'))
           and k.upper() not in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'REQUESTS_CA_BUNDLE')}
    if parent.get('GITHUB_ACTIONS') == 'true':
        if platform == 'win32':
            # A synthetic USERPROFILE breaks Windows AppContainer startup in
            # Chrome. Restore only this OS identity directory in the browser
            # child; --user-data-dir still selects the isolated test profile.
            native = parent.get('BROWSER_NATIVE_USERPROFILE')
            if not native or not PureWindowsPath(native).is_absolute():
                raise RuntimeError('USERPROFILE Windows natif du runner absent pour le navigateur de test.')
            env['USERPROFILE'] = native
        elif platform == 'darwin' and parent.get('BROWSER_NATIVE_HOME'):
            env['HOME'] = parent['BROWSER_NATIVE_HOME']
    return env


def configure_browser(kit, *, windows=None, run=subprocess.run):
    if windows is None:
        windows = os.name == 'nt'
    if not windows:
        return {'status': 'not_required'}
    kit = Path(kit).resolve(strict=True)
    browser = kit / 'browser'
    # Never follow a junction or link while changing a tree's permissions.
    paths = [browser, *browser.rglob('*')]
    for path in paths:
        info = path.lstat()
        if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError('Lien ou jonction dans le navigateur de test : configuration refusée.')
        if not path.resolve().is_relative_to(browser.resolve()):
            raise RuntimeError('Navigateur extérieur au kit refusé.')
    setup = browser / 'setup.exe'
    if not setup.is_file() or not (browser / 'chrome.exe').is_file():
        raise RuntimeError('Configuration officielle du navigateur Windows absente.')
    # Chrome's directory-only installer mode configures sandbox ACLs. It does
    # not install Chrome, change its policy, or grant access to the test data.
    result = run([str(setup), '--configure-browser-in-directory=' + str(browser)],
                 cwd=browser, capture_output=True, timeout=60, check=False)
    # Chromium InstallStatus.CONFIGURE_APP_CONTAINER_SANDBOX_SUCCESS is 78,
    # not the generic installer success code 0.
    if result.returncode != 78:
        raise RuntimeError('Permissions du navigateur non confirmées (code ' + str(result.returncode) + '). Aucun contournement du bac à sable.')
    return {'status': 'configured', 'method': 'chrome_directory_setup', 'exit_code': result.returncode,
            'scope': 'kit/browser', 'sandbox_disabled': False}
