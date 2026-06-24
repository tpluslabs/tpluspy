"""Tests for BlockchainClient.sync_vault_events.

The operator-signature scheme mirrors the Rust verifier in
lib/blockchain-client-utils/src/operator_auth.rs (`verify_operator_signature`).
"""

import asyncio
import hashlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, encode_dss_signature

from tplus.utils.operator import load_operator_sk


def _verify(operator_secret: str, payload: bytes, signature_hex: str) -> bool:
    pubkey = load_operator_sk(operator_secret).public_key()
    sig = bytes.fromhex(signature_hex)
    der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    try:
        pubkey.verify(der, hashlib.sha256(payload).digest(), ec.ECDSA(Prehashed(hashes.SHA256())))
        return True
    except Exception:
        return False


def test_sync_vault_events_signed(blockchain_client, operator_secret):
    asyncio.run(
        blockchain_client.sync_vault_events(
            10,
            20,
            address="0x1234567890123456789012345678901234567890",
            events=["0x" + "11" * 32],
            operator_secret=operator_secret,
            timestamp_ms=1_700_000_000_000,
        )
    )

    post = blockchain_client._post
    post.assert_awaited_once()
    assert post.await_args.args[0] == "historical_logs"
    assert post.await_args.kwargs["requires_auth"] is False

    body = post.await_args.kwargs["json_data"]
    assert body["from_block"] == 10
    assert body["to_block"] == 20
    assert body["timestamp"] == 1_700_000_000_000
    assert body["address"] == "0x1234567890123456789012345678901234567890"
    assert body["events"] == ["0x" + "11" * 32]

    events_str = ",".join(body["events"])
    payload = f"{body['from_block']}:{body['to_block']}:{body['timestamp']}:{body['address']}:{events_str}".encode()
    assert _verify(operator_secret, payload, body["signature"])


def test_sync_vault_events_unsigned(blockchain_client):
    asyncio.run(blockchain_client.sync_vault_events(0, 100, timestamp_ms=1_700_000_000_000))

    body = blockchain_client._post.await_args.kwargs["json_data"]
    assert body["signature"] == ""
    assert "address" not in body
    assert "events" not in body
