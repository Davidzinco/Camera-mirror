"""Short-lived invitations pinned to the sender's TLS certificate."""
import base64
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import re
import secrets
import ssl
import time


@dataclass(frozen=True)
class Invitation:
    host: str
    port: int
    fingerprint: str
    token: str

    def __post_init__(self):
        ip = ipaddress.IPv4Address(self.host)
        if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            raise ValueError('Gunakan alamat IPv4 komputer pengirim di jaringan lokal.')
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('Port tidak valid.')
        if not re.fullmatch(r'[0-9a-f]{64}', self.fingerprint):
            raise ValueError('Identitas sertifikat tidak valid.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', self.token):
            raise ValueError('Token pairing tidak valid.')

    def encode(self):
        data = json.dumps(self.__dict__, separators=(',', ':')).encode()
        return 'cm1:' + base64.urlsafe_b64encode(data).decode().rstrip('=')

    @classmethod
    def decode(cls, value):
        try:
            value = value.strip()
            if len(value) > 2048 or not value.startswith('cm1:'):
                raise ValueError()
            payload = value[4:]
            raw = base64.b64decode(payload + '=' * (-len(payload) % 4), altchars=b'-_', validate=True)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
            return cls(**data)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ValueError('Undangan tidak valid. Salin seluruh undangan dari pengirim.') from exc


class PairingGate:
    """One peer per session; monotonic expiry, bounded attempts, never reusable."""
    def __init__(self, ttl=300, attempts=5, clock=time.monotonic):
        self.token = secrets.token_urlsafe(32)
        self.clock = clock
        self.deadline = clock() + ttl
        self.attempts = attempts
        self.used = False

    def claim(self, token):
        if self.used or self.clock() >= self.deadline or self.attempts <= 0:
            return False
        if (not isinstance(token, str) or not token.isascii()
                or not secrets.compare_digest(token, self.token)):
            self.attempts -= 1
            return False
        self.used = True
        return True


def create_tls(directory):
    """Ephemeral identity, deleted after the session; no secrets in preferences."""
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Camera Mirror session')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    cert_path, key_path = Path(directory)/'cert.pem', Path(directory)/'key.pem'
    with key_path.open('xb') as handle:
        key_path.chmod(0o600)
        handle.write(key.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_path, key_path)
    pin = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return context, pin
