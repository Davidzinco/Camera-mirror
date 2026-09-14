"""Camera lifecycle, independent from Tk and the discovery loop."""
import json
from pathlib import Path
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
    except (OSError, ValueError, KeyError, TypeError): return None


def rediscover():
    api.run(['systemctl', '--user', 'restart', 'wireplumber'])
    return 'Kamera dideteksi ulang. Buka kembali aplikasi tujuan bila perlu.'


def prepare():
    return api.run(['pkexec', '/usr/bin/python', str(ROOT/'setup_devices.py')], timeout=120)


def start(serial, facing, size, fps):
    api.camera_command(serial, facing, size, fps)
    if serial not in api.devices(): raise RuntimeError('HP belum terhubung. Sambungkan kabel atau pilih Hubungkan HP.')
    modes = api.camera_modes(serial)
    if fps not in api.supported_fps(modes, facing, size):
        raise RuntimeError(f'{fps} fps pada resolusi ini tidak tersedia di kamera HP. Pilih 30 fps atau resolusi lain.')
    if not Path('/dev/video10').exists(): prepare()
    if Path('/sys/class/video4linux/video10/name').read_text().strip() != 'Android Webcam':
        raise RuntimeError('Perangkat webcam dipakai perangkat lain. Buka Pengaturan lanjutan.')
    if int(api.run(['adb', '-s', serial, 'shell', 'getprop', 'ro.build.version.sdk'])) < 31:
        raise RuntimeError('Kamera HP membutuhkan Android 12 atau lebih baru.')
    if api.active(): api.stop()
    started = time.time()
    api.run(['systemd-run', '--user', '--unit='+api.UNIT, '--collect', '--',
             '/usr/bin/python', str(ROOT/'stream_service.py'), serial, facing, size, fps])
    try:
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            time.sleep(.2)
            if not api.active(): raise RuntimeError('Kamera tidak berhasil dimulai. Lihat rincian di Bantuan → Log kamera.')
            frame = runtime_dir()/'preview.jpg'
            try:
                if frame.stat().st_mtime > started: break
            except FileNotFoundError: pass
        else: raise RuntimeError('HP belum mengirim gambar. Periksa koneksi dan coba lagi.')
    except Exception:
        if api.active(): api.stop()
        raise
    rediscover()
    if preferences.load()['screen_off']:
        phone_screen.start(serial)
    return dict(serial=serial, facing=facing, size=size, fps=fps)
