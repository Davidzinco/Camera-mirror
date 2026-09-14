"""Limited privileged helper, invoked by the GUI through the desktop password dialog."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    if os.geteuid() != 0:
        raise RuntimeError("Penyiapan perangkat membutuhkan hak administrator.")
    ctl = shutil.which("v4l2loopback-ctl")
    if not ctl:
        raise RuntimeError("Pasang dahulu di terminal: sudo pacman -S --needed v4l2loopback-utils")
    subprocess.run(["/usr/bin/modprobe", "v4l2loopback", "devices=0"], check=True)
    for number, label in ((10, "Android Webcam"), (11, "OBS Virtual Camera")):
        device = Path(f"/dev/video{number}")
        if device.exists():
            name = Path(f"/sys/class/video4linux/video{number}/name").read_text().strip()
            if name != label:
                raise RuntimeError(f"{device} sudah dipakai oleh {name}; tidak diubah.")
        else:
            subprocess.run([ctl, "add", "-n", label, "-x", "1", str(device)], check=True)
        print(f"{device}: {label} siap.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
