import json
from pydantic import TypeAdapter

from tplus.model.trades import TradeEvent, parse_trade_event

def test_parse_trade_event():
    raw_msg = '{"Confirmed":{"asset_id":"82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@000000000000a4b1","trade_id":122519,"price":"3862.36934070","quantity":"0.01000000","timestamp_ns":1761283013888453220,"buyer_is_maker":false,"status":"Confirmed"}}'

    parse_trade_event(json.loads(raw_msg))

def test_deserialise_trade_event():
    raw_msg = '{"Confirmed":{"asset_id":"82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@000000000000a4b1","trade_id":122519,"price":"3862.36934070","quantity":"0.01000000","timestamp_ns":1761283013888453220,"buyer_is_maker":false,"status":"Confirmed"}}'

    event = TypeAdapter(TradeEvent).validate_json(raw_msg)
    assert event is not None

