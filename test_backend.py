import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import backend


class BackendTests(unittest.TestCase):
    def test_invalid_network_endpoints(self):
        for value in ("", "-x", "192.168.1.2", "192.168.1.2:0", "192.168.1.2:65536", "host;touch /tmp/file:5555"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                backend.endpoint(value)

    def test_endpoints(self):
        self.assertEqual(backend.endpoint(" 192.168.1.2:33333 "), "192.168.1.2:33333")
        self.assertEqual(backend.endpoint("[fd00::1]:33333"), "[fd00::1]:33333")

    @patch("backend.run", return_value="List of devices attached\nabc unauthorized\ndef offline\nghi device usb:1\n192.168.1.2:5555 device\n")
    def test_only_authorized_devices(self, run):
        self.assertEqual(backend.devices(), ["ghi", "192.168.1.2:5555"])

    @patch("backend.devices", return_value=[])
    @patch("backend.run", return_value="failed to connect")
    def test_adb_success_exit_with_failed_connection(self, run, devices):
        with self.assertRaises(RuntimeError):
            backend.connect("192.168.1.2:5555")

    @patch("backend.run", return_value="Successfully paired")
    def test_pairing_secret_not_in_arguments(self, run):
        backend.pair("192.168.1.2:33333", "123456")
        self.assertNotIn("123456", str(run.call_args.args))
        self.assertEqual(run.call_args.kwargs["input_text"], "123456\n")

    def test_reject_invalid_camera_before_start(self):
        with self.assertRaises(ValueError):
            backend.camera_command("--tcpip", "back", "1920x1080", "30")

    @patch("backend.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "Device unavailable"))
    def test_command_failure_preserves_diagnostic(self, run):
        with self.assertRaisesRegex(RuntimeError, "Device unavailable"):
            backend.run(["adb", "devices"])

    def test_install_hints_name_the_right_package(self):
        with patch("backend.sys.platform", "win32"):
            self.assertIn("Google.PlatformTools", backend.install_hint("adb"))
            self.assertIn("Google.PlatformTools", backend.install_hint("C:/x/adb.exe"))
            self.assertIn("Genymobile.scrcpy", backend.install_hint("scrcpy"))
            self.assertIn("Camera Mirror lagi", backend.install_hint("ffmpeg"))

    def test_winget_lookup_picks_the_executable_not_a_lookalike(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root/'Microsoft'/'WinGet'/'Packages'/'Genymobile.scrcpy_x'/'scrcpy-win64-v5.0.1'
            package.mkdir(parents=True)
            (package/'scrcpy.exe').write_bytes(b'')
            (package/'scrcpy-server').write_bytes(b'')
            env = {'LOCALAPPDATA': str(root), 'USERPROFILE': str(root),
                   'ProgramFiles': str(root/'programs'), 'PATH': ''}
            with patch.dict(os.environ, env), patch("backend.shutil.which", return_value=None), \
                    patch("backend.sys.platform", "win32"):
                found = backend.find_executable('scrcpy')
            self.assertEqual(Path(found).name, 'scrcpy.exe')


if __name__ == "__main__":
    unittest.main()
