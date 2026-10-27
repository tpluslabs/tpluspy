import pytest

from tplus.model.settlement import (
    InnerSettlementRequest,
    SettlementMode,
    TxSettlementRequest,
)

CHAIN_ID = "0x000000000000aa36a7"
ASSET_IN = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
ASSET_OUT = "0x58372ab62269A52fA636aD7F200d93999595DCAF"


class TestInnerSettlementRequest:
    def test_from_raw(self, user):
        request = InnerSettlementRequest.from_raw(
            ASSET_IN,
            100,
            6,
            ASSET_OUT,
            100,
            18,
            user.public_key,
            CHAIN_ID,
            0,
            7,
            mode=SettlementMode.MARGIN,
        )
        assert (
            request.asset_in == "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000"
        )
        assert request.amount_in == 100_000_000_000_000  # normalized
        assert (
            request.asset_out == "58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000"
        )
        assert request.amount_out == 100
        assert request.chain_id == CHAIN_ID
        assert request.nonce == 7

    def test_from_raw_with_expires_at(self, user):
        request = InnerSettlementRequest.from_raw(
            ASSET_IN,
            100,
            6,
            ASSET_OUT,
            100,
            18,
            user.public_key,
            CHAIN_ID,
            0,
            7,
            mode=SettlementMode.MARGIN,
            expires_at=1_700_000_000_000_000_000,
        )
        assert request.expires_at == 1_700_000_000_000_000_000
        assert request.settler == user.public_key


class TestTxSettlementRequest:
    @pytest.fixture(scope="class")
    def settlement(self, user):
        return {
            "tplus_user": user.public_key,
            "sub_account_index": 0,
            "settler": user.public_key,
            **get_base_settlement_data(),
            "chain_id": CHAIN_ID,
            "nonce": 7,
        }

    def test_signing_payload(self, settlement, user):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        settlement = TxSettlementRequest(inner=settlement, signature=[])
        actual = settlement.signing_payload()
        expected = f'{{"tplus_user":"{user.public_key}","sub_account_index":0,"settler":"{user.public_key}","mode":"margin","asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000","amount_in":"11478827000000000000","asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000","amount_out":"2500000000000000","chain_id":"000000000000aa36a7","nonce":7,"expires_at":null,"protocol_version":2}}'
        assert actual == expected

        # Show it is the same as the inner version.
        actual = settlement.inner.signing_payload()
        assert actual == expected

    def test_legacy_signing_payload(self, settlement, user):
        """
        Version 1 is what clients predating ``protocol_version`` signed: ``mm_pubkey``
        (since removed) serialized as null, no version field.
        """
        inner = InnerSettlementRequest.model_validate({**settlement, "protocol_version": 1})
        settlement = TxSettlementRequest(inner=inner, signature=[])
        actual = settlement.signing_payload()
        expected = f'{{"tplus_user":"{user.public_key}","sub_account_index":0,"settler":"{user.public_key}","mode":"margin","asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000","amount_in":"11478827000000000000","asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000","amount_out":"2500000000000000","chain_id":"000000000000aa36a7","nonce":7,"expires_at":null,"mm_pubkey":null}}'
        assert actual == expected

    def test_create_signed(self, settlement, user):
        signed = TxSettlementRequest.create_signed(settlement, user)
        assert signed.signature  # truthiness

        # Show user is not required in inner dict.
        settlement.pop("tplus_user", None)
        signed = TxSettlementRequest.create_signed(settlement, user)
        assert signed.inner.tplus_user == user.public_key
        assert signed.signature  # truthiness

        # Show can use model.
        settlement_model = InnerSettlementRequest.model_validate(settlement)
        signed = TxSettlementRequest.create_signed(settlement_model, user)
        assert signed.inner.tplus_user == user.public_key
        assert signed.signature  # truthiness


def get_base_settlement_data() -> dict:
    return {
        "asset_in": ASSET_IN,
        "amount_in": 11478827000000000000,
        "asset_out": ASSET_OUT,
        "amount_out": 2500000000000000,
    }
