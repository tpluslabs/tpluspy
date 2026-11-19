import asyncio

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, encode_dss_signature

from tplus.client.clearingengine import ClearingEngineClient
from tplus.client.clearingengine.approval_durations import (
    SET_APPROVAL_DURATIONS_DOMAIN,
    build_set_approval_durations_request,
)
from tplus.model.approval_durations import (
    ApprovalDurationChainMap,
    ApprovalDurations,
    SetApprovalDurationsRequest,
)
from tplus.model.council import committee_hash, council_digest
from tplus.model.types import ChainID
from tplus.utils.operator import load_operator_signers, load_operator_sk


@pytest.fixture(scope="session")
def durations() -> ApprovalDurationChainMap:
    return ApprovalDurationChainMap(
        per_chain={
            ChainID.from_parts(1, 5): ApprovalDurations(withdrawal_secs=300, settlement_secs=20),
            ChainID.evm(42_161): ApprovalDurations(withdrawal_secs=180, settlement_secs=15),
            ChainID.evm(1): ApprovalDurations(withdrawal_secs=240, settlement_secs=40),
        }
    )


@pytest.fixture
def council_send(mocker):
    """A ClearingEngineClient whose ``_send`` rejects the window twice, then accepts."""
    client = ClearingEngineClient(base_url="http://127.0.0.1:3032")
    rejection = httpx.Response(400, text="min_seq 0 below last_accepted_max 41")
    send = mocker.patch.object(
        client,
        "_send",
        new=mocker.AsyncMock(side_effect=[rejection, rejection, httpx.Response(200)]),
    )
    return client, send


def test_to_bincode_matches_rust(durations):
    rust_vector = (
        (1).to_bytes(8, "little")
        + b"\x00"
        + (1).to_bytes(8, "big")
        + (240).to_bytes(8, "little")
        + (40).to_bytes(8, "little")
    )
    mainnet = ChainID.evm(1)
    single_chain = ApprovalDurationChainMap(per_chain={mainnet: durations.per_chain[mainnet]})
    assert single_chain.to_bincode() == rust_vector

    encoded = durations.to_bincode()
    assert encoded[:8] == (3).to_bytes(8, "little")
    chain_ids = [encoded[offset : offset + 9] for offset in range(8, len(encoded), 25)]
    assert chain_ids == [chain_id.to_bytes() for chain_id in sorted(durations.per_chain)]
    assert [ChainID(chain_id.hex()).routing_id for chain_id in chain_ids] == [0, 0, 1]


def test_build_set_approval_durations_request_signs_the_encoded_map(durations, operator_secret):
    signers = load_operator_signers([operator_secret])
    request = build_set_approval_durations_request(durations, signers, 1, 7, 9)

    body = request.model_dump(mode="json")
    assert body["payload"]["min_seq"] == 7
    assert body["payload"]["committee_hash"] == committee_hash(list(signers), 1).hex()
    assert body["payload"]["approval_durations"]["per_chain"]["00000000000000a4b1"] == {
        "withdrawal_secs": 180,
        "settlement_secs": 15,
    }
    assert SetApprovalDurationsRequest.model_validate(body) == request
    digest = council_digest(request.payload, SET_APPROVAL_DURATIONS_DOMAIN, durations.to_bincode())
    [sig] = request.sigs
    assert sig.signer == next(iter(signers))
    signature = bytes.fromhex(sig.signature)
    load_operator_sk(operator_secret).public_key().verify(
        encode_dss_signature(
            int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
        ),
        digest,
        ec.ECDSA(Prehashed(hashes.SHA256())),
    )


def test_post_council_request_chases_the_anchor(council_send):
    client, send = council_send
    windows = []

    def build_request(min_seq: int, max_seq: int) -> dict:
        windows.append((min_seq, max_seq))
        return {}

    asyncio.run(client.post_council_request("approval-durations/set", build_request))

    assert windows == [(0, 0), (41, 41), (42, 42)]
    assert send.await_count == 3
