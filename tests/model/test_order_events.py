"""``/orders`` stream frames as the OMS actually serializes them.

The OMS publishes ``tplus_client::OrderEvent`` with serde's default *external*
enum tagging (``{"Removed": {...}}``); see
``tplus-rs-client/crates/tplus-client/src/order_event.rs`` and
``bin/order-management-system/src/ws_endpoints.rs::publish_order_event``. The
field sets below mirror ``orderbook_messages::events::*`` and
``orderbook_messages::actions::Order``.
"""

import pytest

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order import (
    OrderAmendedEvent,
    OrderAmendFailedEvent,
    OrderCancelFailedEvent,
    OrderCancelledEvent,
    OrderCreatedEvent,
    OrderCreateFailedEvent,
    OrderRemovedEvent,
    OrderReplacedEvent,
    OrderReplaceFailedEvent,
    OrderTriggeredEvent,
    OrderUpdatedEvent,
    parse_order_event,
)

USER = "0xeb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e"
OPERATOR = "37ec9d1ac1b0a9f0d1d9bbbd3b0ce7c6d5e3f7a3f6b1c2d3e4f5a6b7c8d9e0f1"
ORDER_ID = "emccyT7Dl3zKq0Yf4GcYyg=="


def _order_wire() -> dict:
    """``orderbook_messages::actions::Order`` as the OMS serializes it."""
    return {
        "user_order": {
            "signer": "ab" * 32,
            "order_id": ORDER_ID,
            "base_asset": "1",
            "book_price_decimals": 8,
            "book_quantity_decimals": 8,
            "details": {
                "Limit": {
                    "limit_price": 250_000_000_000,
                    "quantity": 4_300_000_000,
                    "time_in_force": {"GTC": {"post_only": True}},
                }
            },
            "side": "Sell",
            "trigger": None,
            "creation_timestamp_ns": 1_756_425_599_125_000_000,
            "target": {"account": 1, "is_spot": False},
            "reduce_only": False,
            "max_trading_fees_rate": 50_000,
            "protocol_version": 1,
        },
        "signature": [1, 2, 3],
        "book_timestamp_ns": 1_756_425_599_125_500_000,
        "limit_overrides": None,
        "limit_overrides_signature": None,
        "amend_overrides": None,
        "trigger_touched": None,
        "is_liquidation": False,
        "is_auto_deleverage": False,
        "additional_signers": [],
        "limit_overrides_additional_signers": [],
        "limit_overrides_book_timestamp_ns": None,
    }


def _removed_wire() -> dict:
    return {
        "order_id": ORDER_ID,
        "asset_id": "1",
        "user_id": USER,
        "timestamp_ns": 1_756_425_600_792_000_000,
        "operator_pubkey": OPERATOR,
        "reason": "Completed",
        "filled_quantity": 43,
        "filled_amount": 1_081,
        "confirmed_quantity": 43,
        "confirmed_amount": 1_081,
        "book_quantity_decimals": 8,
        "initial_receive_timestamp_ns": 1_756_425_599_125_000_000,
    }


def test_externally_tagged_removed_completed():
    event = parse_order_event({"Removed": _removed_wire()})

    assert isinstance(event, OrderRemovedEvent)
    assert event.event_type == "REMOVED"
    assert event.order_id == ORDER_ID
    assert event.asset_id == AssetIdentifier("1")
    assert event.reason == "Completed"
    assert event.filled_quantity == event.confirmed_quantity == 43
    assert event.initial_receive_timestamp_ns == 1_756_425_599_125_000_000


def test_externally_tagged_created_carries_the_full_book_order():
    event = parse_order_event({"Created": _order_wire()})

    assert isinstance(event, OrderCreatedEvent)
    assert event.order_id == ORDER_ID
    assert event.user_order.base_asset == AssetIdentifier("1")
    assert event.user_order.side.value == "Sell"
    assert event.user_order.details.quantity == 4_300_000_000
    assert event.signature == [1, 2, 3]
    assert event.is_liquidation is False


@pytest.mark.parametrize(
    ("variant", "payload", "model", "event_type"),
    [
        (
            "Replaced",
            {
                "order_id": ORDER_ID,
                "asset_id": "1",
                "user_id": USER,
                "new_quantity": 41,
                "new_price": 2_510,
                "timestamp_ns": 10,
                "authorization_revision": 10,
                "operator_pubkey": OPERATOR,
                "initial_receive_timestamp_ns": None,
            },
            OrderReplacedEvent,
            "REPLACED",
        ),
        (
            "Amended",
            {
                "order_id": ORDER_ID,
                "asset_id": "1",
                "user_id": USER,
                "new_quantity": 20,
                "remaining_quantity": 18,
                "authorization_revision": 11,
                "book_quantity_decimals": 8,
                "timestamp_ns": 11,
                "operator_pubkey": OPERATOR,
            },
            OrderAmendedEvent,
            "AMENDED",
        ),
        (
            "Triggered",
            {
                "order_id": ORDER_ID,
                "asset_id": "1",
                "user_id": USER,
                "timestamp_ns": 12,
                "quantity": 43,
                "trigger_touched": True,
                "operator_pubkey": OPERATOR,
            },
            OrderTriggeredEvent,
            "TRIGGERED",
        ),
        (
            "Canceled",
            {
                "order_id": ORDER_ID,
                "asset_id": "1",
                "user_id": USER,
                "timestamp_ns": 13,
                "operator_pubkey": OPERATOR,
                "initial_receive_timestamp_ns": 1,
            },
            OrderCancelledEvent,
            "CANCELED",
        ),
        (
            "CreateFailed",
            {"order_id": ORDER_ID, "user_id": USER},
            OrderCreateFailedEvent,
            "CREATEFAILED",
        ),
        (
            "ReplaceFailed",
            {"order_id": ORDER_ID, "user_id": USER},
            OrderReplaceFailedEvent,
            "REPLACEFAILED",
        ),
        (
            "AmendFailed",
            {"order_id": ORDER_ID, "user_id": USER},
            OrderAmendFailedEvent,
            "AMENDFAILED",
        ),
        (
            "CancelFailed",
            {"order_id": ORDER_ID, "user_id": USER},
            OrderCancelFailedEvent,
            "CANCELFAILED",
        ),
    ],
)
def test_every_rust_variant_parses(variant, payload, model, event_type):
    event = parse_order_event({variant: payload})

    assert isinstance(event, model)
    assert event.event_type == event_type
    assert event.order_id == ORDER_ID


def test_legacy_internally_tagged_shape_still_parses():
    removed = parse_order_event({"type": "removed", **_removed_wire()})
    assert isinstance(removed, OrderRemovedEvent)

    updated = parse_order_event(
        {
            "type": "updated",
            "order_id": ORDER_ID,
            "status": "Partial",
            "filled_quantity": 2,
            "remaining_quantity": 41,
            "update_timestamp_ns": 5,
        }
    )
    assert isinstance(updated, OrderUpdatedEvent)

    snake = parse_order_event({"type": "replace_failed", "order_id": ORDER_ID, "user_id": USER})
    assert isinstance(snake, OrderReplaceFailedEvent)


def test_unknown_or_malformed_frames_raise():
    with pytest.raises(ValueError, match="Unknown order event type"):
        parse_order_event({"type": "exploded"})
    with pytest.raises(ValueError, match="Invalid order event structure"):
        parse_order_event({"Exploded": {"order_id": ORDER_ID}})
    with pytest.raises(ValueError, match="Invalid order event structure"):
        parse_order_event({"Removed": "not-an-object"})
    with pytest.raises(ValueError, match="Invalid order event structure"):
        parse_order_event({"Removed": {}, "Created": {}})
    with pytest.raises(ValueError, match="Invalid order event structure"):
        parse_order_event([])


def test_removed_missing_required_field_raises_validation_error():
    payload = _removed_wire()
    del payload["reason"]
    with pytest.raises(ValueError):
        parse_order_event({"Removed": payload})
