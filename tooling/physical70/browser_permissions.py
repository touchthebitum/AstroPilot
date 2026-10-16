"""Prepare only the kit's verified browser files for Windows sandbox access."""
import os
from pathlib import Path
import stat
import subprocess


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
