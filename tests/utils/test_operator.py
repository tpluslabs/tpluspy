import hashlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, encode_dss_signature

from tplus.utils.operator import SECP256K1_HALF_ORDER, load_operator_sk, sign_operator_payload

OPERATOR_SECRET = "afa3fd40eafd3703780358990983f75930c87744455bf18a472012a04ae521ff"


def test_sign_operator_payload_verifies():
    sk = load_operator_sk(OPERATOR_SECRET)
    payload = b"10:20:1700000000000::"
    sig = bytes.fromhex(sign_operator_payload(payload, sk))
    der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    sk.public_key().verify(
        der, hashlib.sha256(payload).digest(), ec.ECDSA(Prehashed(hashes.SHA256()))
    )


def test_sign_operator_payload_low_s():
    sk = load_operator_sk(OPERATOR_SECRET)
    sig = bytes.fromhex(sign_operator_payload(b"payload", sk))
    s = int.from_bytes(sig[32:], "big")
    assert s <= SECP256K1_HALF_ORDER
