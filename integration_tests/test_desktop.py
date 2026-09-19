import asyncio
import contextlib
from dataclasses import replace
import importlib.util
import queue
import tempfile
import time
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(name) for name in
                ('aiortc', 'aiohttp', 'av', 'numpy', 'pyvirtualcam', 'cryptography'))
if AVAILABLE:
    import aiohttp
    import numpy as np
    from camera_link.frames import LatestFrame
    from camera_link.media import CameraTrack, VirtualCamera
    from camera_link.pairing import Invitation, create_tls
    from camera_link.session import Session, SessionWorker, description


@unittest.skipUnless(AVAILABLE, 'Install requirements-desktop.txt for media integration tests')
class MediaIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tasks = []
        self.sessions = []
        self.producer = None

    async def asyncTearDown(self):
        for session in self.sessions:
            session.stop()
        for task in self.tasks:
            try:
                await asyncio.wait_for(task, 5)
            except TimeoutError:
                self.fail('Session failed to stop and release its network resources')
        if self.producer:
            self.producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.producer

    async def wait_until(self, predicate, timeout=15):
        async def wait():
            while not predicate():
                await asyncio.sleep(.02)
        await asyncio.wait_for(wait(), timeout)

    def run_session(self, session):
        self.sessions.append(session)
        task = asyncio.create_task(session.run())
        self.tasks.append(task)
        return task

    async def sender(self):
        frames = LatestFrame()
        async def produce():
            counter = 0
            while True:
                image = np.zeros((180, 320, 3), dtype=np.uint8)
                image[:, :, 0] = 200
                image[:, (counter % 280):(counter % 280)+40, 1] = 200
                frames.put(image)
                counter += 1
                await asyncio.sleep(1/30)
        self.producer = asyncio.create_task(produce())
        sender = Session('send', source=frames, host='127.0.0.1', port=0)
        self.run_session(sender)
        invitation = None
        async def get_invitation():
            nonlocal invitation
            while invitation is None:
                try:
                    kind, value = sender.events.get_nowait()
                    if kind == 'invitation' and value:
                        invitation = Invitation.decode(value)
                except queue.Empty:
                    await asyncio.sleep(.01)
        await asyncio.wait_for(get_invitation(), 5)
        return sender, invitation

    async def test_encrypted_camera_reaches_virtual_output_adapter(self):
        sent = []
        class FakeDevice:
            device = 'Test virtual device'
            def __init__(self, **kwargs):
                self.kwargs = kwargs
            def __enter__(self):
                return self
            def __exit__(self, *args):
                sent.append('closed')
            def send(self, image):
                # Only collect a small scalar, never an unbounded frame backlog.
                sent.append(int(image[360, 640, 0]))
            def sleep_until_next_frame(self):
                time.sleep(1/30)

        sender, invitation = await self.sender()
        with patch('pyvirtualcam.Camera', FakeDevice):
            receiver = Session('receive', invitation=invitation)
            task = self.run_session(receiver)
            await self.wait_until(lambda: receiver.frames_received >= 12)
            await self.wait_until(lambda: any(isinstance(v, int) and v > 150 for v in sent))
            frame, _, _ = receiver.received.get()
            self.assertEqual(frame.shape, (180, 320, 3))
            self.assertTrue(sender.connected)
            self.assertTrue(receiver.connected)
            self.assertEqual(receiver.sink.name, 'Test virtual device')
            self.assertFalse(sender.gate.claim(invitation.token))
            replay = Session('receive', invitation=invitation, preview_only=True)
            await asyncio.wait_for(self.run_session(replay), 5)
            self.assertIn('sudah dipakai', replay.failure)
            self.assertFalse(sender.stop_requested.is_set())
            # The original invitation cannot control a session after it is claimed.
            async with aiohttp.ClientSession() as client:
                async with client.post(f'https://127.0.0.1:{invitation.port}/stop',
                        ssl=aiohttp.Fingerprint(bytes.fromhex(invitation.fingerprint)),
                        headers={'Authorization': 'Bearer '+invitation.token}) as response:
                    self.assertEqual(response.status, 403)
            receiver.stop()
            await asyncio.wait_for(task, 5)
            await self.wait_until(lambda: self.tasks[0].done())
            self.assertFalse(receiver.sink.thread.is_alive())
            self.assertEqual(sent[-1], 'closed')
            self.assertIsNone(receiver.received.get()[0])

    async def test_certificate_mismatch_does_not_disclose_or_consume_token(self):
        sender, invitation = await self.sender()
        bad = replace(invitation, fingerprint='0'*64)
        receiver = Session('receive', invitation=bad, preview_only=True)
        await asyncio.wait_for(self.run_session(receiver), 5)
        self.assertIn('Identitas', receiver.failure)
        self.assertFalse(sender.gate.used)
        self.assertEqual(sender.gate.attempts, 5)

    async def test_missing_virtual_device_leaves_pairing_available(self):
        sender, invitation = await self.sender()
        with patch('pyvirtualcam.Camera', side_effect=RuntimeError('No virtual device')):
            receiver = Session('receive', invitation=invitation)
            await asyncio.wait_for(self.run_session(receiver), 5)
        self.assertIn('Kamera virtual belum tersedia', receiver.failure)
        self.assertFalse(sender.gate.used)
        self.assertFalse(receiver.sink.thread.is_alive())

    async def test_unauthorized_stop_cannot_terminate_sender(self):
        sender, invitation = await self.sender()
        async with aiohttp.ClientSession() as client:
            async with client.post(f'https://127.0.0.1:{invitation.port}/stop',
                    ssl=aiohttp.Fingerprint(bytes.fromhex(invitation.fingerprint)),
                    headers={'Authorization': 'Bearer wrong'}) as response:
                self.assertEqual(response.status, 403)
        self.assertFalse(sender.stop_requested.is_set())

    async def test_replayed_pairing_rejected_over_https(self):
        sender, invitation = await self.sender()
        self.assertTrue(sender.gate.claim(invitation.token))
        async with aiohttp.ClientSession() as client:
            async with client.post(f'https://127.0.0.1:{invitation.port}/offer',
                    ssl=aiohttp.Fingerprint(bytes.fromhex(invitation.fingerprint)),
                    headers={'Authorization': 'Bearer '+invitation.token}, json={}) as response:
                self.assertEqual(response.status, 403)

    async def test_stop_worker_during_connection_attempt(self):
        frames = LatestFrame()
        frames.put(np.zeros((180, 320, 3), dtype=np.uint8))
        session = Session('send', source=frames, host='127.0.0.1', port=0)
        worker = SessionWorker(session)
        worker.start()
        await self.wait_until(lambda: session.runner is not None)
        worker.stop()
        await asyncio.to_thread(worker.thread.join, 5)
        self.assertFalse(worker.thread.is_alive())
        self.assertTrue(session.pc is None or session.pc.connectionState == 'closed')

    async def test_video_timestamps_increase_and_sdp_rejects_extra_media(self):
        frames = LatestFrame()
        frames.put(np.zeros((10, 10, 3), dtype=np.uint8))
        track = CameraTrack(frames)
        one, two = await track.recv(), await track.recv()
        self.assertGreater(two.pts, one.pts)
        track.stop()
        for sdp in ('v=0\r\nm=audio 1 RTP/AVP 0\r\n',
                    'm=video 1 RTP/AVP 96\r\nm=video 2 RTP/AVP 96\r\n'):
            with self.assertRaises(ValueError):
                description(dict(type='offer', sdp=sdp), 'offer')

    async def test_virtual_camera_stale_image_becomes_black(self):
        values = []
        class FakeDevice:
            device = 'Test'
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def send(self, image): values.append(int(image.max()))
            def sleep_until_next_frame(self): time.sleep(.01)
        frames = LatestFrame()
        frames.put(np.full((10, 10, 3), 200, dtype=np.uint8))
        with patch('pyvirtualcam.Camera', FakeDevice):
            sink = VirtualCamera(frames, width=20, height=20)
            try:
                await sink.open()
                await self.wait_until(lambda: 200 in values)
                frames.clear()
                await self.wait_until(lambda: values[-1] == 0)
            finally:
                await sink.close()
        self.assertFalse(sink.thread.is_alive())
