"""FFmpeg preflight and explicit Windows install tests (no real winget calls)."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import dependencies


class FFmpegDependencyTests(unittest.TestCase):
    def test_both_tools_present(self):
        with patch('dependencies.shutil.which', return_value='some-tool.exe'):
            self.assertEqual(dependencies.missing_ffmpeg(), [])
            dependencies.require_ffmpeg()

    def test_missing_tools_actionable_and_not_installed_implicitly(self):
        with patch('dependencies.shutil.which', return_value=None):
            with patch('dependencies.subprocess.run', side_effect=AssertionError('unexpected installer')):
                with self.assertRaisesRegex(dependencies.MissingFFmpegError, 'winget install --id Gyan.FFmpeg --exact'):
                    dependencies.require_ffmpeg()

    def test_install_windows_only(self):
        with patch('dependencies.sys.platform', 'linux'):
            with self.assertRaisesRegex(RuntimeError, 'Windows-only'):
                dependencies.install_ffmpeg_windows()

    def test_install_requires_winget(self):
        with patch('dependencies.sys.platform', 'win32'), patch('dependencies.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'winget is unavailable'):
                dependencies.install_ffmpeg_windows()

    def test_install_executes_known_package_only_after_requested(self):
        completed = subprocess.CompletedProcess([], 0, stdout='Installed', stderr='')
        with patch('dependencies.sys.platform', 'win32'):
            with patch('dependencies.shutil.which', return_value='winget'):
                with patch('dependencies.subprocess.run', return_value=completed) as run:
                    result = dependencies.install_ffmpeg_windows()
        args, kwargs = run.call_args
        self.assertEqual(args[0][1:5], ['install', '--id', 'Gyan.FFmpeg', '--exact'])
        self.assertIn('--accept-package-agreements', args[0])
        self.assertIn('--accept-source-agreements', args[0])
        self.assertTrue(kwargs['capture_output'])
        self.assertIn('reopen Studio', result)

    def test_failed_install_preserves_error(self):
        completed = subprocess.CompletedProcess([], 1, stdout='', stderr='Package not found')
        with patch('dependencies.sys.platform', 'win32'):
            with patch('dependencies.shutil.which', return_value='winget'):
                with patch('dependencies.subprocess.run', return_value=completed):
                    with self.assertRaisesRegex(RuntimeError, 'Package not found'):
                        dependencies.install_ffmpeg_windows()


if __name__ == '__main__':
    unittest.main()
