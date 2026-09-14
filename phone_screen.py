"""Blank the phone panel while keeping the camera's Android session awake."""
import subprocess
import time

import backend as api

UNIT = 'camera-mirror-screen'


def active():
    result = subprocess.run(['systemctl', '--user', 'is-active', UNIT], capture_output=True, timeout=5)
    return result.returncode == 0


def stop():
    if active(): api.run(['systemctl', '--user', 'stop', UNIT])


def start(serial):
    if not api.active(): raise RuntimeError('Mulai kamera terlebih dahulu.')
    stop()
    api.run(['systemd-run', '--user', '--unit='+UNIT, '--collect',
             '--property=BindsTo=android-webcam.service', '--property=After=android-webcam.service',
             '--', '/usr/bin/scrcpy', '--serial='+serial, '--no-video', '--no-audio',
             '--no-window', '--keep-active', '--turn-screen-off', '--no-clipboard-autosync'])
    time.sleep(1.5)
    if not active(): raise RuntimeError('Layar belum bisa dipadamkan. Lihat Log kamera.')
    # Android 15+ exposes the same display-only power operation directly.
    sdk = int(api.run(['adb', '-s', serial, 'shell', 'getprop', 'ro.build.version.sdk']))
    if sdk >= 35:
        api.run(['adb', '-s', serial, 'shell', 'cmd', 'display', 'power-off', '0'])


def restore(serial):
    stop()
    sdk = int(api.run(['adb', '-s', serial, 'shell', 'getprop', 'ro.build.version.sdk']))
    if sdk >= 35:
        api.run(['adb', '-s', serial, 'shell', 'cmd', 'display', 'power-reset', '0'])
