"""Regression coverage for the kit's browser-only sandbox configuration."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from browser_permissions import configure_browser, browser_environment


class BrowserPermissions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.kit = self.root / 'kit with spaces'
        self.browser = self.kit / 'browser'
        self.browser.mkdir(parents=True)
        for name in ('chrome.exe', 'setup.exe'):
            (self.browser / name).write_bytes(b'fixture')

    def tearDown(self):
        self.tmp.cleanup()

    def test_windows_ci_restores_only_browser_os_identity_not_test_storage(self):
        parent = {'GITHUB_ACTIONS': 'true', 'USERPROFILE': r'D:\isolated\USERPROFILE',
                  'BROWSER_NATIVE_USERPROFILE': r'C:\Users\runneradmin',
                  'APPDATA': r'D:\isolated\APPDATA', 'LOCALAPPDATA': r'D:\isolated\LOCALAPPDATA',
                  'HOME': r'D:\isolated\HOME', 'TEMP': r'D:\isolated\TEMP',
                  'ASTROPILOT_DATA_DIR': 'forbidden', 'HTTPS_PROXY': 'forbidden'}
        before = parent.copy()
        child = browser_environment(parent, platform='win32')
        self.assertEqual(parent, before)
        self.assertEqual(child['USERPROFILE'], parent['BROWSER_NATIVE_USERPROFILE'])
        for key in ('APPDATA', 'LOCALAPPDATA', 'HOME', 'TEMP'):
            self.assertEqual(child[key], parent[key])
        self.assertNotIn('ASTROPILOT_DATA_DIR', child)
        self.assertNotIn('HTTPS_PROXY', child)

    def test_windows_ci_requires_explicit_absolute_native_identity(self):
        for value in (None, '', 'relative'):
            parent = {'GITHUB_ACTIONS': 'true', 'USERPROFILE': 'synthetic'}
            if value is not None:
                parent['BROWSER_NATIVE_USERPROFILE'] = value
            with self.assertRaisesRegex(RuntimeError, 'natif'):
                browser_environment(parent, platform='win32')

    def test_physical_windows_keeps_its_existing_os_identity(self):
        parent = {'USERPROFILE': r'C:\Users\physical', 'BROWSER_NATIVE_USERPROFILE': 'unused'}
        self.assertEqual(browser_environment(parent, platform='win32'), parent)

    def test_macos_keeps_existing_native_home_rule(self):
        parent = {'GITHUB_ACTIONS': 'true', 'HOME': '/isolated', 'BROWSER_NATIVE_HOME': '/Users/runner'}
        self.assertEqual(browser_environment(parent, platform='darwin')['HOME'], '/Users/runner')
        self.assertEqual(parent['HOME'], '/isolated')

    def test_macos_does_not_run_or_inspect_windows_setup(self):
        run = Mock()
        self.assertEqual(configure_browser(self.root / 'absent', windows=False, run=run)['status'], 'not_required')
        run.assert_not_called()

    def test_only_official_directory_mode_without_shell_or_sandbox_bypass(self):
        run = Mock(return_value=Mock(returncode=78))
        self.assertFalse(configure_browser(self.kit, windows=True, run=run)['sandbox_disabled'])
        args, kwargs = run.call_args
        self.assertEqual(args[0], [str(self.browser / 'setup.exe'), '--configure-browser-in-directory=' + str(self.browser)])
        self.assertEqual(kwargs['cwd'], self.browser)
        self.assertNotIn('shell', kwargs)

    def test_missing_setup_does_not_fall_back_to_unsandboxed_browser(self):
        (self.browser / 'setup.exe').unlink()
        run = Mock()
        with self.assertRaisesRegex(RuntimeError, 'absente'):
            configure_browser(self.kit, windows=True, run=run)
        run.assert_not_called()

    def test_setup_failure_stops_launch(self):
        with self.assertRaisesRegex(RuntimeError, 'code 5'):
            configure_browser(self.kit, windows=True, run=Mock(return_value=Mock(returncode=5)))

    def test_generic_installer_success_is_not_sandbox_confirmation(self):
        with self.assertRaisesRegex(RuntimeError, 'code 0'):
            configure_browser(self.kit, windows=True, run=Mock(return_value=Mock(returncode=0)))

    def test_controller_does_not_spawn_chrome_when_configuration_fails(self):
        import controller
        from unittest.mock import patch
        case = self.kit / 'case'
        case.mkdir()
        (self.kit / 'kit.json').write_text('{"browser":"browser/chrome.exe"}')
        owner = Mock(kit=self.kit, case=case)
        with patch.object(controller, 'configure_browser', side_effect=RuntimeError('permissions refusées')), patch.object(controller, 'spawn') as spawn:
            with self.assertRaisesRegex(RuntimeError, 'permissions refusées'):
                controller.browser(owner, 'http://127.0.0.1:1')
            spawn.assert_not_called()
        import json
        self.assertEqual(json.loads((case / 'browser-permissions.json').read_text())['status'], 'failed')

    def test_setup_timeout_propagates_instead_of_bypassing_sandbox(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            configure_browser(self.kit, windows=True, run=Mock(side_effect=subprocess.TimeoutExpired('setup', 60)))

    def test_external_link_or_junction_is_rejected_before_setup(self):
        outside = self.root / 'outside'
        outside.mkdir()
        link = self.browser / 'external'
        if os.name == 'nt':
            subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
        else:
            link.symlink_to(outside, target_is_directory=True)
        run = Mock()
        try:
            with self.assertRaisesRegex(RuntimeError, 'Lien ou jonction'):
                configure_browser(self.kit, windows=True, run=run)
            run.assert_not_called()
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()


if __name__ == '__main__':
    unittest.main()
