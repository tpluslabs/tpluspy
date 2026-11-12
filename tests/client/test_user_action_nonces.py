import json
from unittest.mock import AsyncMock, patch

import pytest

from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.user import DelegatedUser, User


def test_subaccount_transfer_builder_signs_nonce():
    user = User()
    client = OrderBookClient(default_user=user)

    payload = client._build_transfer_request(
        0,
        1,
        AssetIdentifier("200"),
        1234,
        nonce=42,
        user=user,
    )

    assert payload["inner"]["nonce"] == 42
    assert len(payload["signature"]) == 64


def test_close_position_builder_signs_nonce():
    user = User()
    client = OrderBookClient(default_user=user)

    payload = client._build_close_position_request(1, "200", nonce=43, user=user)

    assert payload["inner"]["nonce"] == 43
    assert len(payload["signature"]) == 64


def test_delegated_subaccount_transfer_targets_account_and_adds_signer():
    account = User()
    signer = User()
    delegated = DelegatedUser(account.public_key, signer)
    client = OrderBookClient(default_user=delegated)

    payload = client._build_transfer_request(
        0,
        1,
        AssetIdentifier("200"),
        1234,
        nonce=44,
        user=delegated,
    )

    assert payload["inner"]["user"] == account.public_key
    assert payload["inner"]["nonce"] == 44
    assert payload["signature"] == []
    assert payload["additional_signers"][0]["signer"] == {"Ed25519": signer.public_key_vec}
    signer.vk.verify(
        bytes(payload["additional_signers"][0]["signature"]),
        json.dumps(payload["inner"], separators=(",", ":")).encode(),
    )


def test_delegated_close_position_targets_account_and_adds_signer():
    account = User()
    signer = User()
    delegated = DelegatedUser(account.public_key, signer)
    client = OrderBookClient(default_user=delegated)

    payload = client._build_close_position_request(
        1,
        "200",
        nonce=45,
        user=delegated,
    )

    assert payload["inner"]["user"] == account.public_key
    assert payload["inner"]["nonce"] == 45
    assert payload["signature"] == []
    assert payload["additional_signers"][0]["signer"] == {"Ed25519": signer.public_key_vec}
    signer.vk.verify(
        bytes(payload["additional_signers"][0]["signature"]),
        json.dumps(payload["inner"], separators=(",", ":")).encode(),
    )


def test_custody_repayment_signs_exact_fields_and_supports_delegation():
    owner = User()
    signer = User()
    for user in (owner, DelegatedUser(owner.public_key, signer)):
        client = OrderBookClient(default_user=user)
        payload = client._build_custody_repayment(0, "token", 12, nonce=42)
        assert list(payload["inner"]) == ["user", "repayment", "nonce"]
        assert payload["inner"]["repayment"] == {
            "source": "Funding",
            "asset": "token",
            "amount": "12",
        }
        assert payload["inner"]["nonce"] == 42
        if isinstance(user, DelegatedUser):
            signature = payload["additional_signers"][0]["signature"]
            key = signer.vk
        else:
            signature = payload["signature"]
            key = owner.vk
        key.verify(bytes(signature), json.dumps(payload["inner"], separators=(",", ":")).encode())


@pytest.mark.asyncio
async def test_custody_repayment_posts_signed_payload_and_returns_ce_amounts():
    user = User()
    client = OrderBookClient(default_user=user)
    reply = {"success": True, "repaid": "12", "remaining_liability": "3"}
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=reply) as post:
        assert await client.request_custody_repayment(0, "token", 12, nonce=42) == reply
    args = post.call_args
    assert args.args == ("/account/transfer/custody-repayment",)
    payload = args.kwargs["json_data"]
    user.vk.verify(
        bytes(payload["signature"]), json.dumps(payload["inner"], separators=(",", ":")).encode()
    )
