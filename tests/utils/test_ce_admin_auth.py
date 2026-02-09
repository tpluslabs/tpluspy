"""
Integration tests for CE admin auth signature computation (secp256k1 ECDSA).

Signs requests in Python and submits them to a running Clearing Engine,
verifying the Rust side accepts our signatures.

Mirrors the Rust implementation in:
  bin/clearing-engine/src/permissionless/routes/auth.rs
"""

import hashlib
import time

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, decode_dss_signature

SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_HALF_ORDER = SECP256K1_ORDER // 2

CE_URL = "http://127.0.0.1:3032"
OPERATOR_SECRET = "afa3fd40eafd3703780358990983f75930c87744455bf18a472012a04ae521ff"


def _load_operator_sk() -> ec.EllipticCurvePrivateKey:
    secret_bytes = bytes.fromhex(OPERATOR_SECRET)
    return ec.derive_private_key(int.from_bytes(secret_bytes, "big"), ec.SECP256K1())


def _sign(payload: bytes, sk: ec.EllipticCurvePrivateKey) -> str:
    """SHA256 -> ECDSA sign -> low-S normalize -> compact r||s -> hex."""
    digest = hashlib.sha256(payload).digest()
    sig_der = sk.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
    r, s = decode_dss_signature(sig_der)
    if s > SECP256K1_HALF_ORDER:
        s = SECP256K1_ORDER - s
    return (r.to_bytes(32, "big") + s.to_bytes(32, "big")).hex()


@pytest.mark.integration
class TestCeAdminAuth:
    def test_set_primary_request(self):
        """Sign a SetPrimaryRequest and POST to /rotation/fetch."""
        sk = _load_operator_sk()
        ts = time.time_ns()
        payload = ts.to_bytes(8, "big") + b"\x01"
        sig = _sign(payload, sk)

        resp = httpx.post(
            f"{CE_URL}/rotation/fetch",
            json={"inner": {"primary": True, "timestamp_ns": ts}, "signature": sig},
            timeout=5,
        )
        assert resp.status_code == 200

    def test_modify_user_status_request(self):
        """Sign a ModifyUserStatusRequest and POST to /admin/status/modify."""
        sk = _load_operator_sk()
        ts = time.time_ns()
        user_pubkey = bytes(range(32))
        payload = ts.to_bytes(8, "big") + user_pubkey + b"\x01"
        sig = _sign(payload, sk)

        resp = httpx.post(
            f"{CE_URL}/admin/status/modify",
            json={
                "inner": {
                    "user": user_pubkey.hex(),
                    "is_mm": True,
                    "timestamp_ns": ts,
                },
                "signature": sig,
            },
            timeout=5,
        )
        assert resp.status_code == 200
