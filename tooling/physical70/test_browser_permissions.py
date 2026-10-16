"""Regression coverage for the kit's browser-only sandbox configuration."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from browser_permissions import configure_browser


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
