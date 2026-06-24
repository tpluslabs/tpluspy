from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.user import User


def test_subaccount_transfer_builder_signs_nonce():
    user = User()
    client = OrderBookClient(default_user=user)

    payload = client._build_transfer_to_subaccount(
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
