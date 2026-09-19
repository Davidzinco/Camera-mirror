"""Real local WebRTC smoke/throughput check with a synthetic video source.

This does not validate a physical camera or a second computer. Use --virtual-camera
only after installing the OS virtual camera backend, then inspect it in another app.
"""
import argparse
import asyncio
import contextlib
import json
import queue
import time

import numpy as np

from .frames import LatestFrame
from .session import Session


async def check(seconds=10, virtual_camera=False, device=''):
    frames = LatestFrame()
    sender = Session('send', source=frames, host='127.0.0.1', port=0)
    receiver = None
    tasks = []

    async def produce():
        counter = 0
        deadline = time.monotonic()
        while True:
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            frame[:, :, 2] = 100
            x = (counter*12) % 1180
            frame[:, x:x+100, 1] = 220
            frames.put(frame)
            counter += 1
            deadline += 1/30
            await asyncio.sleep(max(0, deadline-time.monotonic()))

    producer = asyncio.create_task(produce())
    tasks.append(asyncio.create_task(sender.run()))
    try:
        invitation = None
        deadline = time.monotonic()+5
        while invitation is None:
            if time.monotonic() > deadline or tasks[0].done():
                raise RuntimeError(sender.failure or 'Pengirim tidak siap.')
            try:
                kind, value = sender.events.get_nowait()
                if kind == 'invitation':
                    invitation = value
            except queue.Empty:
                await asyncio.sleep(.01)
        receiver = Session('receive', invitation=invitation, preview_only=not virtual_camera,
                           device=device)
        tasks.append(asyncio.create_task(receiver.run()))
        deadline = time.monotonic()+35
        while receiver.frames_received == 0:
            if time.monotonic() > deadline or tasks[-1].done():
                raise RuntimeError(receiver.failure or 'Tidak ada video yang diterima.')
            await asyncio.sleep(.01)
        before = receiver.frames_received
        started, cpu_started = time.monotonic(), time.process_time()
        while time.monotonic()-started < seconds:
            if any(task.done() for task in tasks):
                raise RuntimeError(receiver.failure or sender.failure or 'Stream berhenti terlalu awal.')
            await asyncio.sleep(.05)
        elapsed = time.monotonic()-started
        count = receiver.frames_received-before
        return dict(source='synthetic 1280x720, target 30 fps', transport='WebRTC, loopback HTTPS pinned',
                    output=receiver.sink.name if receiver.sink else 'preview only (no virtual device)',
                    seconds=round(elapsed, 2), frames=count, received_fps=round(count/elapsed, 2),
                    process_cpu_percent=round((time.process_time()-cpu_started)/elapsed*100, 1),
                    physical_camera_tested=False, cross_os_tested=False,
                    motion_to_display_latency_measured=False)
    finally:
        sender.stop()
        if receiver:
            receiver.stop()
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), 5)
        finally:
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=10)
    parser.add_argument('--virtual-camera', action='store_true')
    parser.add_argument('--device', default='')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 1800:
        parser.error('--seconds must be between 1 and 1800')
    if args.device and not args.virtual_camera:
        parser.error('--device requires --virtual-camera')
    try:
        result = asyncio.run(check(args.seconds, args.virtual_camera, args.device))
    except (RuntimeError, TimeoutError) as exc:
        parser.exit(1, f'Pemeriksaan gagal: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
