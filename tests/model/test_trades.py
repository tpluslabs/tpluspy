import json

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.trades import parse_trade_event, TradeConfirmedEvent


def test_parse_trade_event():
    raw_msg = '{"Confirmed":{"asset_id":"82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@000000000000a4b1","trade_id":122519,"price":"3862.36934070","quantity":"0.01000000","timestamp_ns":1761283013888453220,"buyer_is_maker":false,"status":"Confirmed"}}'

    ev = parse_trade_event(json.loads(raw_msg))

    assert isinstance(ev, TradeConfirmedEvent)
    assert ev.trade.asset_id == AssetIdentifier(
        "82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@000000000000a4b1"
    )
    assert ev.trade.trade_id == 122519
    assert ev.trade.price == 3862.36934070
    assert ev.trade.quantity == 0.01
    assert ev.trade.timestamp_ns == 1761283013888453220
    assert not ev.trade.buyer_is_maker
    assert ev.trade.status == "Confirmed"
