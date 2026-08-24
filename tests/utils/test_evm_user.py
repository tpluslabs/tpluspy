import pytest
from eth_keys import KeyAPI
from eth_utils import keccak

from tplus.model.multisig import SignerKey
from tplus.utils.user import EvmDelegatedUser
from tplus.utils.user.evm import (
    EIP191_PREFIX,
    derive_legacy_signer_key,
    recover_signer_key,
)
from tplus.utils.user.model import sign_master_key_message

ACCOUNT_ID = "ab" * 32


@pytest.fixture
def master_key_signature(eth_account):
    return sign_master_key_message(eth_account)


def verify_like_backend(pubkey: bytes, message: str, signature: list[int]) -> bool:
    """Re-run the T+ ``verify_secp256k1_eip191`` path against a signed payload."""
    body = message.encode("utf-8")
    prehash = keccak(EIP191_PREFIX + str(len(body)).encode("ascii") + body)
    raw = bytes(signature)
    recovery_id = raw[64] - 27 if raw[64] >= 27 else raw[64]
    sig = KeyAPI().Signature(signature_bytes=raw[:64] + bytes([recovery_id]))
    return KeyAPI().ecdsa_recover(prehash, sig).to_compressed_bytes() == pubkey


def test_recover_signer_key_matches_wallet_key(eth_account, master_key_signature):
    # T+ registers the wallet's own key, so recovery must land on exactly that key.
    expected = KeyAPI().PrivateKey(bytes(eth_account.key)).public_key
    assert recover_signer_key(master_key_signature) == expected.to_compressed_bytes()


def test_derive_legacy_signer_key_differs_from_wallet_key(master_key_signature):
    legacy = derive_legacy_signer_key(master_key_signature)
    assert len(legacy) == 33
    assert legacy != recover_signer_key(master_key_signature)


class TestEvmDelegatedUser:
    def test_signing_parts_produces_a_signature_tplus_accepts(self, eth_account):
        user = EvmDelegatedUser(ACCOUNT_ID, eth_account)
        payload = '{"order_id": "abc", "quantity": 5}'

        master, additional = user.signing_parts(payload)

        assert master == []
        signer_key = additional[0].signer
        assert signer_key.variant == "Secp256k1"
        assert bytes(signer_key.key_bytes) == user.signer_key
        # T+ verifies against the whitespace-stripped payload, not what was passed in.
        assert verify_like_backend(
            user.signer_key, payload.replace(" ", ""), additional[0].signature
        )

    def test_acts_for_the_account_not_the_wallet(self, eth_account, eth_user):
        user = EvmDelegatedUser(ACCOUNT_ID, eth_account)
        assert user.public_key == ACCOUNT_ID
        assert user.public_key != eth_user.public_key
        assert user.evm_address == eth_account.address

    def test_has_no_master_key(self, eth_account):
        user = EvmDelegatedUser(ACCOUNT_ID, eth_account)
        with pytest.raises(ValueError, match="cannot produce master signatures"):
            user.sign("payload")

    def test_rejects_invalid_account_public_key(self, eth_account):
        with pytest.raises(ValueError, match="account_public_key"):
            EvmDelegatedUser("nope", eth_account)


def test_signed_requests_carry_the_wallet_cosignature(eth_account):
    """Requests a wallet account signs travel as co-signatures, not master signatures."""
    from tplus.model.asset_identifier import AssetAddress
    from tplus.model.withdrawal import WithdrawalRequest

    user = EvmDelegatedUser(ACCOUNT_ID, eth_account)
    asset = AssetAddress.from_evm_address("0x" + "12" * 20, chain_id=1)

    request = WithdrawalRequest.create_signed(signer=user, asset=asset, amount=5, nonce=1)

    assert request.inner.tplus_user == ACCOUNT_ID
    assert request.signature == []
    signer_key = request.additional_signers[0].signer
    assert signer_key == SignerKey.secp256k1(list(user.signer_key))
    assert verify_like_backend(
        user.signer_key,
        request.signing_payload().replace(" ", ""),
        request.additional_signers[0].signature,
    )
