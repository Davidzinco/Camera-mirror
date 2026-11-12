"""Camera lifecycle, independent from Tk and the discovery loop."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import backend as api
import preferences
import phone_screen
from stream_service import runtime_dir

ROOT = Path(__file__).resolve().parent


def current():
    try:
        data = json.loads((runtime_dir()/'settings.json').read_text())
        api.camera_command(data['serial'], data['facing'], data['size'], data['fps'])
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def rediscover():
    if sys.platform == 'linux' and shutil.which('systemctl') and shutil.which('wireplumber'):
        try:
            api.run(['systemctl', '--user', 'restart', 'wireplumber'])
        except Exception:
            pass
        return 'Kamera dideteksi ulang. Buka kembali aplikasi tujuan bila perlu.'
    return 'Kamera aktif.'


def prepare():
    if sys.platform == 'win32':
        return 'Windows siap menggunakan OBS Virtual Camera.'
    if shutil.which('pkexec'):
        return api.run(['pkexec', sys.executable, str(ROOT/'setup_devices.py')], timeout=120)
    return 'Penyiapan perangkat selesai.'


def start(serial, facing, size, fps):
    api.camera_command(serial, facing, size, fps)
    if serial not in api.devices():
        raise RuntimeError('HP belum terhubung. Sambungkan kabel atau pilih Hubungkan HP.')
    modes = api.camera_modes(serial)
    if fps not in api.supported_fps(modes, facing, size):
        raise RuntimeError(f'{fps} fps pada resolusi ini tidak tersedia di kamera HP. Pilih 30 fps atau resolusi lain.')
    if sys.platform == 'linux':
        if not Path('/dev/video10').exists():
            prepare()
        if Path('/sys/class/video4linux/video10/name').exists():
            if Path('/sys/class/video4linux/video10/name').read_text().strip() != 'Android Webcam':
                raise RuntimeError('Perangkat webcam dipakai perangkat lain. Buka Pengaturan lanjutan.')
    sdk_str = api.run(['adb', '-s', serial, 'shell', 'getprop', 'ro.build.version.sdk'])
    if sdk_str.isdigit() and int(sdk_str) < 31:
        raise RuntimeError('Kamera HP membutuhkan Android 12 atau lebih baru.')
    if api.active():
        api.stop()
    started = time.time()

    if sys.platform == 'linux' and shutil.which('systemd-run'):
        api.run(['systemd-run', '--user', '--unit='+api.UNIT, '--collect', '--',
                 sys.executable, str(ROOT/'stream_service.py'), serial, facing, size, fps])
    else:
        proc = subprocess.Popen([sys.executable, str(ROOT/'stream_service.py'), serial, facing, size, fps],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        api.set_active_process(proc)

    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            time.sleep(.25)
            if not api.active():
                raise RuntimeError('Kamera tidak berhasil dimulai. Lihat rincian di Bantuan → Log kamera.')
            frame = runtime_dir()/'preview.jpg'
            try:
                if frame.stat().st_mtime >= started or api.active():
                    break
            except FileNotFoundError:
                pass
        else:
            if not api.active():
                raise RuntimeError('HP belum mengirim gambar. Periksa koneksi dan coba lagi.')
    except Exception:
        if api.active():
            api.stop()
        raise

    rediscover()
    if preferences.load()['screen_off']:
        try:
            phone_screen.start(serial)
        except Exception:
            pass
    return dict(serial=serial, facing=facing, size=size, fps=fps)
