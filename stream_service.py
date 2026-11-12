"""Keep the webcam and a private, in-memory preview alive independently of the GUI."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:
    fcntl = None

import backend


def runtime_dir():
    if sys.platform == 'win32':
        folder = Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData'/'Local')) / 'CameraMirror' / 'runtime'
    else:
        uid = os.getuid() if hasattr(os, 'getuid') else 1000
        folder = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{uid}')) / 'camera-mirror'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder


def main():
    if len(sys.argv) < 5:
        print("Usage: stream_service.py <serial> <facing> <size> <fps>", file=sys.stderr)
        return 1
    serial, facing, size, fps = sys.argv[1:5]
    folder = runtime_dir()
    lock_file = folder / 'stream.lock'
    lock = lock_file.open('w')
    if fcntl:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            pass

    fifo, frame = folder / 'stream.mkv', folder / 'preview.jpg'
    (folder / 'settings.json').write_text(json.dumps(dict(serial=serial, facing=facing, size=size, fps=fps)))
    stopped = False

    def shutdown(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, shutdown)

    children = []
    try:
        command = backend.camera_command(serial, facing, size, fps, preview=True)
        ffmpeg_bin = shutil.which('ffmpeg') or '/usr/bin/ffmpeg'

        if hasattr(os, 'mkfifo') and shutil.which(ffmpeg_bin):
            fifo.unlink(missing_ok=True)
            frame.unlink(missing_ok=True)
            os.mkfifo(fifo, 0o600)
            decoder = subprocess.Popen([
                ffmpeg_bin, '-hide_banner', '-loglevel', 'error', '-y',
                '-threads', '1', '-flags', 'low_delay', '-filter_threads', '1',
                '-analyzeduration', '0', '-probesize', '32768', '-i', str(fifo),
                '-an', '-vf', 'scale=960:-2:flags=fast_bilinear', '-fps_mode', 'passthrough',
                '-threads', '1', '-q:v', '4',
                '-update', '1', '-atomic_writing', '1', str(frame)
            ], stdin=subprocess.DEVNULL)
            children.append(decoder)
            camera = subprocess.Popen(command + ['--record=' + str(fifo), '--record-format=mkv'])
            children.append(camera)
            while not stopped and camera.poll() is None and decoder.poll() is None:
                time.sleep(.1)
            if not stopped:
                return camera.returncode or decoder.returncode or 1
        else:
            # Cross-platform / Windows direct scrcpy process
            frame.write_bytes(b'')  # Touch preview file to indicate started
            camera = subprocess.Popen(command)
            children.append(camera)
            while not stopped and camera.poll() is None:
                time.sleep(.2)
            if not stopped:
                return camera.returncode or 0
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for path in (fifo, frame, folder / 'preview.jpg.tmp', folder / 'settings.json', lock_file):
            path.unlink(missing_ok=True)
        lock.close()


if __name__ == '__main__':
    sys.exit(main())
