import sys
import subprocess
import unittest

from camera_link.frames import LatestFrame
from camera_link.pairing import Invitation, PairingGate


class PairingTests(unittest.TestCase):
    def test_invitation_roundtrip_and_reject_untrusted_shapes(self):
        invitation = Invitation('192.168.1.20', 8765, 'a'*64, 'B'*43)
        self.assertEqual(Invitation.decode(invitation.encode()), invitation)
        for value in ('', 'https://example.com', 'cm1:%%%%', 'cm1:e30', 'cm1:'+'a'*2100):
            with self.subTest(value=value[:20]), self.assertRaises(ValueError):
                Invitation.decode(value)

    def test_bad_addresses_and_identity(self):
        for host in ('0.0.0.0', '224.0.0.1', 'example.com', '127.0.0.1/path'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                Invitation(host, 8765, 'a'*64, 'B'*43)
        with self.assertRaises(ValueError):
            Invitation('127.0.0.1', True, 'a'*64, 'B'*43)
        with self.assertRaises(ValueError):
            Invitation('127.0.0.1', 8765, 'invalid', 'B'*43)

    def test_token_is_single_use_and_expired_tokens_cannot_claim(self):
        now = [10]
        gate = PairingGate(ttl=5, clock=lambda: now[0])
        self.assertTrue(gate.claim(gate.token))
        self.assertFalse(gate.claim(gate.token))
        expired = PairingGate(ttl=5, clock=lambda: now[0])
        now[0] = 15
        self.assertFalse(expired.claim(expired.token))

    def test_failed_attempt_limit_and_unicode_input(self):
        gate = PairingGate(attempts=2)
        self.assertFalse(gate.claim('salah'))
        self.assertFalse(gate.claim('saláh'))
        self.assertFalse(gate.claim(gate.token))
        self.assertFalse(gate.used)


class HandoffTests(unittest.TestCase):
    def test_frame_backlog_is_replaced_and_clear_removes_stale_frame(self):
        frames = LatestFrame()
        for value in range(1000):
            frames.put(value)
        value, sequence, stamp = frames.get()
        self.assertEqual((value, sequence), (999, 1000))
        self.assertGreater(stamp, 0)
        frames.clear()
        self.assertIsNone(frames.get()[0])
        self.assertEqual(frames.get()[2], 0)

    def test_new_entry_point_does_not_import_linux_backend(self):
        result = subprocess.run([sys.executable, '-c',
            "import sys, desktop_camera; assert callable(desktop_camera.main); "
            "assert 'camera_link.ui' not in sys.modules; assert 'fcntl' not in sys.modules"],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
