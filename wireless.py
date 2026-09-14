"""Wireless setup and reconnection, restricted to devices the user enrolled."""
import ipaddress
import re
import shutil
import subprocess
import time

import backend as api
import preferences


def identity(address):
    value = api.run(['adb', '-s', address, 'shell', 'getprop', 'ro.serialno'], timeout=5).strip()
    if not value or value.lower() == 'unknown':
        raise RuntimeError('Identitas HP belum terbaca. Izinkan USB debugging di HP.')
    return value


def connect_checked(address, expected=None):
    api.endpoint(address)
    api.run(['adb', 'connect', address], timeout=6)
    actual = identity(address)
    if expected and actual != expected:
        raise RuntimeError('Alamat jaringan ini bukan HP yang disimpan. Pilih Hubungkan HP lagi.')
    return actual


def setup_usb(device):
    serial = device['serial']
    if device['mode'] != 'usb': raise ValueError('Hubungkan kabel USB terlebih dahulu.')
    physical = identity(serial)
    network = api.run(['adb', '-s', serial, 'shell', 'ip', '-o', '-4', 'addr', 'show', 'wlan0'])
    match = re.search(r'\binet\s+(\d+\.\d+\.\d+\.\d+)/', network)
    if not match: raise RuntimeError('Sambungkan HP ke Wi-Fi yang sama dengan komputer, lalu coba lagi.')
    host = str(ipaddress.ip_address(match.group(1)))
    address = host + ':5555'
    api.run(['adb', '-s', serial, 'tcpip', '5555'])
    error = None
    for attempt in range(4):
        time.sleep(.5)
        try:
            connect_checked(address, physical)
            preferences.remember(physical, address, device['name'])
            return address
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            error = exc
    raise RuntimeError('Belum bisa terhubung lewat Wi-Fi. Pastikan HP dan komputer berada di jaringan yang sama.\n'+str(error))


def parse_services(output, kind):
    services = []
    for line in output.splitlines():
        parts = line.split(';')
        if len(parts) < 9 or parts[0] != '=' or parts[4] != kind: continue
        try:
            host = ipaddress.ip_address(parts[7])
            if host.version != 4: continue
            address = api.endpoint(f'{host}:{parts[8]}')
        except ValueError: continue
        entry = dict(name=parts[3], address=address)
        if entry not in services: services.append(entry)
    return services


def discover(kind='_adb-tls-connect._tcp', timeout=4):
    if not shutil.which('avahi-browse'): return []
    try:
        result = subprocess.run(['avahi-browse', '-rtp', kind],
                                capture_output=True, text=True, timeout=timeout)
        output = result.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b''
        if isinstance(output, bytes): output = output.decode(errors='replace')
    return parse_services(output, kind)


def reconnect(connected):
    """Never enable network debugging or start a camera during discovery."""
    saved = preferences.load()
    if not saved['auto_connect']: return None
    known = saved['wireless']
    connected_serials = {d['serial'] for d in connected}
    # ADB keys authenticate endpoints; also verify the enrolled hardware identity.
    for item in known:
        address, physical = item.get('address'), item.get('serial')
        if not address or not physical: continue
        if address in connected_serials: return address
        try:
            connect_checked(address, physical)
            return address
        except (ValueError, RuntimeError, subprocess.TimeoutExpired): pass
    if not known: return None
    for service in discover() + discover('_adb._tcp'):
        for item in known:
            if not item.get('serial'): continue
            if (item.get('service') != service['name'] and
                    not service['name'].startswith('adb-'+item['serial']+'-')): continue
            try:
                connect_checked(service['address'], item['serial'])
                preferences.remember(item['serial'], service['address'], item.get('name', 'HP Android'), service['name'])
                return service['address']
            except (ValueError, RuntimeError, subprocess.TimeoutExpired): pass
    return None
