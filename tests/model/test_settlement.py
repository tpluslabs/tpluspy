import pytest

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.settlement import (
    BundleSettlementRequest,
    TxSettlementRequest,
)

CHAIN_ID = 42161
ASSET_IN = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
ASSET_OUT = "0x58372ab62269A52fA636aD7F200d93999595DCAF"


class TestTxSettlementRequest:
    @pytest.fixture(scope="class")
    def settlement(self, user):
        return {
            "tplus_user": user.public_key,
            **get_base_settlement_data(),
            "chain_id": CHAIN_ID,
        }

    def test_signing_payload(self, settlement, user):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        settlement = TxSettlementRequest(inner=settlement, signature=[])
        actual = settlement.signing_payload()
        expected = f'{{"tplus_user":"{user.public_key}","asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1","amount_in":"9f4cfc56cd29b000","asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000@000000000000a4b1","amount_out":"8e1bc9bf04000","chain_id":42161}}'
        assert actual == expected

        # Show it is the same as the inner version.
        actual = settlement.inner.signing_payload()
        assert actual == expected

    def test_from_signed(self, settlement, user):
        settlement = TxSettlementRequest.create_signed(settlement, user)
        assert settlement.signature  # truthiness


class TestBundleSettlementRequest:
    def test_signing_payload(self, user):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        inner = {
            "settlements": [get_base_settlement_data()],
            "bundle": {"bundle": {}, "bundle_id": 0},
            "tplus_user": user.public_key,
            "chain_id": CHAIN_ID,
        }
        settlement = BundleSettlementRequest(inner=inner, signature=[])
        actual = settlement.signing_payload()
        expected = f'{{"settlements":[{{"asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1","amount_in":"9f4cfc56cd29b000","asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000@000000000000a4b1","amount_out":"8e1bc9bf04000"}}],"bundle":{{"bundle":{{}},"bundle_id":0}},"chain_id":42161,"tplus_user":"{user.public_key}"}}'
        assert actual == expected


def get_base_settlement_data() -> dict:
    return {
        "asset_in": AssetIdentifier(f"{ASSET_IN}@{CHAIN_ID}"),
        "amount_in": 11478827000000000000,
        "asset_out": AssetIdentifier(f"{ASSET_OUT}@{CHAIN_ID}"),
        "amount_out": 2500000000000000,
    }
