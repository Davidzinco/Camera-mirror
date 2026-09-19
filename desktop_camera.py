#!/usr/bin/env python3
"""Windows/Linux entry point for the LAN camera prototype."""
import sys


def main():
    try:
        from camera_link.ui import main as run
    except ImportError as exc:
        message = ('Dependensi kamera desktop belum lengkap. Jalankan:\n'
                   'python -m pip install -r requirements-desktop.txt\n'
                   f'Komponen yang gagal dimuat: {exc.name}')
        print(message, file=sys.stderr)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.warning(None, 'Penyiapan Camera Mirror', message)
        except ImportError:
            pass
        return 1
    return run()


if __name__ == '__main__':
    sys.exit(main())
