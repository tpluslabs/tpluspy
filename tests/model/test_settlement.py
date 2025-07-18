from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.settlement import (
    BundleSettlementRequest,
    TxSettlementRequest,
)

CHAIN_ID = 11155111
ASSET_IN = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
ASSET_OUT = "0x58372ab62269A52fA636aD7F200d93999595DCAF"
SETTLER = "0xeb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e"


class TestTxSettlementRequest:
    def test_signing_payload(self):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        settlement = {
            "tplus_user": SETTLER,
            "calldata": [],
            **get_base_settlement_data(),
            "chain_id": CHAIN_ID,
        }
        settlement = TxSettlementRequest(inner=settlement, signature=[])
        actual = settlement.signing_payload()
        expected = '{"tplus_user":[235,136,106,86,249,240,239,166,68,50,103,140,235,241,39,14,147,20,167,88,230,235,105,122,96,98,2,164,81,227,232,46],"calldata":[],"asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@0000000000aa36a7","amount_in":"0x64","asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000@0000000000aa36a7","amount_out":"0x64","chain_id":[0,0,0,0,0,170,54,167]}'
        assert actual == expected

        # Show it is the same as the inner version.
        actual = settlement.inner.signing_payload()
        assert actual == expected


class TestBundleSettlementRequest:
    def test_signing_payload(self):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        inner = {
            "settlements": [get_base_settlement_data()],
            "bundle": {"bundle": {}, "bundle_id": 0},
            "tplus_user": SETTLER,
            "chain_id": CHAIN_ID,
        }
        settlement = BundleSettlementRequest(inner=inner, signature=[])
        actual = settlement.signing_payload()
        expected = '{"settlements":[{"asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@0000000000aa36a7","amount_in":"0x64","asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000@0000000000aa36a7","amount_out":"0x64"}],"bundle":{"bundle":{},"bundle_id":0},"chain_id":[0,0,0,0,0,170,54,167],"tplus_user":[235,136,106,86,249,240,239,166,68,50,103,140,235,241,39,14,147,20,167,88,230,235,105,122,96,98,2,164,81,227,232,46]}'
        assert actual == expected


def get_base_settlement_data() -> dict:
    return {
        "asset_in": AssetIdentifier(f"{ASSET_IN}@{CHAIN_ID}"),
        "amount_in": 100,
        "asset_out": AssetIdentifier(f"{ASSET_OUT}@{CHAIN_ID}"),
        "amount_out": 100,
    }
