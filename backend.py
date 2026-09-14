"""Command layer for Camera Mirror. All commands run without a shell."""
import ipaddress
import re
import subprocess

UNIT = "android-webcam"


def run(args, timeout=25, input_text=None):
    result = subprocess.run(args, input=input_text, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
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
    output = run(["adb", "devices", "-l"])
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


def camera_command(serial, facing, size, fps, preview=False):
    if not serial or serial.startswith("-") or any(c.isspace() for c in serial):
        raise ValueError("Pilih perangkat yang sudah terhubung.")
    if facing not in ("back", "front") or size not in ("1280x720", "1920x1080") or fps not in ("15", "30", "60"):
        raise ValueError("Pengaturan kamera tidak valid.")
    args = ["/usr/bin/scrcpy", "--serial=" + serial, "--video-source=camera",
            "--camera-facing=" + facing, "--camera-size=" + size, "--camera-fps=" + fps,
            "--v4l2-sink=/dev/video10", "--no-audio", "--video-codec=h264",
            "--video-buffer=0", "--v4l2-buffer=0"]
    args += ["--window-title=Camera Mirror"] if preview else ["--no-window"]
    return args


def active():
    result = subprocess.run(["systemctl", "--user", "is-active", UNIT],
                            text=True, capture_output=True, timeout=5)
    return result.returncode == 0


def stop():
    run(["systemctl", "--user", "stop", UNIT])


def logs():
    return run(["journalctl", "--user", "-u", UNIT, "-n", "30", "--no-pager"])


def device_details():
    found = []
    for line in run(['adb', 'devices', '-l'], timeout=5).splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[1] != 'device': continue
        serial = fields[0]
        model = next((v[6:].replace('_', ' ').replace('SM_', 'SM ') for v in fields if v.startswith('model:')), 'HP Android')
        found.append(dict(serial=serial, name=model,
                          mode='usb' if any(v.startswith('usb:') for v in fields) else 'wifi'))
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
            if match: current['sizes'].append(match[1])
    return cameras


def camera_modes(serial):
    result = run(['scrcpy', '--serial='+serial, '--list-camera-sizes'], timeout=15)
    modes = parse_camera_modes(result)
    if not modes: raise RuntimeError('Kemampuan kamera belum terbaca. Coba cari HP lagi.')
    return modes


def supported_fps(modes, facing, size):
    first = next((camera for camera in modes if camera['facing'] == facing), None)
    if not first or size not in first['sizes']: return []
    return [str(value) for value in (15, 30, 60) if value in first['fps']]
