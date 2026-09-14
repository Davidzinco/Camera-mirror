"""Small, atomic user preferences. Pairing secrets never enter this file."""
import json
import os
from pathlib import Path
import threading

_LOCK = threading.RLock()
DEFAULTS = dict(mode='usb', facing='back', size='1920x1080', fps='30', auto_connect=True,
                wireless=[], last_device='', screen_off=False)


def path():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'camera-mirror'/'preferences.json'


def load():
    with _LOCK:
        try:
            saved = json.loads(path().read_text())
            if not isinstance(saved, dict): saved = {}
        except (OSError, ValueError): saved = {}
        result = dict(DEFAULTS)
        result.update({key: value for key, value in saved.items() if key in DEFAULTS})
        if not isinstance(result['wireless'], list): result['wireless'] = []
        result['wireless'] = [item for item in result['wireless'] if isinstance(item, dict)]
        return result


def save(**changes):
    with _LOCK:
        state = load()
        state.update({key: value for key, value in changes.items() if key in DEFAULTS})
        file = path()
        file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = file.with_suffix('.tmp')
        temp.write_text(json.dumps(state, indent=2))
        temp.chmod(0o600)
        temp.replace(file)


def remember(serial, address, name, service=''):
    with _LOCK:
        devices = [item for item in load()['wireless'] if item.get('serial') != serial]
        devices.append(dict(serial=serial, address=address, name=name, service=service))
        save(wireless=devices[-8:])
