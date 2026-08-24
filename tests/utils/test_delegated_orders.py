from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.limit_order import GTC
from tplus.model.market_order import MarketBaseQuantity
from tplus.utils.limit_order import create_limit_order_ob_request_payload
from tplus.utils.market_order import create_market_order_ob_request_payload
from tplus.utils.replace_order import create_replace_order_ob_request_payload
from tplus.utils.signing import create_cancel_order_ob_request_payload
from tplus.utils.user import DelegatedUser, User


def test_delegated_create_order_uses_additional_signer():
    account = User()
    signer = User()
    delegated = DelegatedUser(account.public_key, signer)

    request = create_limit_order_ob_request_payload(
        quantity=100,
        price=200,
        side="Buy",
        signer=delegated,
        book_quantity_decimals=2,
        book_price_decimals=2,
        asset_identifier=AssetIdentifier("1"),
        order_id="order-1",
        time_in_force=GTC(post_only=True),
    )

    assert request.order.signer == account.public_key
    assert request.signature == []
    assert request.additional_signers[0].signer.model_dump() == {"Ed25519": signer.public_key_vec}
    signer.vk.verify(
        bytes(request.additional_signers[0].signature),
        request.order.signable_part().encode(),
    )


def test_delegated_create_order_preserves_master_order_wire_shape(monkeypatch):
    account = User()
    delegated = DelegatedUser(account.public_key, User())
    monkeypatch.setattr("tplus.utils.limit_order.time.time_ns", lambda: 123)

    def build_request(signer: User):
        return create_limit_order_ob_request_payload(
            quantity=100,
            price=200,
            side="Buy",
            signer=signer,
            book_quantity_decimals=2,
            book_price_decimals=2,
            asset_identifier=AssetIdentifier("1"),
            order_id="order-1",
            time_in_force=GTC(post_only=True),
        )

    master_request = build_request(account)
    delegated_request = build_request(delegated)

    master_payload = master_request.model_dump(mode="json")
    delegated_payload = delegated_request.model_dump(mode="json")
    master_signature = master_payload.pop("signature")
    master_additional_signers = master_payload.pop("additional_signers")
    delegated_signature = delegated_payload.pop("signature")
    delegated_additional_signers = delegated_payload.pop("additional_signers")

    assert delegated_request.order.signable_part() == master_request.order.signable_part()
    assert delegated_payload == master_payload
    assert len(master_signature) == 64
    assert master_additional_signers == []
    assert delegated_signature == []
    assert len(delegated_additional_signers) == 1


def test_delegated_replace_uses_additional_signer():
    account = User()
    signer = User()
    delegated = DelegatedUser(account.public_key, signer)

    request = create_replace_order_ob_request_payload(
        original_order_id="order-1",
        asset_identifier=AssetIdentifier("1"),
        signer=delegated,
        new_price=300,
        new_quantity=100,
        book_price_decimals=2,
        book_quantity_decimals=2,
    )

    payload = request.model_dump(mode="json")
    [additional] = payload["additional_signers"]

    assert payload["signer"] == account.public_key
    assert payload["signature"] == []
    assert additional["signer"] == {"Ed25519": signer.public_key_vec}
    compact = (
        request.request.model_dump_json(exclude_none=False)
        .replace(" ", "")
        .replace("\r", "")
        .replace("\n", "")
    )
    signer.vk.verify(bytes(additional["signature"]), compact.encode())


def test_delegated_market_order_uses_additional_signer():
    account = User()
    signer = User()
    delegated = DelegatedUser(account.public_key, signer)

    request = create_market_order_ob_request_payload(
        side="Sell",
        signer=delegated,
        book_quantity_decimals=2,
        book_price_decimals=2,
        asset_identifier=AssetIdentifier("1"),
        order_id="order-2",
        base_quantity=MarketBaseQuantity(quantity=100, max_sellable_amount=None),
    )

    assert request.order.signer == account.public_key
    assert request.signature == []
    assert request.additional_signers[0].signer.model_dump() == {"Ed25519": signer.public_key_vec}
    signer.vk.verify(
        bytes(request.additional_signers[0].signature),
        request.order.signable_part().encode(),
    )


def test_delegated_cancel_uses_authenticated_account_without_additional_signers():
    account = User()
    delegated = DelegatedUser(account.public_key, User())

    request = create_cancel_order_ob_request_payload(
        signer=delegated,
        asset_identifier=AssetIdentifier("1"),
        order_id="order-1",
    )

    assert request.cancel.signer == account.public_key
    assert request.signature == []
    assert "additional_signers" not in request.model_dump(mode="json")
