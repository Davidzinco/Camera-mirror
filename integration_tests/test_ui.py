"""Headless Qt behavior tests; no hardware or real virtual driver is required."""
import importlib.util
import os
import queue
import tempfile
import time
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(name) for name in ('PySide6', 'aiortc', 'numpy', 'aiohttp'))
if AVAILABLE:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    import numpy as np
    from PySide6.QtCore import QPoint, QSettings
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtMultimedia import QVideoFrame
    from PySide6.QtWidgets import QApplication
    from camera_link.frames import LatestFrame
    from camera_link.session import Session, SessionWorker
    from camera_link.ui import Window


@unittest.skipUnless(AVAILABLE, 'Install requirements-desktop.txt for Qt tests')
class DesktopUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.settings = QSettings(self.folder.name+'/test.ini', QSettings.Format.IniFormat)
        with patch('camera_link.ui.QSettings', return_value=self.settings):
            self.window = Window()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.stop()
        deadline = time.monotonic()+5
        while self.window.worker and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(self.window.worker, 'UI failed to release worker')
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.folder.cleanup()

    def pump_until(self, predicate, timeout=8):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_roles_theme_and_invalid_invitation(self):
        w = self.window
        self.assertEqual(w.theme.currentData(), 'dark')
        w.theme.setCurrentIndex(1)
        self.assertEqual(self.settings.value('theme'), 'light')
        w.role.setCurrentIndex(1)
        self.assertFalse(w.send_box.isVisible())
        self.assertTrue(w.receive_box.isVisible())
        w.incoming.setPlainText('invalid')
        w.start_button.click()
        self.assertIn('Undangan tidak valid', w.status.text())
        self.assertIsNone(w.worker)
        self.assertTrue(w.start_button.isEnabled())

    def test_no_camera_fails_before_listening(self):
        w = self.window
        w.address.setEditText('127.0.0.1')
        w.cameras.clear()
        w.cameras.addItem('Tidak ada kamera', None)
        w.start_button.click()
        self.assertIn('Kamera belum ditemukan', w.status.text())
        self.assertIsNone(w.worker)
        self.assertFalse(w.pending_capture)

    def test_compact_layout_keeps_actions_visible_and_settings_reachable(self):
        w = self.window
        w.resize(680, 520)
        for role in (0, 1):
            w.role.setCurrentIndex(role)
            w.advanced.hide()
            w.toggle_advanced()
            self.app.processEvents()
            self.app.processEvents()
            self.assertEqual((w.width(), w.height()), (680, 520))
            self.assertEqual(w.settings_scroll.horizontalScrollBar().maximum(), 0)
            for control in (w.start_button, w.stop_button, w.preview):
                position = control.mapTo(w, QPoint(0, 0))
                self.assertGreaterEqual(position.x(), 0)
                self.assertGreaterEqual(position.y(), 0)
                self.assertLessEqual(position.x() + control.width(), w.width())
                self.assertLessEqual(position.y() + control.height(), w.height())
            viewport = w.settings_scroll.viewport()
            position = w.preview_only.mapTo(viewport, QPoint(0, 0))
            self.assertGreaterEqual(position.y(), 0)
            self.assertLessEqual(position.y() + w.preview_only.height(), viewport.height())

        w.role.setCurrentIndex(0)
        w.invite_box.show()
        w.outgoing.setPlainText('cm1:' + 'a' * 500)
        self.app.processEvents()
        w.settings_scroll.ensureWidgetVisible(w.copy)
        self.app.processEvents()
        self.assertEqual(w.settings_scroll.horizontalScrollBar().maximum(), 0)
        self.assertTrue(w.settings_scroll.viewport().rect().contains(
            w.copy.mapTo(w.settings_scroll.viewport(), w.copy.rect().center())))

    def test_capture_converts_padded_rows_and_ignores_frames_after_stop(self):
        w = self.window
        image = QImage(9, 17, QImage.Format.Format_RGB888)
        image.fill(QColor(7, 31, 211))
        frame = QVideoFrame(image)
        w.pending_capture = True
        w.capture_frame(frame)
        w.pending_capture = False
        captured = w.frames.get()[0]
        self.assertEqual(captured.shape[0], 720)
        self.assertTrue(np.all(captured == [7, 31, 211]))
        w.stop()
        w.capture_frame(frame)
        self.assertIsNone(w.frames.get()[0])
        self.assertIsNone(w.worker)

    def test_receiver_preview_and_close_stops_worker(self):
        source = LatestFrame()
        source.put(np.full((180, 320, 3), 120, dtype=np.uint8))
        sender = Session('send', source=source, host='127.0.0.1', port=0)
        sender_worker = SessionWorker(sender)
        sender_worker.start()
        invitation = None
        try:
            deadline = time.monotonic()+5
            while invitation is None and time.monotonic() < deadline:
                try:
                    kind, value = sender.events.get(timeout=.05)
                    if kind == 'invitation':
                        invitation = value
                except queue.Empty:
                    pass
            self.assertIsNotNone(invitation)
            w = self.window
            w.role.setCurrentIndex(1)
            w.preview_only.setChecked(True)
            w.incoming.setPlainText(invitation)
            w.start_button.click()
            self.pump_until(lambda: w.worker is not None and w.worker.session.frames_received >= 3)
            self.pump_until(lambda: 'Preview diagnostik' in w.stats.text())
            self.assertFalse(w.role.isEnabled())
            self.assertEqual(w.incoming.toPlainText(), '')
            worker = w.worker
            w.close()
            self.pump_until(lambda: w.worker is None)
            self.assertFalse(worker.thread.is_alive())
            self.assertIsNone(worker.session.received.get()[0])
        finally:
            sender_worker.stop()
            sender_worker.thread.join(5)
            self.assertFalse(sender_worker.thread.is_alive())
