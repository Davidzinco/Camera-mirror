"""Installer tests use temporary folders and never install OS packages or shortcuts."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import bootstrap


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)/'Camera Mirror'
        self.root.mkdir()
        (self.root/'requirements-desktop.txt').write_text('example-package==1\n')
        self.python = bootstrap.environment_python(self.root)
        self.python.parent.mkdir(parents=True)
        self.python.touch()

    def test_platform_interpreter_paths(self):
        self.assertEqual(bootstrap.environment_python(self.root, True),
                         self.root/'.venv'/'Scripts'/'python.exe')
        self.assertEqual(bootstrap.environment_python(self.root, False),
                         self.root/'.venv'/'bin'/'python')

    @patch('scripts.bootstrap.probe')
    @patch('scripts.bootstrap.run')
    def test_successful_install_is_reused_and_requirement_change_installs_again(self, run, probe):
        bootstrap.prepare(self.root)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0],
                         [self.python, '-m', 'ensurepip', '--upgrade'])
        command = run.call_args.args[0]
        self.assertEqual(command[0], self.python)
        self.assertEqual(command[1:4], ['-m', 'pip', 'install'])
        bootstrap.prepare(self.root)
        self.assertEqual(run.call_count, 2)
        (self.root/'requirements-desktop.txt').write_text('example-package==2\n')
        bootstrap.prepare(self.root)
        self.assertEqual(run.call_count, 4)
        self.assertEqual(probe.call_count, 3)

    @patch('scripts.bootstrap.probe', side_effect=bootstrap.SetupError('Qt missing'))
    @patch('scripts.bootstrap.run')
    def test_failed_dependency_check_never_marks_install_complete(self, run, probe):
        with self.assertRaises(bootstrap.SetupError):
            bootstrap.prepare(self.root)
        self.assertFalse((self.root/'.venv'/'.camera-mirror-ready').exists())

    @patch('scripts.bootstrap.run', side_effect=subprocess.CalledProcessError(1, ['pip']))
    def test_failed_download_can_be_retried(self, run):
        with self.assertRaises(subprocess.CalledProcessError):
            bootstrap.prepare(self.root)
        self.assertFalse((self.root/'.venv'/'.camera-mirror-ready').exists())
        with patch('scripts.bootstrap.run'), patch('scripts.bootstrap.probe'):
            bootstrap.prepare(self.root)
        self.assertTrue((self.root/'.venv'/'.camera-mirror-ready').exists())

    def test_linux_shortcut_handles_spaces_and_exec_metacharacters(self):
        with patch.dict(os.environ, XDG_DATA_HOME=self.folder.name):
            entry = bootstrap.linux_shortcut(self.root, self.python)
        text = entry.read_text()
        self.assertIn('Name=Camera Mirror', text)
        self.assertIn('"'+str(self.python)+'"', text)
        self.assertIn('"--launch"', text)
        # These values must not become field codes or command substitutions.
        quoted = bootstrap.desktop_quote('/tmp/100%/$cash/`literal`/"quoted"/path\\tail')
        self.assertIn('100%%', quoted)
        self.assertIn('\\\\$', quoted)
        self.assertIn('\\\\`', quoted)
        self.assertIn('\\\\"', quoted)
        self.assertIn('\\\\\\\\', quoted)
        with self.assertRaises(bootstrap.SetupError):
            bootstrap.desktop_quote('/tmp/new\nline')

    @patch('scripts.bootstrap.subprocess.run')
    def test_windows_shortcut_passes_path_as_data(self, run):
        root = Path('C:/Camera Mirror $example')
        bootstrap.windows_shortcut(root)
        args = run.call_args.args[0]
        self.assertNotIn(str(root), args[-1])
        self.assertEqual(run.call_args.kwargs['env']['CAMERA_MIRROR_INSTALL_ROOT'], str(root))
