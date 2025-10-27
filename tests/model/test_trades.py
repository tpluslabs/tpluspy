import json

import pytest

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.trades import (
    TradeConfirmedEvent,
    TradePendingEvent,
    parse_single_trade,
    parse_trade_event,
)


@pytest.fixture(scope="module")
def make_trade():
    def fn(ty: str):
        return f'{{"asset_id":"82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@000000000000a4b1","trade_id":122519,"price":"3862.36934070","quantity":"0.01000000","timestamp_ns":1761283013888453220,"buyer_is_maker":false,"status":"{ty}"}}'

    return fn


def assert_trade(evt, type: str):
    assert evt.trade.asset_id == AssetIdentifier(
        "82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@000000000000a4b1"
    )
    assert evt.trade.trade_id == 122519
    assert evt.trade.price == 3862.36934070
    assert evt.trade.quantity == 0.01
    assert evt.trade.timestamp_ns == 1761283013888453220
    assert not evt.trade.buyer_is_maker
    assert evt.trade.status == type


@pytest.mark.parametrize("evt_type", (TradeConfirmedEvent, TradePendingEvent, TradeConfirmedEvent))
def test_parse_trade_event(evt_type, make_trade):
    evt_str = evt_type.model_fields["event_type"].default
    trade = make_trade(evt_str)
    raw_msg = f'{{"{evt_str}":{trade}}}'
    evt = parse_trade_event(json.loads(raw_msg))
    assert isinstance(evt, evt_type)
    assert_trade(evt, evt_str)


def test_parse_trade(make_trade):
    data = json.loads(make_trade("Pending"))
    trade = parse_single_trade(data)
    assert not trade.buyer_is_maker
