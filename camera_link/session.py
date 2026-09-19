"""Single-peer WebRTC session with certificate-pinned HTTPS signaling."""
import asyncio
import contextlib
import json
import queue
import re
import secrets
import tempfile
import threading
import time

import aiohttp
from aiohttp import web
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError

from .frames import LatestFrame
from .media import CameraTrack, VirtualCamera
from .pairing import Invitation, PairingGate, create_tls


class LinkError(RuntimeError):
    pass


def description(data, expected):
    if (not isinstance(data, dict) or data.get('type') != expected
            or not isinstance(data.get('sdp'), str) or len(data['sdp']) > 65536):
        raise ValueError('Deskripsi sesi tidak valid.')
    # This prototype negotiates one camera, never audio or extra data channels.
    media = [line for line in data['sdp'].splitlines() if line.startswith('m=')]
    if len(media) != 1 or not media[0].startswith('m=video '):
        raise ValueError('Sesi harus berisi satu kamera.')
    return RTCSessionDescription(sdp=data['sdp'], type=expected)


class Session:
    """All network objects belong to run()'s event loop; stop is thread-safe."""
    def __init__(self, role, source=None, host='127.0.0.1', port=8765,
                 invitation=None, device='', preview_only=False,
                 sink_factory=VirtualCamera):
        if role not in ('send', 'receive'):
            raise ValueError('Peran sesi tidak valid.')
        self.role = role
        self.source = source if source is not None else LatestFrame()
        self.received = LatestFrame()
        self.host, self.port = host, port
        self.invitation = invitation
        self.device = device
        self.preview_only = preview_only
        self.sink_factory = sink_factory
        self.events = queue.Queue()
        self.stop_requested = threading.Event()
        self.pc = None
        self.runner = None
        self.sink = None
        self.consumer = None
        self.gate = None
        self.negotiating_since = None
        self.connected = False
        self.failure = None
        self.frames_received = 0
        self.remote_invitation = None
        self.control_token = None

    def emit(self, kind, value):
        self.events.put((kind, value))

    def stop(self):
        self.stop_requested.set()

    async def run(self):
        try:
            if self.stop_requested.is_set():
                return
            self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))

            @self.pc.on('connectionstatechange')
            async def state_changed():
                state = self.pc.connectionState
                if state == 'connected':
                    self.connected = True
                    self.emit('status', 'Mengirim kamera' if self.role == 'send' else
                              ('Menerima — preview diagnostik saja' if self.preview_only
                               else 'Menerima — kamera virtual aktif'))
                elif state == 'failed':
                    self.failure = 'Koneksi terputus. Periksa Wi-Fi, lalu buat undangan baru.'
                    self.stop()

            with tempfile.TemporaryDirectory(prefix='camera-mirror-') as folder:
                if self.role == 'send':
                    await self._serve(folder)
                else:
                    await self._connect()
                await self._watch()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self.stop_requested.is_set():
                if isinstance(exc, (LinkError, ValueError)):
                    self.failure = str(exc)
                elif isinstance(exc, aiohttp.ServerFingerprintMismatch):
                    self.failure = 'Identitas pengirim berbeda. Minta undangan baru dari laptop yang benar.'
                elif isinstance(exc, (aiohttp.ClientError, TimeoutError, OSError)):
                    self.failure = ('Tidak dapat terhubung. Periksa alamat jaringan, firewall, '
                                    'dan pastikan kedua perangkat berada di LAN yang sama.')
                else:
                    self.failure = 'Sesi kamera gagal. Periksa kamera dan dependensi, lalu coba lagi.'
        finally:
            self.stop_requested.set()
            if self.consumer:
                self.consumer.cancel()
                with contextlib.suppress(asyncio.CancelledError, MediaStreamError):
                    await self.consumer
            if self.remote_invitation:
                await self._notify_stop()
            if self.runner:
                await self.runner.cleanup()
            if self.pc:
                await self.pc.close()
            if self.sink:
                await self.sink.close()
            self.received.clear()
            if self.failure:
                self.emit('error', self.failure)
            self.emit('finished', '')

    async def _serve(self, folder):
        self.gate = PairingGate()
        context, fingerprint = create_tls(folder)
        app = web.Application(client_max_size=70000)
        app.router.add_post('/offer', self._offer)
        app.router.add_post('/stop', self._remote_stop)
        self.runner = web.AppRunner(app, access_log=None, shutdown_timeout=1)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port, ssl_context=context)
        await site.start()
        # Port zero is useful for isolated integration tests.
        actual_port = self.runner.addresses[0][1]
        invitation = Invitation(self.host, actual_port, fingerprint, self.gate.token)
        self.emit('invitation', invitation.encode())
        self.emit('status', 'Menunggu penerima — undangan berlaku 5 menit, satu kali pakai')

    async def _offer(self, request):
        auth = request.headers.get('Authorization', '')
        token = auth.removeprefix('Bearer ') if auth.startswith('Bearer ') else ''
        # Claim before any await so two simultaneous requests cannot share the camera.
        if self.stop_requested.is_set() or not self.gate.claim(token):
            if self.gate.attempts <= 0:
                self.failure = 'Terlalu banyak percobaan pairing. Mulai ulang untuk membuat undangan baru.'
                self.stop()
            raise web.HTTPForbidden(text='Undangan kedaluwarsa, salah, atau sudah digunakan.')
        self.negotiating_since = time.monotonic()
        self.emit('invitation', '')
        try:
            data = await asyncio.wait_for(request.json(), 5)
            offer = description(data, 'offer')
            self.pc.addTrack(CameraTrack(self.source))
            await asyncio.wait_for(self.pc.setRemoteDescription(offer), 10)
            answer = await self.pc.createAnswer()
            await asyncio.wait_for(self.pc.setLocalDescription(answer), 10)
            self.control_token = secrets.token_urlsafe(32)
            self.emit('status', 'Menghubungkan kamera ke penerima…')
            return web.json_response(dict(sdp=self.pc.localDescription.sdp, type='answer',
                                          control=self.control_token))
        except Exception as exc:
            if not self.stop_requested.is_set():
                self.failure = 'Pairing gagal. Mulai ulang dan gunakan undangan baru.'
            self.stop()
            raise web.HTTPBadRequest(text='Negosiasi kamera gagal.') from exc

    async def _remote_stop(self, request):
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if (not self.control_token or not token.isascii()
                or not secrets.compare_digest(token, self.control_token)):
            raise web.HTTPForbidden()
        self.emit('status', 'Penerima menghentikan sesi kamera.')
        self.stop()
        return web.Response(status=204)

    async def _notify_stop(self):
        invitation = self.remote_invitation
        # Best effort: network loss must never prevent local shutdown.
        with contextlib.suppress(aiohttp.ClientError, TimeoutError, OSError):
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1)) as client:
                async with client.post(f'https://{invitation.host}:{invitation.port}/stop',
                        ssl=aiohttp.Fingerprint(bytes.fromhex(invitation.fingerprint)),
                        allow_redirects=False,
                        headers={'Authorization': 'Bearer '+self.control_token}):
                    pass

    async def _connect(self):
        invitation = self.invitation
        if isinstance(invitation, str):
            invitation = Invitation.decode(invitation)
        if not isinstance(invitation, Invitation):
            raise ValueError('Tempel undangan dari komputer pengirim.')
        if not self.preview_only:
            self.sink = self.sink_factory(self.received, device=self.device)
            try:
                await self.sink.open()
            except RuntimeError as exc:
                raise LinkError(str(exc)) from exc
            self.emit('output', self.sink.name)

        @self.pc.on('track')
        def on_track(track):
            if track.kind == 'video' and self.consumer is None:
                self.consumer = asyncio.create_task(self._consume(track))

        self.pc.addTransceiver('video', direction='recvonly')
        await self.pc.setLocalDescription(await self.pc.createOffer())
        self.negotiating_since = time.monotonic()
        self.emit('status', 'Menghubungkan ke kamera pengirim…')
        # Pin is checked before sending the token or SDP; redirects are disallowed.
        fingerprint = aiohttp.Fingerprint(bytes.fromhex(invitation.fingerprint))
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as client:
            async with client.post(
                    f'https://{invitation.host}:{invitation.port}/offer',
                    ssl=fingerprint, allow_redirects=False,
                    headers={'Authorization': 'Bearer ' + invitation.token},
                    json=dict(sdp=self.pc.localDescription.sdp, type='offer')) as response:
                if response.status == 403:
                    raise LinkError('Undangan kedaluwarsa atau sudah dipakai. Minta undangan baru.')
                if response.status != 200:
                    raise LinkError('Pengirim menolak sesi. Buat undangan baru dan coba lagi.')
                # Bound peer-controlled signaling data even when Content-Length is absent.
                body = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    body.extend(chunk)
                    if len(body) > 70000:
                        raise LinkError('Jawaban pengirim terlalu besar.')
                payload = json.loads(body)
                answer = description(payload, 'answer')
                control = payload.get('control')
                if not isinstance(control, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', control):
                    raise LinkError('Kredensial sesi pengirim tidak valid.')
                self.control_token = control
                self.remote_invitation = invitation
        await self.pc.setRemoteDescription(answer)

    async def _consume(self, track):
        try:
            while not self.stop_requested.is_set():
                frame = await track.recv()
                if frame.width > 1920 or frame.height > 1080:
                    raise ValueError('Ukuran kamera melebihi batas prototipe (1080p).')
                self.received.put(frame.to_ndarray(format='rgb24'))
                self.frames_received += 1
        except asyncio.CancelledError:
            raise
        except MediaStreamError:
            if not self.stop_requested.is_set():
                self.failure = 'Pengirim menghentikan kamera. Buat undangan baru untuk menyambung kembali.'
                self.stop()
        except Exception:
            self.failure = 'Video tidak dapat dibaca. Periksa kamera pengirim dan mulai ulang.'
            self.stop()

    async def _watch(self):
        started = time.monotonic()
        while not self.stop_requested.is_set():
            now = time.monotonic()
            if self.gate and not self.gate.used and now >= self.gate.deadline:
                raise LinkError('Undangan kedaluwarsa. Mulai kembali untuk membuat undangan baru.')
            if self.negotiating_since and not self.connected and now-self.negotiating_since > 30:
                raise LinkError('Koneksi media gagal. Periksa firewall UDP dan isolasi jaringan Wi-Fi.')
            mailbox = self.source if self.role == 'send' else self.received
            _, _, stamp = mailbox.get()
            if (self.role == 'send' or self.connected) and now-max(stamp, started) > 10:
                raise LinkError('Kamera tidak mengirim gambar. Periksa perangkat lalu mulai ulang.')
            if self.sink and self.sink.error:
                raise LinkError(self.sink.help_text())
            await asyncio.sleep(.1)
        if self.failure:
            raise LinkError(self.failure)


class SessionWorker:
    """Cooperative cancellation also covers in-flight HTTPS/capture setup."""
    def __init__(self, session):
        self.session = session
        self.thread = threading.Thread(target=self._run, name='camera-network', daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.session.stop()

    async def _supervise(self):
        task = asyncio.create_task(self.session.run())
        try:
            while not task.done():
                if self.session.stop_requested.is_set():
                    task.cancel()
                    break
                await asyncio.sleep(.05)
            with contextlib.suppress(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def _run(self):
        asyncio.run(self._supervise())
