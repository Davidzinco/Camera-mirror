"""Install the desktop app into its own environment and create a user shortcut.

Uses only Python's standard library; never installs packages into system Python.
"""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PROBE = ('import aiohttp, aiortc, av, numpy, cryptography, pyvirtualcam; '
         'from PySide6 import QtWidgets, QtMultimedia, QtNetwork')


class SetupError(RuntimeError):
    pass


def environment_python(root, windows=None):
    windows = sys.platform == 'win32' if windows is None else windows
    return root / '.venv' / ('Scripts/python.exe' if windows else 'bin/python')


def run(command, root):
    subprocess.run([str(part) for part in command], cwd=root, check=True)


def requirement_stamp(root):
    return hashlib.sha256((root/'requirements-desktop.txt').read_bytes()).hexdigest()


def probe(python, root):
    result = subprocess.run([str(python), '-c', PROBE], cwd=root,
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise SetupError('Dependensi belum dapat dimuat:\n' + detail +
                         '\nLihat bagian Masalah instalasi di README.md. '
                         'Library sistem Qt tidak dipasang oleh pip.')


def prepare(root, reinstall=False):
    python = environment_python(root)
    marker = root/'.venv'/'.camera-mirror-ready'
    expected = requirement_stamp(root)
    # Use an existing environment when available, even if the caller's Python changed.
    if not python.is_file():
        if not (3, 10) <= sys.version_info[:2] < (3, 15) or struct.calcsize('P') != 8:
            raise SetupError('Gunakan Python 64-bit versi 3.10 sampai 3.14; disarankan 3.12.')
        print('Membuat lingkungan aplikasi .venv...', flush=True)
        try:
            run([sys.executable, '-m', 'venv', root/'.venv'], root)
        except subprocess.CalledProcessError as exc:
            raise SetupError('Lingkungan Python gagal dibuat. Pada Ubuntu/Debian pasang '
                             'python3-venv, lalu jalankan installer lagi. Lihat README.md.') from exc
    saved = marker.read_text().strip() if marker.exists() else ''
    if reinstall or saved != expected:
        marker.unlink(missing_ok=True)
        print('Memasang dependensi Camera Mirror. Unduhan pertama dapat memakan beberapa menit.', flush=True)
        run([python, '-m', 'pip', 'install', '-r', root/'requirements-desktop.txt'], root)
        probe(python, root)
        marker.write_text(expected+'\n')
    else:
        probe(python, root)
    return python


def desktop_quote(value):
    """Quote one Exec argument, including the desktop entry string-escape layer."""
    value = str(value)
    if any(char in value for char in '\r\n\0'):
        raise SetupError('Nama folder berisi karakter yang tidak didukung pintasan.')
    value = value.replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\'+char)
    # Backslashes are unescaped once by the .desktop parser, then by the Exec parser.
    return '"'+value.replace('\\', '\\\\')+'"'


def linux_shortcut(root, python):
    base = Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local'/'share')
    folder = base/'applications'
    folder.mkdir(parents=True, exist_ok=True)
    entry = folder/'camera-mirror-desktop.desktop'
    command = ' '.join(desktop_quote(value) for value in
                       (python, root/'scripts'/'bootstrap.py', '--launch'))
    entry.write_text('[Desktop Entry]\nType=Application\nName=Camera Mirror\n'
                     'Comment=Bagikan kamera melalui Wi-Fi\n'
                     f'Exec={command}\nIcon=camera-video\nTerminal=true\n'
                     'Categories=AudioVideo;Video;\n', encoding='utf-8')
    entry.chmod(0o755)
    return entry


def windows_shortcut(root):
    # Pass the path via the environment, never interpolate it into PowerShell source.
    env = dict(os.environ, CAMERA_MIRROR_INSTALL_ROOT=str(root))
    code = r'''
$ErrorActionPreference = 'Stop'
$folder = Join-Path ([Environment]::GetFolderPath('Programs')) 'Camera Mirror'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $folder 'Camera Mirror.lnk'))
$link.TargetPath = Join-Path $env:CAMERA_MIRROR_INSTALL_ROOT 'Install-Windows.cmd'
$link.WorkingDirectory = $env:CAMERA_MIRROR_INSTALL_ROOT
$link.Description = 'Bagikan kamera melalui Wi-Fi'
$link.Save()
'''
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', code],
                   check=True, env=env)
    return 'Start Menu > Camera Mirror'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch', action='store_true', help='Open the app after setup')
    parser.add_argument('--no-shortcut', action='store_true', help='Do not change the application menu')
    parser.add_argument('--reinstall', action='store_true', help='Run pip again even if requirements are unchanged')
    args = parser.parse_args(argv)
    try:
        if sys.platform not in ('linux', 'win32'):
            raise SetupError('Installer ini ditujukan untuk Windows dan Linux.')
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            raise SetupError('Jalankan installer sebagai pengguna desktop, tanpa sudo.')
        python = prepare(ROOT, args.reinstall)
        if not args.no_shortcut:
            try:
                shortcut = windows_shortcut(ROOT) if sys.platform == 'win32' else linux_shortcut(ROOT, python)
                print(f'Pintasan tersedia: {shortcut}', flush=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                print(f'Pintasan gagal dibuat ({exc}). Aplikasi tetap bisa dibuka lewat installer.', flush=True)
        print('Aplikasi siap. Kamera virtual pada komputer penerima disiapkan terpisah; lihat README.md.', flush=True)
        if args.launch:
            run([python, ROOT/'desktop_camera.py'], ROOT)
        return 0
    except (SetupError, OSError, subprocess.SubprocessError) as exc:
        print(f'\nPenyiapan belum selesai: {exc}\nJalankan installer lagi setelah masalah diperbaiki.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
