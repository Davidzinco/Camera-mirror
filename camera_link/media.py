"""Media adapters; no systemd, FIFOs, or Linux-only imports."""
import asyncio
from fractions import Fraction
import sys
import threading
import time

import av
import numpy as np
from aiortc import VideoStreamTrack
from aiortc.mediastreams import MediaStreamError


class CameraTrack(VideoStreamTrack):
    def __init__(self, frames, fps=30):
        super().__init__()
        self.frames = frames
        self.fps = fps
        self.started = None
        self.counter = 0

    async def recv(self):
        if self.readyState != 'live':
            raise MediaStreamError
        now = time.monotonic()
        if self.started is None:
            self.started = now
        target = self.started + self.counter / self.fps
        await asyncio.sleep(max(0, target - now))
        # Skip elapsed slots instead of transmitting a burst of stale frames.
        self.counter = max(self.counter, int((time.monotonic() - self.started) * self.fps))
        image, _, stamp = self.frames.get()
        if image is None or time.monotonic() - stamp > 5:
            raise MediaStreamError
        frame = av.VideoFrame.from_ndarray(image, format='rgb24')
        frame.pts = self.counter * (90000 // self.fps)
        frame.time_base = Fraction(1, 90000)
        self.counter += 1
        return frame


class VirtualCamera:
    """Own the virtual device on one thread; never block the asyncio/UI loops."""
    def __init__(self, frames, device='', width=1280, height=720, fps=30):
        self.frames = frames
        self.device = device
        self.width, self.height, self.fps = width, height, fps
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.error = None
        self.name = ''
        self.thread = threading.Thread(target=self._run, name='virtual-camera', daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            import pyvirtualcam
            if sys.platform not in ('linux', 'win32'):
                raise RuntimeError('Output kamera virtual saat ini ditujukan untuk Windows dan Linux.')
            kwargs = dict(width=self.width, height=self.height, fps=self.fps,
                          fmt=pyvirtualcam.PixelFormat.RGB,
                          backend='v4l2loopback' if sys.platform == 'linux' else 'obs')
            if self.device:
                kwargs['device'] = self.device
            with pyvirtualcam.Camera(**kwargs) as camera:
                self.name = camera.device
                self.ready.set()
                empty = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                last_sequence = -1
                rendered = empty
                while not self.stopped.is_set():
                    value, sequence, stamp = self.frames.get()
                    if value is None or time.monotonic() - stamp > 2:
                        rendered = empty
                        last_sequence = -1
                    elif sequence != last_sequence:
                        source = av.VideoFrame.from_ndarray(value, format='rgb24')
                        # Letterbox to preserve the camera's aspect ratio.
                        ratio = min(self.width/source.width, self.height/source.height)
                        w, h = max(1, int(source.width*ratio)), max(1, int(source.height*ratio))
                        fitted = source.reformat(width=w, height=h, format='rgb24').to_ndarray()
                        rendered = empty.copy()
                        y, x = (self.height-h)//2, (self.width-w)//2
                        rendered[y:y+h, x:x+w] = fitted
                        last_sequence = sequence
                    camera.send(rendered)
                    camera.sleep_until_next_frame()
        except Exception as exc:
            self.error = exc
        finally:
            self.ready.set()

    async def open(self):
        self.start()
        if not await asyncio.to_thread(self.ready.wait, 10):
            raise RuntimeError('Perangkat kamera virtual tidak merespons.')
        if self.error:
            raise RuntimeError(self.help_text()) from self.error

    def help_text(self):
        if sys.platform == 'win32':
            return ('Kamera virtual belum tersedia. Pasang OBS Studio beserta Virtual Camera, '
                    'tutup pemakai kamera virtual lain, lalu coba lagi.')
        return ('Kamera virtual belum tersedia. Siapkan v4l2loopback dengan exclusive_caps=1, '
                'pilih /dev/video yang benar dan periksa izin aksesnya.')

    async def close(self):
        self.stopped.set()
        if self.thread.ident is not None:
            await asyncio.to_thread(self.thread.join, 3)
