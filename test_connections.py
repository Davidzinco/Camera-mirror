import os
import tempfile
import unittest
from unittest.mock import patch

import backend
import preferences
import wireless


CAMERAS = '''
    --camera-id=0    (back, 4080x3060, fps={15, 20, 24, 30}, zoom-range=[1, 8])
        - 1920x1080
        - 1280x720
      High speed capture (--camera-high-speed):
        - 1280x720 (fps={120, 240})
    --camera-id=1    (front, 4000x3000, fps={15, 30, 60})
        - 1920x1080
'''


class CameraModeTests(unittest.TestCase):
    def test_high_speed_modes_do_not_claim_native_sixty_fps(self):
        modes = backend.parse_camera_modes(CAMERAS)
        self.assertEqual(backend.supported_fps(modes, 'back', '1280x720'), ['15', '30'])
        self.assertEqual(backend.supported_fps(modes, 'front', '1920x1080'), ['15', '30', '60'])
        self.assertEqual(backend.supported_fps(modes, 'front', '1280x720'), [])


class WirelessTests(unittest.TestCase):
    def test_discovery_uses_resolved_services_only(self):
        result = wireless.parse_services(
            '+;wlan0;IPv4;adb-PHONE-a;_adb-tls-connect._tcp;local\n'
            '=;wlan0;IPv4;adb-PHONE-a;_adb-tls-connect._tcp;local;phone.local;192.168.1.20;38000;\n'
            '=;wlan0;IPv4;printer;_ipp._tcp;local;printer.local;192.168.1.30;631;\n',
            '_adb-tls-connect._tcp')
        self.assertEqual(result, [dict(name='adb-PHONE-a', address='192.168.1.20:38000')])

    @patch('wireless.identity', return_value='DIFFERENT-PHONE')
    @patch('wireless.api.run')
    def test_reassigned_ip_does_not_select_another_phone(self, run, identity):
        with self.assertRaisesRegex(RuntimeError, 'bukan HP'):
            wireless.connect_checked('192.168.1.20:5555', 'MY-PHONE')

    @patch('wireless.preferences.load', return_value=dict(auto_connect=False, wireless=[]))
    @patch('wireless.connect_checked')
    def test_auto_connect_can_be_disabled(self, connect, load):
        self.assertIsNone(wireless.reconnect([]))
        connect.assert_not_called()

    @patch('wireless.preferences.load', return_value=dict(auto_connect=True, wireless=[
        dict(serial='MY-PHONE', address='192.168.1.20:5555', name='Phone')]))
    @patch('wireless.connect_checked', return_value='MY-PHONE')
    def test_reconnect_checks_saved_hardware_identity(self, connect, load):
        self.assertEqual(wireless.reconnect([]), '192.168.1.20:5555')
        connect.assert_called_once_with('192.168.1.20:5555', 'MY-PHONE')

    def test_preferences_preserve_settings_when_address_changes(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, XDG_CONFIG_HOME=directory):
            preferences.save(facing='front', mode='wifi')
            preferences.remember('MY-PHONE', '192.168.1.20:5555', 'Phone')
            preferences.remember('MY-PHONE', '192.168.1.21:5555', 'Phone')
            state = preferences.load()
            self.assertEqual(state['facing'], 'front')
            self.assertEqual(len(state['wireless']), 1)
            self.assertEqual(state['wireless'][0]['address'], '192.168.1.21:5555')
            self.assertEqual(preferences.path().stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
