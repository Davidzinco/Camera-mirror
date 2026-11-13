"""Command layer for Camera Mirror. All commands run without a shell."""
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

UNIT = "android-webcam"
_active_process = None
_recent_logs = []


def find_executable(name):
    """Find executable in PATH or standard installation directories on Windows/Linux."""
    found = shutil.which(name)
    if found:
        return found
    if sys.platform != 'win32':
        return name
    wanted = name if Path(name).suffix else name + '.exe'
    candidates = []
    user_profile = Path(os.environ.get('USERPROFILE', ''))
    local_app_data = Path(os.environ.get('LOCALAPPDATA', ''))
    program_files = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))

    if name in ('adb', 'adb.exe'):
        candidates.extend([
            local_app_data / 'Android' / 'Sdk' / 'platform-tools' / 'adb.exe',
            user_profile / 'scrcpy' / 'adb.exe',
            Path('C:/scrcpy/adb.exe'),
            program_files / 'scrcpy' / 'adb.exe',
            Path('C:/platform-tools/adb.exe'),
        ])
    elif name in ('scrcpy', 'scrcpy.exe'):
        candidates.extend([
            user_profile / 'scrcpy' / 'scrcpy.exe',
            local_app_data / 'Programs' / 'scrcpy' / 'scrcpy.exe',
            Path('C:/scrcpy/scrcpy.exe'),
            program_files / 'scrcpy' / 'scrcpy.exe',
        ])

    # Check WinGet package directories. Only the exact executable counts, so
    # look-alikes such as scrcpy-server are never picked.
    winget_pkg = local_app_data / 'Microsoft' / 'WinGet' / 'Packages'
    if winget_pkg.is_dir():
        try:
            candidates.extend(sorted(path for path in winget_pkg.glob(f'**/{wanted}')
                                     if path.is_file()))
        except OSError:
            pass

    for candidate in candidates:
        if candidate.is_file():
            parent_dir = str(candidate.parent)
            if parent_dir not in os.environ.get('PATH', ''):
                os.environ['PATH'] = parent_dir + os.pathsep + os.environ.get('PATH', '')
            return str(candidate)
    return name


def install_hint(program):
    """Hint shown when a required program is missing."""
    if sys.platform != 'win32':
        return "Pasang scrcpy & adb dari package manager distro Linux Anda."
    name = Path(program).stem.lower()
    if name == 'adb':
        return ("Pasang dengan: winget install Google.PlatformTools "
                "(paket scrcpy juga menyertakan adb)")
    if name == 'scrcpy':
        return "Pasang dengan: winget install Genymobile.scrcpy"
    return "Pasang program tersebut lalu jalankan Camera Mirror lagi."


def run(args, timeout=25, input_text=None):
    cmd = list(args)
    if cmd and isinstance(cmd[0], str):
        cmd[0] = find_executable(cmd[0])
    try:
        result = subprocess.run(cmd, input=input_text, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
    except FileNotFoundError:
        prog = args[0]
        raise RuntimeError(f"Program '{prog}' belum terpasang atau tidak ditemukan di PATH. "
                           f"{install_hint(prog)}")
    if result.returncode:
        raise RuntimeError(result.stdout.strip() or f"Perintah gagal: {args[0]}")
    return result.stdout.strip()


def endpoint(value):
    """Require a literal LAN IP and explicit port, including bracketed IPv6."""
    value = value.strip()
    host, sep, port = value.rpartition(":")
    if not sep or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("Gunakan IP:port dari layar Wireless debugging, contoh 192.168.1.20:37123.")
    ipaddress.ip_address(host.strip("[]"))
    return value


def devices():
    try:
        output = run(["adb", "devices", "-l"])
    except RuntimeError:
        return []
    return [line.split()[0] for line in output.splitlines()
            if len(line.split()) >= 2 and line.split()[1] == "device"]


def pair(address, code):
    address = endpoint(address)
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("Kode pairing harus 6 angka.")
    # Do not expose the pairing code in process arguments or logs.
    output = run(["adb", "pair", address], timeout=60, input_text=code + "\n")
    if "successfully paired" not in output.lower():
        raise RuntimeError(output)
    return "Pairing berhasil. Isi alamat koneksi dari halaman utama Wireless debugging."


def connect(address):
    address = endpoint(address)
    output = run(["adb", "connect", address])
    if address not in devices():
        raise RuntimeError(output + "\nHP belum terhubung; cek IP, port, dan jaringan.")
    return output


def camera_command(serial, facing, size, fps, preview=False, v4l2_sink=None):
    if not serial or serial.startswith("-") or any(c.isspace() for c in serial):
        raise ValueError("Pilih perangkat yang sudah terhubung.")
    if facing not in ("back", "front") or size not in ("1280x720", "1920x1080") or fps not in ("15", "30", "60"):
        raise ValueError("Pengaturan kamera tidak valid.")
    scrcpy_bin = find_executable("scrcpy")
    args = [scrcpy_bin, "--serial=" + serial, "--video-source=camera",
            "--camera-facing=" + facing, "--camera-size=" + size, "--camera-fps=" + fps,
            "--no-audio", "--video-codec=h264", "--video-buffer=0"]
    if v4l2_sink:
        args += ["--v4l2-sink=" + v4l2_sink, "--v4l2-buffer=0"]
        args += ["--window-title=Camera Mirror · Android Webcam"] if preview else ["--no-window"]
    elif sys.platform == 'linux' and Path('/dev/video10').exists():
        args += ["--v4l2-sink=/dev/video10", "--v4l2-buffer=0"]
        args += ["--window-title=Camera Mirror · Android Webcam"] if preview else ["--no-window"]
    else:
        args += ["--window-title=Camera Mirror · Android Webcam"]
        if not preview and sys.platform != 'win32':
            args += ["--no-window"]
    return args


def set_active_process(proc):
    global _active_process
    _active_process = proc


def append_log(line):
    _recent_logs.append(line)
    if len(_recent_logs) > 100:
        _recent_logs.pop(0)


def active():
    global _active_process
    if _active_process is not None:
        if _active_process.poll() is None:
            return True
        _active_process = None
    if sys.platform == 'linux' and shutil.which('systemctl'):
        try:
            result = subprocess.run(["systemctl", "--user", "is-active", UNIT],
                                    text=True, capture_output=True, timeout=5)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    return False


def stop():
    global _active_process
    if _active_process is not None:
        try:
            _active_process.terminate()
            _active_process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                _active_process.kill()
            except OSError:
                pass
        _active_process = None
    if sys.platform == 'linux' and shutil.which('systemctl'):
        try:
            run(["systemctl", "--user", "stop", UNIT])
        except Exception:
            pass


def logs():
    if _recent_logs:
        return "\n".join(_recent_logs[-30:])
    if sys.platform == 'linux' and shutil.which('journalctl'):
        try:
            return run(["journalctl", "--user", "-u", UNIT, "-n", "30", "--no-pager"])
        except Exception:
            pass
    return "Belum ada log kamera."


def device_details():
    found = []
    try:
        output = run(['adb', 'devices', '-l'], timeout=15)
    except RuntimeError:
        return found
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        serial = fields[0]
        state = fields[1]
        if state not in ('device', 'unauthorized'):
            continue
        model = next((v[6:].replace('_', ' ').replace('SM_', 'SM ') for v in fields if v.startswith('model:')), 'HP Android')
        found.append(dict(serial=serial, name=model,
                          mode='usb' if any(v.startswith('usb:') for v in fields) else 'wifi',
                          authorized=(state == 'device')))
    return found


def parse_camera_modes(output):
    cameras = []
    current = None
    high_speed = False
    for line in output.splitlines():
        match = re.search(r'--camera-id=(\S+)\s+\((back|front|external),.*?fps=\{([^}]+)\}', line)
        if match:
            current = dict(id=match[1], facing=match[2], fps=[int(v.strip()) for v in match[3].split(',')], sizes=[])
            cameras.append(current)
            high_speed = False
        elif 'High speed capture' in line:
            high_speed = True
        elif current and not high_speed:
            match = re.match(r'\s+- (\d+x\d+)\s*$', line)
            if match:
                current['sizes'].append(match[1])
    return cameras


def camera_modes(serial):
    result = run(['scrcpy', '--serial=' + serial, '--list-camera-sizes'], timeout=15)
    modes = parse_camera_modes(result)
    if not modes:
        raise RuntimeError('Kemampuan kamera belum terbaca. Coba cari HP lagi.')
    return modes


def supported_fps(modes, facing, size):
    first = next((camera for camera in modes if camera['facing'] == facing), None)
    if not first or size not in first['sizes']:
        return []
    return [str(value) for value in (15, 30, 60) if value in first['fps']]
