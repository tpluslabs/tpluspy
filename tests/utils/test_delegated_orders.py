from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.limit_order import GTC
from tplus.utils.limit_order import create_limit_order_ob_request_payload
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


def test_delegated_replace_and_cancel_use_target_account_without_master_signature():
    account = User()
    delegated = DelegatedUser(account.public_key, User())
    asset = AssetIdentifier("1")

    replace = create_replace_order_ob_request_payload(
        original_order_id="order-1",
        asset_identifier=asset,
        signer=delegated,
        new_price=300,
    )
    cancel = create_cancel_order_ob_request_payload(
        signer=delegated,
        asset_identifier=asset,
        order_id="order-1",
    )

    assert replace.user_id == account.public_key
    assert replace.signature == []
    assert cancel.cancel.signer == account.public_key
    assert cancel.signature == []
