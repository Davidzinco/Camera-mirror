"""Blank the phone panel while keeping the camera's Android session awake."""
import shutil
import subprocess
import time

import backend as api

UNIT = 'camera-mirror-screen'
_screen_proc = None


def active():
    global _screen_proc
    if _screen_proc is not None:
        if _screen_proc.poll() is None:
            return True
        _screen_proc = None
    if shutil.which('systemctl'):
        try:
            result = subprocess.run(['systemctl', '--user', 'is-active', UNIT], capture_output=True, timeout=5)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    return False


def stop():
    global _screen_proc
    if _screen_proc is not None:
        try:
            _screen_proc.terminate()
            _screen_proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                _screen_proc.kill()
            except OSError:
                pass
        _screen_proc = None
    if shutil.which('systemctl') and active():
        try:
            api.run(['systemctl', '--user', 'stop', UNIT])
        except Exception:
            pass


def start(serial):
    if not api.active():
        raise RuntimeError('Mulai kamera terlebih dahulu.')
    stop()
    scrcpy = api.find_executable('scrcpy')
    cmd = [scrcpy, '--serial='+serial, '--no-video', '--no-audio',
           '--no-window', '--keep-active', '--turn-screen-off', '--no-clipboard-autosync']
    if shutil.which('systemd-run'):
        api.run(['systemd-run', '--user', '--unit='+UNIT, '--collect',
                 '--property=BindsTo=android-webcam.service', '--property=After=android-webcam.service',
                 '--', *cmd])
    else:
        global _screen_proc
        _screen_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    # Android 15+ exposes the same display-only power operation directly.
    try:
        sdk_str = api.run(['adb', '-s', serial, 'shell', 'getprop', 'ro.build.version.sdk'])
        if sdk_str.isdigit() and int(sdk_str) >= 35:
            api.run(['adb', '-s', serial, 'shell', 'cmd', 'display', 'power-off', '0'])
    except Exception:
        pass


def restore(serial):
    stop()
    try:
        sdk_str = api.run(['adb', '-s', serial, 'shell', 'getprop', 'ro.build.version.sdk'])
        if sdk_str.isdigit() and int(sdk_str) >= 35:
            api.run(['adb', '-s', serial, 'shell', 'cmd', 'display', 'power-reset', '0'])
    except Exception:
        pass
