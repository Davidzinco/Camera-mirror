"""Keep the webcam and a private, in-memory preview alive independently of the GUI."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import backend


def runtime_dir():
    return Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'camera-mirror'


def main():
    serial, facing, size, fps = sys.argv[1:]
    command = backend.camera_command(serial, facing, size, fps)
    folder = runtime_dir()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (folder / 'stream.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fifo, frame = folder / 'stream.mkv', folder / 'preview.jpg'
    fifo.unlink(missing_ok=True)
    frame.unlink(missing_ok=True)
    os.mkfifo(fifo, 0o600)
    (folder / 'settings.json').write_text(json.dumps(dict(serial=serial, facing=facing, size=size, fps=fps)))
    stopped = False
    def shutdown(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    children = []
    try:
        decoder = subprocess.Popen([
            '/usr/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
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
        for path in (fifo, frame, folder / 'preview.jpg.tmp', folder / 'settings.json'):
            path.unlink(missing_ok=True)
        lock.close()


if __name__ == '__main__':
    sys.exit(main())
