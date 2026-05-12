from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.order import (
    OrderRemovedEvent,
    parse_order_event,
)


def test_parse_order_removed_event_completed():
    payload = {
        "Removed": {
            "order_id": "rt6G7V8gRAG4p7lfidkeUw==",
            "asset_id": "82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@00000000000000a4b1",
            "user_id": "0xabc",
            "timestamp_ns": 1750146943779456128,
            "operator_pubkey": "0xdef",
            "reason": "Completed",
            "filled_quantity": 100,
            "filled_amount": 200,
            "confirmed_quantity": 100,
            "confirmed_amount": 200,
            "book_quantity_decimals": 8,
        }
    }

    event = parse_order_event(payload)

    assert isinstance(event, OrderRemovedEvent)
    assert event.event_type == "REMOVED"
    assert event.order_id == "rt6G7V8gRAG4p7lfidkeUw=="
    assert event.asset_id == AssetIdentifier(
        "82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@00000000000000a4b1"
    )
    assert event.user_id == "0xabc"
    assert event.timestamp_ns == 1750146943779456128
    assert event.operator_pubkey == "0xdef"
    assert event.reason == "Completed"
    assert event.filled_quantity == 100
    assert event.filled_amount == 200
    assert event.confirmed_quantity == 100
    assert event.confirmed_amount == 200
    assert event.book_quantity_decimals == 8


def test_parse_order_removed_event_canceled():
    payload = {
        "Removed": {
            "order_id": "abc",
            "asset_id": "82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@00000000000000a4b1",
            "user_id": "u",
            "timestamp_ns": 0,
            "operator_pubkey": "p",
            "reason": "Canceled",
            "filled_quantity": 0,
            "filled_amount": 0,
            "confirmed_quantity": 0,
            "confirmed_amount": 0,
            "book_quantity_decimals": 0,
        }
    }

    event = parse_order_event(payload)

    assert isinstance(event, OrderRemovedEvent)
    assert event.reason == "Canceled"
    assert event.filled_quantity == 0
