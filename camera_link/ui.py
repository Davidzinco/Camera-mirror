"""Guided Qt UI for the first desktop-camera feasibility milestone."""
import ipaddress
import importlib.util
from pathlib import Path
import queue
import subprocess
import sys
import time

import numpy as np
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoSink
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from .frames import LatestFrame
from .pairing import Invitation
from .session import Session, SessionWorker

THEMES = {
    'dark': dict(bg='#1c1c1b', panel='#242423', text='#eeeeec', muted='#b0b0ad',
                 border='#3d3d3a', accent='#a14b45', hover='#b35851', ink='#ffffff', field='#2e2e2c'),
    'light': dict(bg='#eeede9', panel='#f7f6f2', text='#252523', muted='#62625d',
                  border='#bdbdb5', accent='#93413b', hover='#a14b45', ink='#ffffff', field='#ffffff'),
}


def theme_style(name):
    c = THEMES[name]
    return f'''
        QWidget {{ color: {c['text']}; font-family: "Segoe UI", "Noto Sans", sans-serif; font-size: 13px; }}
        QMainWindow, QDialog, QScrollArea, QWidget#page {{ background: {c['bg']}; }}
        QWidget#settingsPanel {{ background: {c['panel']}; }}
        QGroupBox {{ border: 0; border-top: 1px solid {c['border']};
                    border-radius: 0; margin-top: 12px; padding: 16px 0 0; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 0; padding: 0 8px 0 0; color: {c['muted']}; }}
        QLabel {{ background: transparent; }}
        QLabel#title {{ font-size: 16px; font-weight: 600; }}
        QLabel#muted {{ color: {c['muted']}; }}
        QLabel#preview {{ background: {c['bg']}; color: {c['muted']}; border: 1px solid {c['border']}; }}
        QLabel#stats, QPlainTextEdit {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; font-size: 12px; }}
        QLabel#stats {{ color: {c['muted']}; }}
        QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{ background: {c['bg']};
            border: 1px solid {c['border']}; border-radius: 2px; padding: 6px; selection-background-color: {c['accent']}; }}
        QComboBox QAbstractItemView {{ background: {c['panel']}; color: {c['text']};
            selection-background-color: {c['field']}; selection-color: {c['text']}; }}
        QPushButton {{ background: {c['panel']}; border: 1px solid {c['border']};
            border-radius: 2px; padding: 6px 12px; min-height: 18px; }}
        QPushButton#primary {{ background: {c['accent']}; color: {c['ink']}; border-color: {c['accent']}; }}
        QPushButton:hover {{ background: {c['field']}; }}
        QPushButton#primary:hover {{ background: {c['hover']}; }}
        QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{
            border: 1px solid {c['muted']}; }}
        QPushButton:disabled, QPushButton#primary:disabled {{ color: {c['muted']}; background: {c['bg']}; border-color: {c['border']}; }}
        QCheckBox {{ spacing: 8px; }}
        QCheckBox::indicator {{ width: 14px; height: 14px; }}
        QCheckBox::indicator:unchecked {{ background: {c['bg']}; border: 1px solid {c['border']}; }}
        QCheckBox:focus {{ color: {c['text']}; outline: 1px solid {c['muted']}; }}
        QScrollBar:vertical {{ background: {c['bg']}; width: 12px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 24px; margin: 2px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; }}
    '''


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Camera Mirror · Kamera melalui Wi-Fi')
        self.resize(1040, 680)
        self.setMinimumSize(680, 520)
        self.settings = QSettings('CameraMirror', 'DesktopCamera')
        self.frames = LatestFrame()
        self.camera = None
        self.capture = QMediaCaptureSession(self)
        self.video_sink = QVideoSink(self)
        self.capture.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self.capture_frame)
        self.media_devices = QMediaDevices(self)
        self.media_devices.videoInputsChanged.connect(self.refresh_cameras)
        self.worker = None
        self.pending_capture = False
        self.closing = False
        self.last_preview = -1
        self.last_error = False
        self.output_name = ''
        self._build()
        self.refresh_cameras()
        self.apply_theme()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)

    def _build(self):
        page = QWidget()
        page.setObjectName('page')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel('Camera Mirror')
        title.setObjectName('title')
        title.setWordWrap(True)
        header.addWidget(title)
        self.theme = QComboBox()
        self.theme.addItem('Gelap', 'dark')
        self.theme.addItem('Terang', 'light')
        self.theme.setAccessibleName('Tema tampilan')
        self.theme.setCurrentIndex(max(0, self.theme.findData(self.settings.value('theme', 'dark'))))
        self.theme.currentIndexChanged.connect(self.apply_theme)
        header.addWidget(self.theme)
        layout.addLayout(header)
        subtitle = QLabel(' /  Kamera komputer')
        subtitle.setObjectName('muted')
        header.insertWidget(1, subtitle, 1)

        self.workspace = QHBoxLayout()
        self.workspace.setSpacing(16)
        settings_panel = QWidget()
        settings_panel.setObjectName('settingsPanel')
        settings_panel.setMinimumWidth(288)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(12)
        settings_scroll = QScrollArea()
        self.settings_scroll = settings_scroll
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_panel)
        settings_scroll.setFixedWidth(312)
        self.workspace.addWidget(settings_scroll)
        monitor = QVBoxLayout()
        monitor.setSpacing(12)
        self.workspace.addLayout(monitor, 1)
        layout.addLayout(self.workspace, 1)

        role_box = QGroupBox('Mode koneksi')
        role_layout = QVBoxLayout(role_box)
        role_layout.setContentsMargins(0, 0, 0, 0)
        self.role = QComboBox()
        self.role.addItem('Kirim kamera', 'send')
        self.role.addItem('Terima kamera', 'receive')
        self.role.setAccessibleName('Peran komputer')
        self.role.currentIndexChanged.connect(self.change_role)
        role_layout.addWidget(self.role)
        settings_layout.addWidget(role_box)

        self.send_box = QGroupBox('Sumber kamera')
        form = QFormLayout(self.send_box)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(8)
        camera_row = QHBoxLayout()
        self.cameras = QComboBox()
        self.cameras.setMinimumContentsLength(16)
        self.cameras.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cameras.setAccessibleName('Kamera yang dibagikan')
        camera_row.addWidget(self.cameras, 1)
        self.refresh = QPushButton('Cari ulang')
        self.refresh.clicked.connect(self.refresh_cameras)
        camera_row.addWidget(self.refresh)
        form.addRow('Kamera', camera_row)
        self.address = QComboBox()
        self.address.setEditable(True)
        self.address.setAccessibleName('Alamat IPv4 jaringan pengirim')
        addresses = []
        for entry in QNetworkInterface.allAddresses():
            try:
                address = ipaddress.IPv4Address(entry.toString())
                if not address.is_loopback and not address.is_link_local and not address.is_multicast:
                    addresses.append(str(address))
            except ValueError:
                pass
        self.address.addItems(sorted(set(addresses)))
        if not addresses:
            self.address.setEditText('')
        form.addRow('Alamat jaringan', self.address)
        network_help = QLabel('Pilih IP Wi-Fi/LAN laptop ini. Penerima akan memakai alamat ini. '
                              'Kamera dikirim hingga 720p • 30 fps.')
        network_help.setWordWrap(True)
        network_help.setObjectName('muted')
        form.addRow(network_help)
        settings_layout.addWidget(self.send_box)

        self.receive_box = QGroupBox('Undangan pengirim')
        receiver = QVBoxLayout(self.receive_box)
        receiver.setContentsMargins(0, 0, 0, 0)
        self.incoming = QPlainTextEdit()
        self.incoming.setPlaceholderText('Tempel seluruh undangan cm1:… dari laptop pengirim')
        self.incoming.setAccessibleName('Undangan kamera dari pengirim')
        self.incoming.setFixedHeight(78)
        receiver.addWidget(self.incoming)
        self.destination_hint = QLabel('Gambar akan diteruskan ke kamera virtual agar dapat dipilih '
                                       'di OBS atau aplikasi panggilan.')
        self.destination_hint.setWordWrap(True)
        receiver.addWidget(self.destination_hint)
        self.receive_box.hide()
        settings_layout.addWidget(self.receive_box)

        self.advanced = QGroupBox('Pengaturan lanjutan')
        advanced_layout = QFormLayout(self.advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(8765)
        advanced_layout.addRow('Port pengirim', self.port)
        self.virtual_device = QLineEdit()
        self.virtual_device.setPlaceholderText('Otomatis; Linux: /dev/video10 jika sudah disiapkan')
        self.virtual_device.setText(self.settings.value('virtual_device', ''))
        advanced_layout.addRow('Perangkat virtual', self.virtual_device)
        self.preview_only = QCheckBox('Preview diagnostik saja')
        self.preview_only.setToolTip('Tidak tersedia sebagai webcam virtual.')
        advanced_layout.addRow(self.preview_only)
        self.advanced.hide()
        self.advanced_toggle = QPushButton('Pengaturan lanjutan')
        self.advanced_toggle.clicked.connect(self.toggle_advanced)
        settings_layout.addWidget(self.advanced_toggle)
        settings_layout.addWidget(self.advanced)

        self.invite_box = QGroupBox('Undangan untuk penerima')
        invite_layout = QVBoxLayout(self.invite_box)
        invite_layout.setContentsMargins(0, 0, 0, 0)
        self.outgoing = QPlainTextEdit()
        self.outgoing.setReadOnly(True)
        self.outgoing.setFixedHeight(72)
        self.outgoing.setAccessibleName('Undangan sekali pakai untuk penerima')
        invite_layout.addWidget(self.outgoing)
        self.copy = QPushButton('Salin undangan')
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.outgoing.toPlainText()))
        invite_layout.addWidget(self.copy, alignment=Qt.AlignmentFlag.AlignLeft)
        self.invite_box.hide()
        settings_layout.insertWidget(3, self.invite_box)
        settings_layout.addStretch()

        preview_heading = QLabel('Pratinjau')
        monitor.addWidget(preview_heading)
        self.preview = QLabel('Kamera tidak aktif.\nMulai sesi untuk menampilkan gambar.')
        self.preview.setObjectName('preview')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview.setMinimumWidth(1)
        monitor.addWidget(self.preview, 1)
        self.stats = QLabel('Belum ada stream aktif.')
        self.stats.setWordWrap(True)
        self.stats.setObjectName('stats')
        monitor.addWidget(self.stats)
        self.status = QLabel('Siap. Pilih Kirim di laptop atau Terima di desktop.')
        self.status.setWordWrap(True)
        self.status.setAccessibleName('Status koneksi kamera')
        monitor.addWidget(self.status)
        actions = QHBoxLayout()
        self.start_button = QPushButton('Mulai bagikan kamera')
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton('Berhenti')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addStretch()
        help_button = QPushButton('Bantuan')
        help_button.clicked.connect(self.help)
        actions.addWidget(help_button)
        layout.addLayout(actions)
        if sys.platform == 'linux':
            legacy = QPushButton('Kamera HP Android')
            legacy.clicked.connect(self.open_android)
            header.insertWidget(header.count()-1, legacy)
        note = QLabel('Sesi berhenti saat jendela ditutup. '
                      'Mikrofon dan speaker masih menunggu tahap pengembangan berikutnya.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        layout.addWidget(note)
        self.setCentralWidget(page)
        self.change_role()

    def apply_theme(self):
        name = self.theme.currentData()
        self.setStyleSheet(theme_style(name))
        self.settings.setValue('theme', name)

    def toggle_advanced(self):
        visible = not self.advanced.isVisible()
        self.advanced.setVisible(visible)
        self.advanced_toggle.setText('Tutup pengaturan lanjutan' if visible
                                     else 'Pengaturan lanjutan')
        if visible:
            QTimer.singleShot(0, lambda: self.settings_scroll.ensureWidgetVisible(self.preview_only))

    def change_role(self):
        sending = self.role.currentData() == 'send'
        self.send_box.setVisible(sending)
        self.receive_box.setVisible(not sending)
        self.port.setEnabled(sending)
        self.virtual_device.setEnabled(not sending)
        self.preview_only.setEnabled(not sending)
        self.start_button.setText('Mulai bagikan kamera' if sending else 'Hubungkan kamera')

    def refresh_cameras(self):
        if self.worker or self.pending_capture:
            return
        previous = self.cameras.currentData()
        previous_id = previous.id() if previous is not None else None
        self.cameras.clear()
        for device in QMediaDevices.videoInputs():
            self.cameras.addItem(device.description(), device)
            if device.id() == previous_id:
                self.cameras.setCurrentIndex(self.cameras.count()-1)
        if self.cameras.count() == 0:
            self.cameras.addItem('Kamera tidak ditemukan', None)

    def set_busy(self, busy):
        self.role.setEnabled(not busy)
        self.send_box.setEnabled(not busy)
        self.receive_box.setEnabled(not busy)
        self.advanced.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)

    def start(self):
        if self.worker or self.pending_capture:
            return
        self.last_error = False
        self.output_name = ''
        self.last_preview = -1
        self.frames.clear()
        self.stats.setText('Menyiapkan kamera…')
        sending = self.role.currentData() == 'send'
        try:
            if sending:
                # Validate before opening camera/listening; the real token is generated in worker.
                Invitation(self.address.currentText().strip(), self.port.value(), '0'*64, 'A'*43)
                device = self.cameras.currentData()
                if device is None:
                    raise ValueError('Kamera belum ditemukan. Hubungkan kamera dan klik Cari ulang.')
                self.set_busy(True)
                self.camera = QCamera(device, self)
                formats = [f for f in device.videoFormats()
                           if f.resolution().width() <= 1920 and f.resolution().height() <= 1080]
                if not formats:
                    raise ValueError('Kamera tidak menawarkan format hingga 1080p yang didukung prototipe.')
                chosen = min(formats, key=lambda f: (
                    not (f.minFrameRate() <= 30 <= f.maxFrameRate()),
                    abs(f.resolution().width()-1280) + abs(f.resolution().height()-720)))
                self.camera.setCameraFormat(chosen)
                self.camera.errorOccurred.connect(self.camera_error)
                self.capture.setCamera(self.camera)
                self.pending_capture = True
                self.capture_deadline = time.monotonic() + 10
                self.status.setText('Menyiapkan kamera. Izinkan akses kamera jika diminta sistem.')
                self.camera.start()
            else:
                invitation = Invitation.decode(self.incoming.toPlainText())
                self.settings.setValue('virtual_device', self.virtual_device.text().strip())
                self.set_busy(True)
                session = Session('receive', invitation=invitation,
                                  device=self.virtual_device.text().strip(),
                                  preview_only=self.preview_only.isChecked())
                self.launch(session)
                self.incoming.clear()
        except ValueError as exc:
            self.fail(str(exc))
            self.release_camera()
            self.set_busy(False)

    def launch(self, session):
        self.worker = SessionWorker(session)
        self.status.setText('Menyiapkan koneksi…')
        self.worker.start()

    def capture_frame(self, frame):
        if not self.pending_capture and (not self.worker or self.worker.session.role != 'send'):
            return
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        image = image.scaled(1280, 720, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.FastTransformation)
        image = image.convertToFormat(QImage.Format.Format_RGB888)
        array = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
        self.frames.put(array[:, :image.width()*3].reshape(image.height(), image.width(), 3).copy())

    def camera_error(self, error, message):
        if error == QCamera.Error.NoError:
            return
        self.fail('Kamera tidak dapat dibuka. Periksa izin kamera atau tutup aplikasi lain yang memakainya.')
        self.stop()

    def fail(self, message):
        self.last_error = True
        self.status.setText('Perlu diperiksa: ' + message)

    def stop(self):
        self.pending_capture = False
        self.release_camera()
        self.clear_invitation()
        if self.worker:
            self.stop_button.setEnabled(False)
            self.worker.stop()
            if not self.last_error:
                self.status.setText('Menghentikan kamera…')
        else:
            self.set_busy(False)
            if not self.last_error:
                self.status.setText('Kamera dihentikan.')
        self.preview.clear()
        self.preview.setText('Kamera tidak aktif.')

    def release_camera(self):
        self.pending_capture = False
        if self.camera:
            self.camera.stop()
            self.capture.setCamera(None)
            self.camera.deleteLater()
            self.camera = None
        self.frames.clear()

    def clear_invitation(self):
        invitation = self.outgoing.toPlainText()
        if invitation and QApplication.clipboard().text() == invitation:
            QApplication.clipboard().clear()
        self.outgoing.clear()
        self.invite_box.hide()

    def tick(self):
        if self.pending_capture:
            value, _, _ = self.frames.get()
            if value is not None:
                self.pending_capture = False
                self.launch(Session('send', source=self.frames,
                                    host=self.address.currentText().strip(), port=self.port.value()))
            elif time.monotonic() > self.capture_deadline:
                self.fail('Tidak ada gambar dari kamera. Periksa izin dan perangkat kamera.')
                self.stop()
        if self.worker:
            session = self.worker.session
            while True:
                try:
                    kind, value = session.events.get_nowait()
                except queue.Empty:
                    break
                if kind == 'status' and not self.last_error:
                    self.status.setText(value)
                elif kind == 'invitation':
                    self.clear_invitation()
                    self.outgoing.setPlainText(value)
                    self.invite_box.setVisible(bool(value))
                    if value:
                        QTimer.singleShot(0, lambda: self.settings_scroll.ensureWidgetVisible(self.copy))
                elif kind == 'output':
                    self.output_name = value
                elif kind == 'error':
                    self.fail(value)
            mailbox = self.frames if session.role == 'send' else session.received
            self.paint_preview(mailbox)
            if not self.worker.thread.is_alive():
                self.worker = None
                self.release_camera()
                self.clear_invitation()
                self.set_busy(False)
                self.preview.clear()
                self.preview.setText('Kamera tidak aktif.')
                self.stats.setText('Tidak ada stream aktif.')
                if not self.last_error:
                    self.status.setText('Kamera dihentikan. Mulai kembali untuk membuat sesi baru.')
        if self.closing and self.worker is None:
            self.close()

    def paint_preview(self, mailbox):
        array, sequence, stamp = mailbox.get()
        if array is None or time.monotonic()-stamp > 2:
            self.preview.clear()
            self.preview.setText('Menunggu gambar kamera…')
            return
        if sequence == self.last_preview:
            return
        self.last_preview = sequence
        h, w, _ = array.shape
        image = QImage(array.data, w, h, array.strides[0], QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image).scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)
        suffix = ('Pilih “' + self.output_name + '” di aplikasi tujuan.' if self.output_name else
                  ('Preview diagnostik; bukan webcam virtual.' if self.worker.session.preview_only
                   else 'Kamera laptop dibagikan selama sesi aktif.'))
        self.stats.setText(f'{w} × {h} • {suffix}')

    def help(self):
        QMessageBox.information(self, 'Menghubungkan kamera',
            '1. Laptop: pilih Kirim, kamera, dan IP Wi-Fi/LAN, lalu Mulai.\n'
            '2. Salin undangan melalui kanal pribadi ke desktop di LAN yang sama.\n'
            '3. Desktop: pilih Terima, tempel undangan, lalu Hubungkan.\n'
            '4. Pilih kamera virtual pada aplikasi panggilan atau OBS.\n\n'
            'Windows: pasang OBS Studio beserta Virtual Camera. Jangan jalankan '
            'keluaran OBS Virtual Camera bersamaan dengan aplikasi ini.\n'
            'Linux: siapkan v4l2loopback dengan exclusive_caps=1 dan izin akses pengguna.\n\n'
            'Izinkan port TCP pengirim (default 8765) dan trafik media UDP aplikasi '
            'di firewall jaringan pribadi. Jaringan tamu dapat memblokir koneksi antardevice.\n'
            'Undangan berlaku lima menit dan sekali pakai. Setelah putus, mulai ulang '
            'secara manual. Belum ada discovery atau reconnect otomatis.\n\n'
            'Lihat docs/DESKTOP_CAMERA.md untuk instalasi dan batasan prototipe.')

    def open_android(self):
        if any(importlib.util.find_spec(name) is None for name in ('PIL', 'tkinter')):
            QMessageBox.information(self, 'Penyiapan kamera Android',
                'Mode Android membutuhkan Pillow, Tkinter, dan dependensi Linux pada README.\n'
                'Pasang requirements.txt pada lingkungan Python ini dan Tkinter dari paket OS.')
            return
        path = Path(__file__).resolve().parent.parent / 'camera_mirror.py'
        subprocess.Popen([sys.executable, str(path)], cwd=str(path.parent))

    def closeEvent(self, event):
        if self.worker or self.pending_capture:
            self.closing = True
            self.stop()
            event.ignore()
        else:
            self.clear_invitation()
            event.accept()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window()
    window.show()
    return app.exec()
