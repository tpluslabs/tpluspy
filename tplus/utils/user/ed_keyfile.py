"""
Inspired from eth-keyfile.
"""

import json
import os
from base64 import b64decode, b64encode
from hashlib import pbkdf2_hmac, sha3_256

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _compute_mac(derived_key: bytes, ciphertext: bytes) -> bytes:
    """
    Same pattern as eth-keyfile: MAC = keccak256(derived_key[16:32] + ciphertext)
    """
    hasher = sha3_256()
    hasher.update(derived_key[16:32] + ciphertext)
    return hasher.digest()


def encrypt_keyfile(
    private_key_bytes: bytes, password: str, outfile: str, kdf_iterations: int = 262144
):
    if not isinstance(password, str):
        raise TypeError("Password must be a string")

    salt = os.urandom(16)
    iv = os.urandom(16)

    # Derive 32 bytes so we can split into encrypt key + MAC key
    derived_key = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, kdf_iterations, dklen=32)

    # AES-128-CTR uses first 16 bytes
    encrypt_key = derived_key[:16]

    cipher = Cipher(algorithms.AES(encrypt_key), modes.CTR(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(private_key_bytes) + encryptor.finalize()

    # Compute MAC
    mac = _compute_mac(derived_key, ciphertext)

    # Build JSON
    keyfile = {
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": b64encode(iv).decode()},
            "ciphertext": b64encode(ciphertext).decode(),
            "kdf": "pbkdf2",
            "kdfparams": {
                "salt": b64encode(salt).decode(),
                "iterations": kdf_iterations,
                "dklen": 32,
                "digest": "sha256",
            },
            "mac": b64encode(mac).decode(),
        }
    }

    with open(outfile, "w") as f:
        json.dump(keyfile, f, indent=2)

    print(f"Encrypted keyfile saved to {outfile}")


def decrypt_keyfile(password: str, infile: str) -> bytes:
    with open(infile) as f:
        keyfile = json.load(f)

    crypto = keyfile["crypto"]
    kdfparams = crypto["kdfparams"]
    cipherparams = crypto["cipherparams"]

    salt = b64decode(kdfparams["salt"])
    iv = b64decode(cipherparams["iv"])
    ciphertext = b64decode(crypto["ciphertext"])
    iterations = kdfparams["iterations"]
    dklen = kdfparams["dklen"]
    stored_mac = b64decode(crypto["mac"])

    # Derive key
    derived_key = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=dklen)
    encrypt_key = derived_key[:16]

    # Verify MAC
    computed_mac = _compute_mac(derived_key, ciphertext)
    if computed_mac != stored_mac:
        raise ValueError("MAC mismatch: wrong password or corrupted file")

    # Decrypt
    cipher = Cipher(algorithms.AES(encrypt_key), modes.CTR(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    return plaintext
