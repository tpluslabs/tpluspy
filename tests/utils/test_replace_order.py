import json

import pytest

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order_trigger import TriggerAbove, TriggerBelow
from tplus.utils.replace_order import create_replace_order_ob_request_payload
from tplus.utils.user import User

TRIGGER_PRICE = 42


@pytest.fixture(scope="session")
def signer() -> User:
    return User()


@pytest.mark.parametrize(
    "new_trigger, condition",
    [
        pytest.param(
            TriggerAbove(price=TRIGGER_PRICE),
            {"PriceAbove": {"price": TRIGGER_PRICE}},
            id="above",
        ),
        pytest.param(
            TriggerBelow(price=TRIGGER_PRICE),
            {"PriceBelow": {"price": TRIGGER_PRICE}},
            id="below",
        ),
        pytest.param(None, None, id="none"),
    ],
)
def test_create_replace_order_ob_request_payload_signs_the_trigger_direction(
    signer, new_trigger, condition
):
    payload = create_replace_order_ob_request_payload(
        original_order_id="order-1",
        asset_identifier=AssetIdentifier("1"),
        signer=signer,
        new_price=TRIGGER_PRICE,
        new_quantity=100,
        book_price_decimals=2,
        book_quantity_decimals=2,
        new_trigger=new_trigger,
        request_timestamp_ns=1,
    )
    signed_text = payload.request.model_dump_json()

    assert json.loads(signed_text)["new_trigger"] == condition
    signer.vk.verify(bytes(payload.signature), signed_text.encode())
