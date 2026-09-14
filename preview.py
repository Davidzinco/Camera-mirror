"""Decode only the newest preview frame, outside the Tk event loop."""
import queue
import threading
from PIL import Image, ImageOps
from stream_service import runtime_dir


class Reader:
    def __init__(self):
        self.frames = queue.Queue(maxsize=1)
        self.enabled = False
        self.viewport = (960, 540)
        self.generation = 0
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def reset(self):
        self.generation += 1
        try: self.frames.get_nowait()
        except queue.Empty: pass

    def close(self):
        self.enabled = False
        self.stopped.set()

    def _loop(self):
        previous = None
        while not self.stopped.wait(.004):
            if not self.enabled: continue
            try:
                file = runtime_dir()/'preview.jpg'
                stat = file.stat()
                size, generation = self.viewport, self.generation
                stamp = (stat.st_mtime_ns, size, generation)
                if stamp == previous: continue
                with Image.open(file) as source:
                    frame = ImageOps.contain(source.convert('RGB'), size, Image.Resampling.BILINEAR)
                if not self.enabled or generation != self.generation: continue
                previous = stamp
                try: self.frames.get_nowait()
                except queue.Empty: pass
                self.frames.put_nowait((stat.st_mtime, frame, generation))
            except (OSError, ValueError, queue.Full): pass
