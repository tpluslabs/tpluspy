"""Encrypted on-disk cache for short-lived bearer tokens.

Mirrors the keyfile envelope but with a cheaper KDF — a leaked cache file gives
at most one token-TTL of access, never the underlying signing key.
"""

import json
import os
from base64 import b64decode, b64encode
from hashlib import pbkdf2_hmac, sha3_256, sha256
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from tplus.utils.user.manager import PASSWORD_ENV_VAR

VERSION = 1
_KDF_ITERS = 10_000


def _derive(password: str, salt: bytes) -> bytes:
    return pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _KDF_ITERS, dklen=32)


def _mac(key: bytes, iv: bytes, ct: bytes) -> bytes:
    h = sha3_256()
    h.update(key[16:32] + iv + ct)
    return h.digest()


def encrypt(token: str, expiry_ns: int, base_url: str, password: str) -> dict:
    salt = os.urandom(16)
    iv = os.urandom(16)
    key = _derive(password, salt)
    cipher = Cipher(algorithms.AES(key[:16]), modes.CTR(iv), backend=default_backend())
    enc = cipher.encryptor()
    ct = enc.update(token.encode("utf-8")) + enc.finalize()
    return {
        "version": VERSION,
        "base_url": base_url,
        "expiry_ns": expiry_ns,
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": b64encode(iv).decode()},
            "ciphertext": b64encode(ct).decode(),
            "kdf": "pbkdf2",
            "kdfparams": {
                "salt": b64encode(salt).decode(),
                "iterations": _KDF_ITERS,
                "dklen": 32,
                "digest": "sha256",
            },
            "mac": b64encode(_mac(key, iv, ct)).decode(),
        },
    }


def decrypt(blob: dict, password: str) -> str:
    if blob.get("version") != VERSION:
        raise ValueError(f"unsupported cache version: {blob.get('version')!r}")

    crypto = blob["crypto"]
    salt = b64decode(crypto["kdfparams"]["salt"])
    iv = b64decode(crypto["cipherparams"]["iv"])
    ct = b64decode(crypto["ciphertext"])
    key = _derive(password, salt)
    if _mac(key, iv, ct) != b64decode(crypto["mac"]):
        raise ValueError("MAC mismatch: wrong password or corrupted cache")

    cipher = Cipher(algorithms.AES(key[:16]), modes.CTR(iv), backend=default_backend())
    dec = cipher.decryptor()
    return (dec.update(ct) + dec.finalize()).decode("utf-8")


def cache_path(cache_dir: Path, pubkey: str, base_url: str) -> Path:
    host = sha256(base_url.encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"{pubkey}-{host}.json"


def write_atomic(path: Path, blob: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def resolve_cache_password() -> str | None:
    return os.environ.get(PASSWORD_ENV_VAR)
