import json
from typing import Any

import pytest
from pydantic import ValidationError

from tplus.model.asset_identifier import AssetAddress, AssetIdentifier
from tplus.model.order import Order, Side, TradeTarget
from tplus.model.sync_order import (
    SyncGTC,
    SyncGTD,
    SyncMakerOrderDetails,
    SyncSettlementTerms,
    SyncTakerOrderDetails,
)
from tplus.model.sync_settlement import (
    SyncSettlementApproved,
    SyncSettlementFailure,
    parse_sync_settlement_event,
)
from tplus.model.types import ChainID
from tplus.utils.limit_order import (
    create_sync_maker_order_ob_request_payload,
    create_sync_taker_order_ob_request_payload,
)
from tplus.utils.user import User

CHAIN_ID = ChainID.evm(31337)
WETH = AssetAddress.from_str(
    "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000007a69"
)


def test_sync_taker_details_serialize_like_the_rust_variant():
    details = SyncTakerOrderDetails(
        limit_price=10_000,
        quantity=1_000,
        settlement=SyncSettlementTerms(base_token=WETH, nonce=3),
    )
    dumped = details.model_dump()
    assert dumped == {
        "SyncTaker": {
            "limit_price": 10_000,
            "quantity": 1_000,
            "settlement": {"base_token": str(WETH), "nonce": 3},
        }
    }
    assert SyncTakerOrderDetails.model_validate(dumped) == details


def test_sync_taker_order_round_trips_through_order():
    request = create_sync_taker_order_ob_request_payload(
        quantity=1_000,
        price=10_000,
        side="Sell",
        signer=User(),
        book_quantity_decimals=4,
        book_price_decimals=2,
        asset_identifier=AssetIdentifier("1"),
        order_id="sync-1",
        base_token=WETH,
        nonce=0,
    )
    payload = json.loads(request.order.signable_part())
    assert payload["details"]["SyncTaker"]["settlement"]["base_token"] == str(WETH)
    parsed = Order.model_validate(payload)
    assert isinstance(parsed.details, SyncTakerOrderDetails)
    assert len(request.signature) == 64


def test_parse_sync_settlement_events():
    user = User().public_key
    approved = {
        "asset": "1",
        "maker_quotes": [
            {"order_id": "mm-a", "trade_id": None},
            {"order_id": "mm-b", "trade_id": 7},
        ],
        "tplus_user": user,
        "sub_account_index": 1,
        "settler": user,
        "mode": "margin",
        "asset_in": "11" * 32,
        "amount_in": "100000000",
        "asset_out": "22" * 32,
        "amount_out": "1000000000000000000",
        "chain_id": CHAIN_ID,
        "approval": {
            "inner": {"nonce": 0, "signature": "0xab"},
            "expiry": 10,
            "chain_id": CHAIN_ID,
            "amount_in": "100000000",
            "amount_out": "1000000000000000000",
            "conversion": {
                "canonical_per_representation": "1000000000000000000",
                "state_id": "0x00",
                "canonical_amount": "1000000000000000000",
                "representation_amount": "1000000000000000000",
                "chain_amount": "1000000000000000000",
                "representation_remainder": "0",
            },
        },
        "timestamp_ns": 1,
    }
    event = parse_sync_settlement_event(approved)
    assert isinstance(event, SyncSettlementApproved)
    assert event.amount_in == 100_000_000
    assert event.approval.inner.nonce == 0
    assert event.approval.amount_in == 100_000_000
    assert event.approval.amount_out == 1_000_000_000_000_000_000
    assert [(q.order_id, q.trade_id) for q in event.maker_quotes] == [
        ("mm-a", None),
        ("mm-b", 7),
    ], "trade id 7 belongs to mm-b, not to the quote before it"


def test_parse_sync_settlement_failure():
    """A failure is told from an approval by its reason (v0) or its channel (v1)."""
    taker_view: dict[str, Any] = {
        "asset": "1",
        "taker_order_id": "sync-taker",
        "maker_quotes": [],
        "reason": "sync_settlement_expired",
        "details": None,
        "timestamp_ns": 1,
    }

    event = parse_sync_settlement_event(taker_view)
    assert isinstance(event, SyncSettlementFailure)
    assert event.taker_order_id == "sync-taker"
    assert event.reason == "sync_settlement_expired"
    assert not event.counterparty_at_fault

    enveloped = parse_sync_settlement_event(
        {"type": "event", "channel": "sync-settlement-failed", "data": taker_view}
    )
    assert isinstance(enveloped, SyncSettlementFailure)

    # The maker's own view of the same fill names its quotes, not the taker's order.
    maker_view = parse_sync_settlement_event(
        {
            "asset": "1",
            "taker_order_id": None,
            "maker_quotes": [{"order_id": "mm-1", "trade_id": 7}],
            "reason": "counterparty_at_fault",
            "details": None,
            "timestamp_ns": 1,
        }
    )
    assert isinstance(maker_view, SyncSettlementFailure)
    assert maker_view.taker_order_id is None
    assert maker_view.maker_quotes[0].order_id == "mm-1"
    assert maker_view.counterparty_at_fault


SYNC_HELPERS = (
    lambda side, signer: create_sync_taker_order_ob_request_payload(
        quantity=1_000,
        price=10_000,
        side=side,
        signer=signer,
        book_quantity_decimals=4,
        book_price_decimals=2,
        asset_identifier=AssetIdentifier("1"),
        order_id="sync-side",
        base_token=WETH,
        nonce=0,
    ),
    lambda side, signer: create_sync_maker_order_ob_request_payload(
        quantity=1_000,
        price=10_000,
        side=side,
        signer=signer,
        book_quantity_decimals=4,
        book_price_decimals=2,
        asset_identifier=AssetIdentifier("1"),
        order_id="sync-side",
    ),
)


@pytest.mark.parametrize("helper", SYNC_HELPERS, ids=("taker", "maker"))
@pytest.mark.parametrize(
    "side,expected",
    (("ask", Side.SELL), ("Sell", Side.SELL), ("bid", Side.BUY), ("BUY", Side.BUY)),
)
def test_sync_helpers_parse_side_aliases(helper, side, expected):
    request = helper(side, User())
    assert request.order.side is expected


@pytest.mark.parametrize("helper", SYNC_HELPERS, ids=("taker", "maker"))
@pytest.mark.parametrize("side", ("sel", "long", ""))
def test_sync_helpers_reject_unknown_sides_before_signing(helper, side):
    with pytest.raises(ValueError):
        helper(side, User())


CHECKSUMMED_EXECUTOR = "0xabCDeF0123456789AbcdEf0123456789aBCDEF01"
CANONICAL_EXECUTOR = "0xabcdef0123456789abcdef0123456789abcdef01"


def test_sync_maker_executor_address_is_canonicalized_before_signing():
    details = SyncMakerOrderDetails(
        limit_price=1, quantity=1, executor_address=CHECKSUMMED_EXECUTOR
    )
    assert details.executor_address == CANONICAL_EXECUTOR
    assert details.model_dump()["SyncMaker"]["executor_address"] == CANONICAL_EXECUTOR
    # Uppercase and unprefixed forms are accepted and canonicalized the same way.
    assert (
        SyncMakerOrderDetails(
            limit_price=1, quantity=1, executor_address=CANONICAL_EXECUTOR[2:].upper()
        ).executor_address
        == CANONICAL_EXECUTOR
    )


@pytest.mark.parametrize(
    "executor_address",
    (
        "0x1234",
        "not-an-address",
        "0xabCDeF0123456789AbcdEf0123456789aBCDEF02",  # bad EIP-55 checksum
        "0xzz0000000000000000000000000000000000000000",
        42,
    ),
)
def test_sync_maker_rejects_invalid_executor_addresses(executor_address):
    with pytest.raises(ValidationError):
        SyncMakerOrderDetails(limit_price=1, quantity=1, executor_address=executor_address)


# Pinned interop fixture: the server side of this test lives in
# bin/order-management-system/src/rules/sync_order.rs
# (`tpluspy_signed_sync_maker_with_checksummed_executor_address_verifies`), which
# deserializes INTEROP_REQUEST, re-serializes the order with the Rust `Address` and
# verifies INTEROP_SIGNATURE against it. Regenerate both constants together.
INTEROP_PRIVATE_KEY = bytes(range(1, 33))
INTEROP_PAYLOAD = (
    '{"signer":"79b5562e8fe654f94078b112e8a98ba7901f853ae695bed7e0e3910bad049664",'
    '"order_id":"sync-maker-interop","base_asset":"1","book_price_decimals":2,'
    '"book_quantity_decimals":4,"details":{"SyncMaker":{"limit_price":10000,"quantity":1000,'
    '"time_in_force":"GTC","executor_address":"0xabcdef0123456789abcdef0123456789abcdef01"}},'
    '"side":"Sell","trigger":null,"creation_timestamp_ns":1700000000000000000,'
    '"target":{"account":1,"is_spot":true},"reduce_only":false,"max_trading_fees_rate":50000,'
    '"protocol_version":1}'
)
INTEROP_SIGNATURE = (
    "4a0bdf9ddc42b29b543dad2cc19c4b19d277ea36e07c36433c2a1c6639a63c66"
    "a6bf3dcf70183a1c43b0c0d8bc4ffc17e34b1ff02eed6230eefcee77abe26500"
)


def test_sync_maker_checksummed_executor_address_signs_the_rust_canonical_payload():
    user = User(private_key=INTEROP_PRIVATE_KEY)
    order = Order(
        signer=user.public_key,
        order_id="sync-maker-interop",
        base_asset=AssetIdentifier("1"),
        book_quantity_decimals=4,
        book_price_decimals=2,
        details=SyncMakerOrderDetails(
            limit_price=10_000, quantity=1_000, executor_address=CHECKSUMMED_EXECUTOR
        ),
        side=Side("ask"),
        trigger=None,
        creation_timestamp_ns=1_700_000_000_000_000_000,
        target=TradeTarget.margin_account_spot_trade(),
        reduce_only=False,
        max_trading_fees_rate=50_000,
    )
    payload = order.signable_part()
    assert payload == INTEROP_PAYLOAD
    signature, _ = user.signing_parts(payload)
    assert bytes(signature).hex() == INTEROP_SIGNATURE


@pytest.mark.parametrize(
    "time_in_force,wire",
    (
        (SyncGTC(), "GTC"),
        (
            SyncGTD(timestamp_ns=1_800_000_000_000_000_000),
            {"GTD": {"timestamp_ns": 1_800_000_000_000_000_000}},
        ),
    ),
    ids=("gtc", "gtd"),
)
def test_sync_maker_time_in_force_round_trips_like_the_rust_enum(time_in_force, wire):
    details = SyncMakerOrderDetails(limit_price=1, quantity=2, time_in_force=time_in_force)
    dumped = details.model_dump()
    assert dumped["SyncMaker"]["time_in_force"] == wire
    assert SyncMakerOrderDetails.model_validate(dumped) == details

    # The default is GTC; the wire form parses back into the typed variant.
    assert SyncMakerOrderDetails(limit_price=1, quantity=2).time_in_force == SyncGTC()
    assert (
        SyncMakerOrderDetails.model_validate(
            {"limit_price": 1, "quantity": 2, "time_in_force": wire}
        ).time_in_force
        == time_in_force
    )


@pytest.mark.parametrize(
    "time_in_force",
    (SyncGTC(), SyncGTD(timestamp_ns=1_800_000_000_000_000_000)),
    ids=("gtc", "gtd"),
)
def test_sync_maker_time_in_force_survives_the_order_model(time_in_force):
    request = create_sync_maker_order_ob_request_payload(
        quantity=1_000,
        price=10_000,
        side="Sell",
        signer=User(),
        book_quantity_decimals=4,
        book_price_decimals=2,
        asset_identifier=AssetIdentifier("1"),
        order_id="sync-tif",
        time_in_force=time_in_force,
    )
    payload = json.loads(request.order.signable_part())
    assert payload["details"]["SyncMaker"]["time_in_force"] == time_in_force.model_dump()
    parsed = Order.model_validate(payload)
    assert isinstance(parsed.details, SyncMakerOrderDetails)
    assert parsed.details.time_in_force == time_in_force
    assert parsed.details == request.order.details


@pytest.mark.parametrize("time_in_force", ("IOC", {"GTD": {}}, {"GTC": {"post_only": True}}))
def test_sync_maker_rejects_unknown_time_in_force(time_in_force):
    with pytest.raises(ValidationError):
        SyncMakerOrderDetails.model_validate(
            {"limit_price": 1, "quantity": 2, "time_in_force": time_in_force}
        )
