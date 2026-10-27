from decimal import Decimal

import pytest

from tplus.model.user_event import (
    DepositLanded,
    InterestEpochOccurred,
    SettlementCompleted,
    parse_user_event,
)


def test_parse_settlement_completed():
    """Any settlement that lands arrives as a tagged SettlementCompleted."""
    event = parse_user_event(
        {
            "SettlementCompleted": {
                "user": "ab" * 32,
                "sub_account_index": 0,
                "settler": "cd" * 32,
                "mode": "spot",
                "asset_in": "0",
                "amount_in": "100000000000000000000",
                "asset_out": "1",
                "amount_out": "1000000000000000000",
                "chain_id": "000000000000000001",
                "settlement_nonce": 4,
                "timestamp_ns": 1,
            }
        }
    )
    assert isinstance(event, SettlementCompleted)
    assert event.amount_in == "100000000000000000000"
    assert event.settlement_nonce == 4


class TestParseUserEvent:
    def test_interest_epoch(self):
        """
        Shows the nested payments map keeps its market and sub-account keys and
        that signed amounts arrive as decimals.
        """
        raw = {
            "InterestEpochOccurred": {
                "user": "ab" * 32,
                "payments": {
                    "1": {
                        "1": {
                            "funding_amount": "-12.5",
                            "utilization_amount": "0",
                            "quote_utilization_amount": "0.75",
                            "funding_rate": "0.0001",
                            "utilization_rate": "0.00002",
                            "quote_utilization_rate": "0.00003",
                        }
                    }
                },
                "timestamp_ns": 1_777_920_000_000_000_000,
            }
        }
        event = parse_user_event(raw)
        assert isinstance(event, InterestEpochOccurred)
        payment = event.payments["1"][1]
        assert payment.funding_amount == Decimal("-12.5")
        assert payment.quote_utilization_amount == Decimal("0.75")
        assert payment.funding_rate == Decimal("0.0001")
        assert payment.utilization_rate == Decimal("0.00002")
        assert payment.quote_utilization_rate == Decimal("0.00003")
        assert event.timestamp_ns == 1_777_920_000_000_000_000

    def test_deposit_landed(self):
        raw = {
            "DepositLanded": {
                "user": "ab" * 32,
                "asset": "1",
                "amount": "1500000000000000000",
                "chain_id": "1",
                "deposit_nonce": 42,
                "timestamp_ns": 7,
            }
        }
        event = parse_user_event(raw)
        assert isinstance(event, DepositLanded)
        assert event.amount == "1500000000000000000"

    def test_unknown_variant(self):
        with pytest.raises(ValueError, match="Unknown user activity event variant"):
            parse_user_event({"Nope": {}})
