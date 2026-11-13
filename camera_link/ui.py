"""Guided Qt UI with seamless mode switching between Laptop LAN camera and Android camera."""
import ipaddress
import importlib.util
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

import numpy as np
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoSink
from PySide6.QtNetwork import QNetworkInterface
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .frames import LatestFrame
from .pairing import Invitation
from .session import Session, SessionWorker

# Cross-platform Android imports
try:
    import backend as android_backend
    import controller as android_controller
    import wireless as android_wireless
    import preferences as android_preferences
except ImportError:
    android_backend = None
    android_controller = None
    android_wireless = None
    android_preferences = None

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
        QWidget#settingsPanel, QWidget#androidSettingsPanel {{ background: {c['panel']}; }}
        QGroupBox {{ border: 0; border-top: 1px solid {c['border']};
                    border-radius: 0; margin-top: 12px; padding: 14px 0 0; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 0; padding: 0 8px 0 0; color: {c['muted']}; font-weight: 600; }}
        QLabel {{ background: transparent; }}
        QLabel#title {{ font-size: 16px; font-weight: 600; }}
        QLabel#muted {{ color: {c['muted']}; }}
        QLabel#preview, QLabel#androidPreview {{ background: {c['bg']}; color: {c['muted']}; border: 1px solid {c['border']}; }}
        QLabel#stats, QLabel#androidStats, QPlainTextEdit {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; font-size: 12px; }}
        QLabel#stats, QLabel#androidStats {{ color: {c['muted']}; }}
        QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{ background: {c['bg']};
            border: 1px solid {c['border']}; border-radius: 2px; padding: 5px 8px; selection-background-color: {c['accent']}; }}
        QComboBox QAbstractItemView {{ background: {c['panel']}; color: {c['text']};
            selection-background-color: {c['field']}; selection-color: {c['text']}; }}
        QPushButton {{ background: {c['panel']}; border: 1px solid {c['border']};
            border-radius: 2px; padding: 5px 12px; min-height: 18px; }}
        QPushButton#primary {{ background: {c['accent']}; color: {c['ink']}; border-color: {c['accent']}; font-weight: 600; }}
        QPushButton:hover {{ background: {c['field']}; }}
        QPushButton#primary:hover {{ background: {c['hover']}; }}
        QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{
            border: 1px solid {c['muted']}; }}
        QPushButton:disabled, QPushButton#primary:disabled {{ color: {c['muted']}; background: {c['bg']}; border-color: {c['border']}; }}
        
        QPushButton#modeSelected {{
            background: {c['accent']};
            color: {c['ink']};
            font-weight: 600;
            border: 1px solid {c['accent']};
            border-radius: 4px;
            padding: 6px 14px;
            min-height: 20px;
        }}
        QPushButton#modeUnselected {{
            background: {c['panel']};
            color: {c['muted']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 6px 14px;
            min-height: 20px;
        }}
        QPushButton#modeUnselected:hover {{
            background: {c['field']};
            color: {c['text']};
        }}
        
        QCheckBox {{ spacing: 8px; }}
        QCheckBox::indicator {{ width: 14px; height: 14px; }}
        QCheckBox::indicator:unchecked {{ background: {c['bg']}; border: 1px solid {c['border']}; }}
        QCheckBox:focus {{ color: {c['text']}; outline: 1px solid {c['muted']}; }}
        QScrollBar:vertical {{ background: {c['bg']}; width: 12px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 24px; margin: 2px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; }}
        QStackedWidget {{ background: transparent; }}
    '''


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Camera Mirror · Berbagi Kamera Wi-Fi & HP')
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
        self.android_busy = False
        self.android_stopping = False

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
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header bar
        header = QHBoxLayout()
        title = QLabel('Camera Mirror')
        title.setObjectName('title')
        title.setWordWrap(True)
        header.addWidget(title)

        self.subtitle = QLabel(' /  Kamera Laptop ⇄ PC')
        self.subtitle.setObjectName('muted')
        header.addWidget(self.subtitle, 1)

        self.theme = QComboBox()
        self.theme.addItem('Gelap', 'dark')
        self.theme.addItem('Terang', 'light')
        self.theme.setAccessibleName('Tema tampilan')
        self.theme.setCurrentIndex(max(0, self.theme.findData(self.settings.value('theme', 'dark'))))
        self.theme.currentIndexChanged.connect(self.apply_theme)
        header.addWidget(self.theme)
        layout.addLayout(header)

        # Mode switcher buttons (One-click toggle between modes)
        mode_bar = QHBoxLayout()
        mode_bar.setSpacing(8)
        self.mode_laptop_btn = QPushButton('💻 Kamera Laptop ke PC (Wi-Fi)')
        self.mode_laptop_btn.setObjectName('modeSelected')
        self.mode_laptop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_laptop_btn.clicked.connect(lambda: self.switch_mode(0))
        mode_bar.addWidget(self.mode_laptop_btn)

        self.mode_android_btn = QPushButton('📱 Kamera HP Android ke PC')
        self.mode_android_btn.setObjectName('modeUnselected')
        self.mode_android_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_android_btn.clicked.connect(lambda: self.switch_mode(1))
        mode_bar.addWidget(self.mode_android_btn)
        mode_bar.addStretch()
        layout.addLayout(mode_bar)

        # Stacked pages for the two modes
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # ========================================================
        # PAGE 0: Laptop-to-PC (LAN Wi-Fi WebRTC Mode)
        # ========================================================
        self.laptop_page = QWidget()
        laptop_layout = QVBoxLayout(self.laptop_page)
        laptop_layout.setContentsMargins(0, 0, 0, 0)
        laptop_layout.setSpacing(8)

        self.workspace = QHBoxLayout()
        self.workspace.setSpacing(14)
        settings_panel = QWidget()
        settings_panel.setObjectName('settingsPanel')
        settings_panel.setMinimumWidth(288)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(8)

        settings_scroll = QScrollArea()
        self.settings_scroll = settings_scroll
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_panel)
        settings_scroll.setFixedWidth(312)
        self.workspace.addWidget(settings_scroll)

        monitor = QVBoxLayout()
        monitor.setSpacing(8)
        self.workspace.addLayout(monitor, 1)
        laptop_layout.addLayout(self.workspace, 1)

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
        form.setVerticalSpacing(6)
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
                addr = ipaddress.IPv4Address(entry.toString())
                if not addr.is_loopback and not addr.is_link_local and not addr.is_multicast:
                    addresses.append(str(addr))
            except ValueError:
                pass
        self.address.addItems(sorted(set(addresses)))
        if not addresses:
            self.address.setEditText('')
        form.addRow('Alamat jaringan', self.address)
        network_help = QLabel('Pilih IP Wi-Fi/LAN laptop ini. Penerima memakai alamat ini. '
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
        self.incoming.setFixedHeight(72)
        receiver.addWidget(self.incoming)
        self.destination_hint = QLabel('Gambar diteruskan ke kamera virtual (OBS di Windows, v4l2loopback di Linux).')
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
        self.outgoing.setFixedHeight(68)
        self.outgoing.setAccessibleName('Undangan sekali pakai untuk penerima')
        invite_layout.addWidget(self.outgoing)
        self.copy = QPushButton('Salin undangan')
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.outgoing.toPlainText()))
        invite_layout.addWidget(self.copy, alignment=Qt.AlignmentFlag.AlignLeft)
        self.invite_box.hide()
        settings_layout.insertWidget(3, self.invite_box)
        settings_layout.addStretch()

        preview_heading = QLabel('Pratinjau Laptop ⇄ PC')
        monitor.addWidget(preview_heading)
        self.preview = QLabel('Kamera tidak aktif.\nMulai sesi untuk menampilkan gambar.')
        self.preview.setObjectName('preview')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(160)
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
        laptop_layout.addLayout(actions)

        note = QLabel('Sesi berhenti saat jendela ditutup. Wi-Fi lokal aman dengan PIN fingerprint TLS.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        laptop_layout.addWidget(note)

        self.stack.addWidget(self.laptop_page)

        # ========================================================
        # PAGE 1: Android Phone Camera to PC Mode (Windows & Linux)
        # ========================================================
        self.android_page = QWidget()
        android_layout = QVBoxLayout(self.android_page)
        android_layout.setContentsMargins(0, 0, 0, 0)
        android_layout.setSpacing(8)

        android_workspace = QHBoxLayout()
        android_workspace.setSpacing(14)
        android_settings_panel = QWidget()
        android_settings_panel.setObjectName('androidSettingsPanel')
        android_settings_panel.setMinimumWidth(288)
        android_settings_layout = QVBoxLayout(android_settings_panel)
        android_settings_layout.setContentsMargins(10, 10, 10, 10)
        android_settings_layout.setSpacing(8)

        android_scroll = QScrollArea()
        android_scroll.setFrameShape(QFrame.Shape.NoFrame)
        android_scroll.setWidgetResizable(True)
        android_scroll.setWidget(android_settings_panel)
        android_scroll.setFixedWidth(312)
        android_workspace.addWidget(android_scroll)

        android_monitor = QVBoxLayout()
        android_monitor.setSpacing(8)
        android_workspace.addLayout(android_monitor, 1)
        android_layout.addLayout(android_workspace, 1)

        # Device selection box
        dev_box = QGroupBox('Perangkat HP Android')
        dev_layout = QVBoxLayout(dev_box)
        dev_layout.setContentsMargins(0, 0, 0, 0)
        dev_row = QHBoxLayout()
        self.android_devices = QComboBox()
        self.android_devices.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        dev_row.addWidget(self.android_devices, 1)
        self.android_refresh_btn = QPushButton('🔄 Cari')
        self.android_refresh_btn.clicked.connect(self.android_refresh_devices)
        dev_row.addWidget(self.android_refresh_btn)
        dev_layout.addLayout(dev_row)

        self.android_dev_hint = QLabel('Sambungkan HP via kabel USB (Debug USB aktif) atau Wi-Fi.')
        self.android_dev_hint.setWordWrap(True)
        self.android_dev_hint.setObjectName('muted')
        dev_layout.addWidget(self.android_dev_hint)
        android_settings_layout.addWidget(dev_box)

        # Camera settings box
        cam_box = QGroupBox('Pengaturan Kamera HP')
        cam_form = QFormLayout(cam_box)
        cam_form.setContentsMargins(0, 0, 0, 0)
        cam_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        cam_form.setVerticalSpacing(6)

        self.android_facing = QComboBox()
        self.android_facing.addItem('Kamera Belakang (Utama)', 'back')
        self.android_facing.addItem('Kamera Depan (Selfie)', 'front')
        cam_form.addRow('Arah kamera', self.android_facing)

        self.android_size = QComboBox()
        self.android_size.addItem('1920 × 1080 (FHD)', '1920x1080')
        self.android_size.addItem('1280 × 720 (HD)', '1280x720')
        cam_form.addRow('Resolusi', self.android_size)

        self.android_fps = QComboBox()
        self.android_fps.addItem('30 FPS (Standar)', '30')
        self.android_fps.addItem('60 FPS (Mulus)', '60')
        self.android_fps.addItem('15 FPS (Hemat)', '15')
        cam_form.addRow('Kecepatan frame', self.android_fps)

        self.android_screen_off = QCheckBox('Padamkan layar HP saat aktif (hemat baterai)')
        self.android_screen_off.setChecked(True)
        cam_form.addRow(self.android_screen_off)
        android_settings_layout.addWidget(cam_box)

        # Wireless setup box
        wifi_box = QGroupBox('Koneksi Nirkabel HP (Wi-Fi)')
        wifi_layout = QVBoxLayout(wifi_box)
        wifi_layout.setContentsMargins(0, 0, 0, 0)

        self.android_tcpip_btn = QPushButton('⚡ Jadikan Wi-Fi (dari USB)')
        self.android_tcpip_btn.setToolTip('Aktifkan mode nirkabel sekali-klik dari kabel USB yang terpasang')
        self.android_tcpip_btn.clicked.connect(self.android_setup_wifi_usb)
        wifi_layout.addWidget(self.android_tcpip_btn)

        pair_row = QHBoxLayout()
        self.android_ip = QLineEdit()
        self.android_ip.setPlaceholderText('IP:Port (cth: 192.168.1.5:38123)')
        pair_row.addWidget(self.android_ip, 2)
        self.android_code = QLineEdit()
        self.android_code.setPlaceholderText('Kode 6 angka')
        self.android_code.setMaxLength(6)
        pair_row.addWidget(self.android_code, 1)
        wifi_layout.addLayout(pair_row)

        pair_btn_row = QHBoxLayout()
        self.android_pair_btn = QPushButton('Pair Wireless')
        self.android_pair_btn.clicked.connect(self.android_pair_device)
        pair_btn_row.addWidget(self.android_pair_btn)
        self.android_connect_btn = QPushButton('Hubungkan IP')
        self.android_connect_btn.clicked.connect(self.android_connect_device)
        pair_btn_row.addWidget(self.android_connect_btn)
        wifi_layout.addLayout(pair_btn_row)
        android_settings_layout.addWidget(wifi_box)

        # Tools status
        tools_box = QGroupBox('Status Alat (ADB & scrcpy)')
        tools_layout = QVBoxLayout(tools_box)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        self.android_tools_status = QLabel('Mengecek ketersediaan program…')
        self.android_tools_status.setObjectName('muted')
        self.android_tools_status.setWordWrap(True)
        tools_layout.addWidget(self.android_tools_status)
        self.android_tools_check_btn = QPushButton('Cek ulang ADB & scrcpy')
        self.android_tools_check_btn.clicked.connect(self.android_check_tools)
        tools_layout.addWidget(self.android_tools_check_btn)
        android_settings_layout.addWidget(tools_box)
        android_settings_layout.addStretch()

        # Android monitor / preview
        android_preview_head = QLabel('Pratinjau & Status HP Android')
        android_monitor.addWidget(android_preview_head)
        self.android_preview = QLabel('Kamera HP belum aktif.\nKlik "Mulai Kamera HP" untuk memulai streaming.')
        self.android_preview.setObjectName('androidPreview')
        self.android_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.android_preview.setMinimumHeight(160)
        self.android_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.android_preview.setMinimumWidth(1)
        android_monitor.addWidget(self.android_preview, 1)

        self.android_stats = QLabel('Belum ada stream aktif.')
        self.android_stats.setObjectName('androidStats')
        self.android_stats.setWordWrap(True)
        android_monitor.addWidget(self.android_stats)

        self.android_status = QLabel('Siap. Pilih perangkat HP di sebelah kiri.')
        self.android_status.setWordWrap(True)
        android_monitor.addWidget(self.android_status)

        # Android actions
        android_actions = QHBoxLayout()
        self.android_start_btn = QPushButton('Mulai Kamera HP')
        self.android_start_btn.setObjectName('primary')
        self.android_start_btn.clicked.connect(self.android_start)
        self.android_stop_btn = QPushButton('Berhenti')
        self.android_stop_btn.setEnabled(False)
        self.android_stop_btn.clicked.connect(self.android_stop)
        android_actions.addWidget(self.android_start_btn)
        android_actions.addWidget(self.android_stop_btn)
        android_actions.addStretch()

        self.android_log_btn = QPushButton('Log Kamera')
        self.android_log_btn.clicked.connect(self.android_show_logs)
        android_actions.addWidget(self.android_log_btn)

        self.android_help_btn = QPushButton('Bantuan HP')
        self.android_help_btn.clicked.connect(self.android_show_help)
        android_actions.addWidget(self.android_help_btn)
        android_layout.addLayout(android_actions)

        android_note = QLabel(
            'Windows: Kamera HP diteruskan melalui OBS Virtual Camera atau tangkapan jendela. '
            'Linux: Kamera HP otomatis masuk ke perangkat virtual /dev/video10.'
        )
        android_note.setWordWrap(True)
        android_note.setObjectName('muted')
        android_layout.addWidget(android_note)

        self.stack.addWidget(self.android_page)

        self.setCentralWidget(page)
        self.change_role()
        self.android_check_tools()

    def switch_mode(self, index):
        """Switch between Laptop-to-PC mode (0) and Android-to-PC mode (1)."""
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.mode_laptop_btn.setObjectName('modeSelected')
            self.mode_android_btn.setObjectName('modeUnselected')
            self.subtitle.setText(' /  Kamera Laptop ⇄ PC')
        else:
            self.mode_laptop_btn.setObjectName('modeUnselected')
            self.mode_android_btn.setObjectName('modeSelected')
            self.subtitle.setText(' /  Kamera HP Android')
            self.android_refresh_devices()
        self.apply_theme()

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

        # Update Android status if active
        if android_backend:
            is_active = android_backend.active()
            if is_active and not self.android_stop_btn.isEnabled():
                self.android_start_btn.setEnabled(False)
                self.android_stop_btn.setEnabled(True)
            elif not is_active and self.android_stop_btn.isEnabled() and not self.android_busy:
                self.android_start_btn.setEnabled(True)
                self.android_stop_btn.setEnabled(False)
                self.android_status.setText('Kamera HP berhenti.')
                self.android_stats.setText('Stream nonaktif.')
                self.android_preview.setText('Kamera HP tidak aktif.')

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

    # ========================================================
    # Android mode handler methods
    # ========================================================
    def android_check_tools(self):
        """Check availability of adb and scrcpy."""
        if not android_backend:
            self.android_tools_status.setText('Modul backend Android tidak ditemukan.')
            return
        adb = android_backend.find_executable('adb')
        scrcpy = android_backend.find_executable('scrcpy')
        adb_ok = shutil.which(adb) or Path(adb).is_file()
        scrcpy_ok = shutil.which(scrcpy) or Path(scrcpy).is_file()

        if adb_ok and scrcpy_ok:
            self.android_tools_status.setText('✔️ ADB & scrcpy siap digunakan.')
        else:
            missing = []
            if not adb_ok: missing.append('ADB')
            if not scrcpy_ok: missing.append('scrcpy')
            self.android_tools_status.setText(f'⚠️ Belum terpasang: {", ".join(missing)}.\nKlik Bantuan HP untuk cara pasang.')

    def android_refresh_devices(self):
        """Populate the Android device dropdown with authorized and unauthorized status."""
        if not android_backend:
            return
        self.android_devices.clear()
        try:
            devs = android_backend.device_details()
            if devs:
                unauth = [d for d in devs if not d.get('authorized', True)]
                auth = [d for d in devs if d.get('authorized', True)]
                for d in auth:
                    label = f"📱 {d['name']} ({d['serial']}) [{d['mode'].upper()}]"
                    self.android_devices.addItem(label, d)
                for d in unauth:
                    label = f"⚠️ [Perlu Izin HP] {d['name']} ({d['serial']})"
                    self.android_devices.addItem(label, d)

                if auth:
                    self.android_status.setText(f"Ditemukan {len(auth)} HP siap. Klik Mulai Kamera HP.")
                    self.android_dev_hint.setText("Perangkat siap terhubung.")
                elif unauth:
                    self.android_status.setText("⚠️ HP terdeteksi, tetapi perlu izin! Buka layar HP dan klik 'Izinkan USB debugging' (Allow).")
                    self.android_dev_hint.setText("Tekan 'Izinkan' atau 'Allow' pada pop-up di layar HP Anda, lalu klik Cari lagi.")
            else:
                self.android_devices.addItem('Tidak ada HP terdeteksi', None)
                self.android_status.setText('Tidak ada HP terdeteksi. Hubungkan kabel USB atau cek Wi-Fi.')
                self.android_dev_hint.setText('Sambungkan HP via kabel USB (Debug USB aktif) atau Wi-Fi.')
        except Exception as exc:
            self.android_devices.addItem('Error mendeteksi perangkat', None)
            self.android_status.setText(f'Gagal mendeteksi perangkat: {exc}')

    def android_start(self):
        """Start streaming from the selected Android phone."""
        if not android_controller or not android_backend:
            QMessageBox.warning(self, 'Peringatan', 'Modul Android tidak tersedia.')
            return
        data = self.android_devices.currentData()
        if not data or not data.get('serial'):
            QMessageBox.information(self, 'Info', 'Silakan pilih perangkat HP Android yang terhubung terlebih dahulu.')
            return

        serial = data['serial']
        facing = self.android_facing.currentData()
        size = self.android_size.currentData()
        fps = self.android_fps.currentData()

        if android_preferences:
            android_preferences.save(facing=facing, size=size, fps=fps,
                                     screen_off=self.android_screen_off.isChecked())

        self.android_busy = True
        self.android_start_btn.setEnabled(False)
        self.android_stop_btn.setEnabled(True)
        self.android_status.setText(f'Menghubungkan ke kamera HP {data["name"]}…')
        self.android_stats.setText(f'Menyiapkan resolusi {size} • {fps} fps ({facing})…')

        def worker():
            try:
                android_controller.start(serial, facing, size, fps)
            except Exception as exc:
                QTimer.singleShot(0, lambda: self._android_error(str(exc)))
            finally:
                self.android_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _android_error(self, message):
        self.android_start_btn.setEnabled(True)
        self.android_stop_btn.setEnabled(False)
        self.android_status.setText(f'Gagal: {message}')
        self.android_stats.setText('Stream gagal dimulai.')
        QMessageBox.warning(self, 'Error Kamera HP', message)

    def android_stop(self):
        """Stop the Android camera stream without blocking the UI thread."""
        if not android_backend or self.android_stopping:
            return
        self.android_stopping = True
        self.android_start_btn.setEnabled(False)
        self.android_stop_btn.setEnabled(False)
        self.android_status.setText('Menghentikan kamera HP…')

        def worker():
            try:
                android_backend.stop()
                QTimer.singleShot(0, self._android_stop_done)
            except Exception as exc:
                message = str(exc)
                QTimer.singleShot(0, lambda: self._android_stop_done(message))

        threading.Thread(target=worker, daemon=True, name='android-stop').start()

    def _android_stop_done(self, error=None):
        self.android_stopping = False
        self.android_start_btn.setEnabled(True)
        self.android_stop_btn.setEnabled(False)
        if error:
            self.android_status.setText(f'Gagal menghentikan kamera: {error}')
            self.android_stats.setText('Stream mungkin masih aktif; cek Log Kamera.')
            return
        self.android_status.setText('Kamera HP dihentikan.')
        self.android_stats.setText('Stream nonaktif.')
        self.android_preview.setText('Kamera HP tidak aktif.')

    def android_setup_wifi_usb(self):
        """Switch USB connected Android device to wireless ADB tcpip mode."""
        if not android_wireless:
            return
        data = self.android_devices.currentData()
        if not data or data.get('mode') != 'usb':
            QMessageBox.information(self, 'Sambungkan USB',
                                    'Hubungkan HP ke laptop/PC dengan kabel USB terlebih dahulu dengan Debug USB aktif.')
            return
        self.android_status.setText('Mengalihkan HP ke mode Wi-Fi…')

        def worker():
            try:
                addr = android_wireless.setup_usb(data)
                QTimer.singleShot(0, lambda: self._android_wifi_success(addr))
            except Exception as exc:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, 'Gagal Wi-Fi', str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _android_wifi_success(self, addr):
        self.android_status.setText(f'Mode Wi-Fi berhasil! Terhubung ke {addr}.')
        self.android_refresh_devices()
        QMessageBox.information(self, 'Sukses Mode Wi-Fi',
                                f'HP sekarang terhubung secara nirkabel melalui {addr}.\nKabel USB sudah dapat dilepas!')

    def android_pair_device(self):
        """Pair phone via Wireless Debugging code."""
        if not android_backend:
            return
        addr = self.android_ip.text().strip()
        code = self.android_code.text().strip()
        if not addr or not code:
            QMessageBox.information(self, 'Pairing Wireless',
                                    'Isi alamat IP:Port dan kode pairing 6 angka dari layar Wireless Debugging HP.')
            return
        self.android_pair_btn.setEnabled(False)
        self.android_status.setText('Melakukan pairing wireless…')

        def worker():
            try:
                msg = android_backend.pair(addr, code)
                QTimer.singleShot(0, lambda: self._android_pair_done(msg))
            except Exception as exc:
                message = str(exc)
                QTimer.singleShot(0, lambda: self._android_pair_done(None, message))

        threading.Thread(target=worker, daemon=True, name='android-pair').start()

    def _android_pair_done(self, message=None, error=None):
        self.android_pair_btn.setEnabled(True)
        if error:
            self.android_status.setText(f'Pairing gagal: {error}')
            QMessageBox.warning(self, 'Pairing Gagal', error)
            return
        self.android_status.setText('Pairing berhasil.')
        QMessageBox.information(self, 'Pairing Sukses', message)
        self.android_refresh_devices()

    def android_connect_device(self):
        """Connect to paired Wireless device."""
        if not android_backend:
            return
        addr = self.android_ip.text().strip()
        if not addr:
            QMessageBox.information(self, 'Hubungkan IP', 'Isi alamat IP:Port nirkabel HP.')
            return
        self.android_connect_btn.setEnabled(False)
        self.android_status.setText(f'Menghubungkan ke {addr}…')

        def worker():
            try:
                android_backend.connect(addr)
                QTimer.singleShot(0, lambda: self._android_connect_done(addr))
            except Exception as exc:
                message = str(exc)
                QTimer.singleShot(0, lambda: self._android_connect_done(addr, message))

        threading.Thread(target=worker, daemon=True, name='android-connect').start()

    def _android_connect_done(self, addr, error=None):
        self.android_connect_btn.setEnabled(True)
        if error:
            self.android_status.setText(f'Gagal terhubung: {error}')
            QMessageBox.warning(self, 'Gagal Terhubung', error)
            return
        self.android_status.setText(f'Terhubung ke {addr}.')
        self.android_refresh_devices()

    def android_show_logs(self):
        """Display Android camera logs."""
        if not android_backend:
            return
        logs = android_backend.logs()
        box = QMessageBox(self)
        box.setWindowTitle('Log Kamera HP Android')
        box.setText(logs or 'Belum ada catatan log.')
        box.exec()

    def android_show_help(self):
        """Display help dialog for Android camera mode."""
        msg = (
            "📱 Panduan Kamera HP Android ke PC:\n\n"
            "1. Di HP: Buka Pengaturan > Opsi Pengembang (Developer Options).\n"
            "2. Aktifkan 'Debugging USB' (USB Debugging).\n"
            "3. Sambungkan HP ke PC via kabel USB, lalu klik 'Cari HP'.\n"
            "4. Klik '⚡ Jadikan Wi-Fi (dari USB)' jika ingin mencabut kabel.\n"
            "5. Klik 'Mulai Kamera HP'.\n\n"
            "🔹 Persyaratan Windows:\n"
            "   Pasang scrcpy & ADB via perintah terminal:\n"
            "   winget install Genymobile.scrcpy\n"
            "   dan pasang OBS Studio untuk OBS Virtual Camera.\n\n"
            "🔹 Persyaratan Linux:\n"
            "   sudo apt install scrcpy adb (Ubuntu/Debian)\n"
            "   atau sudo pacman -S scrcpy android-tools (Arch/CachyOS)\n"
        )
        QMessageBox.information(self, 'Bantuan Kamera HP Android', msg)

    def help(self):
        QMessageBox.information(self, 'Menghubungkan kamera Laptop ke PC',
            '1. Laptop: pilih Kirim, kamera, dan IP Wi-Fi/LAN, lalu Mulai.\n'
            '2. Salin undangan melalui kanal pribadi ke desktop di LAN yang sama.\n'
            '3. Desktop: pilih Terima, tempel undangan, lalu Hubungkan.\n'
            '4. Pilih kamera virtual pada aplikasi panggilan atau OBS.\n\n'
            'Windows: pasang OBS Studio beserta Virtual Camera. Jangan jalankan '
            'keluaran OBS Virtual Camera bersamaan dengan aplikasi ini.\n'
            'Linux: siapkan v4l2loopback dengan exclusive_caps=1 dan izin akses pengguna.\n\n'
            'Izinkan port TCP pengirim (default 8765) dan trafik media UDP aplikasi '
            'di firewall jaringan pribadi.\n\n'
            'Gunakan tombol di atas untuk beralih antara Kamera Laptop dan Kamera HP Android!')

    def open_android(self):
        """Switch to Android mode page directly."""
        self.switch_mode(1)

    def closeEvent(self, event):
        if self.worker or self.pending_capture:
            self.closing = True
            self.stop()
            event.ignore()
        else:
            if android_backend and android_backend.active():
                android_backend.stop()
            self.clear_invitation()
            event.accept()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window()
    window.show()
    return app.exec()
