"""Sandbox setup regressions; no downloads, native permission changes or product imports."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from setup_browser import configure_windows_sandbox


class SandboxSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / 'browser with spaces'
        self.folder.mkdir()
        (self.folder / 'setup.exe').write_bytes(b'fixture')
        self.binary = self.folder / 'chrome.exe'

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_explicit_directory_sandbox_success_is_accepted(self):
        run = Mock(return_value=Mock(returncode=78))
        self.assertEqual(configure_windows_sandbox(self.binary, run=run), 78)
        args, kwargs = run.call_args
        self.assertEqual(args[0], [str(self.folder / 'setup.exe'), '--configure-browser-in-directory=' + str(self.folder)])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(kwargs['cwd'], self.folder)

    def test_missing_setup_prevents_launch(self):
        (self.folder / 'setup.exe').unlink()
        run = Mock()
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            configure_windows_sandbox(self.binary, run=run)
        run.assert_not_called()

    def test_failure_or_generic_install_success_is_not_accepted(self):
        for code in (0, 5, 79):
            with self.assertRaisesRegex(RuntimeError, str(code)):
                configure_windows_sandbox(self.binary, run=Mock(return_value=Mock(returncode=code)))

    def test_timeout_does_not_continue_without_sandbox(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            configure_windows_sandbox(self.binary, run=Mock(side_effect=subprocess.TimeoutExpired('setup', 60)))


if __name__ == '__main__':
    unittest.main()
