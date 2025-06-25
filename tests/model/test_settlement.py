from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.settlement import TxSettlementRequest

CHAIN_ID = 11155111
ASSET_IN = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
ASSET_OUT = "0x58372ab62269A52fA636aD7F200d93999595DCAF"


class TestTxSettlementRequest:
    def test_model_dump_json(self):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        settlement = {
            "tplus_user": "0xeb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e",
            "calldata": [],
            "asset_in": AssetIdentifier(f"{ASSET_IN}@{CHAIN_ID}"),
            "amount_in": 100,
            "asset_out": AssetIdentifier(f"{ASSET_OUT}@{CHAIN_ID}"),
            "amount_out": 100,
            "chain_id": CHAIN_ID,
        }
        settlement = TxSettlementRequest(inner=settlement, signature=[])
        actual = settlement.inner.model_dump_json()
        expected = '{"tplus_user":[235,136,106,86,249,240,239,166,68,50,103,140,235,241,39,14,147,20,167,88,230,235,105,122,96,98,2,164,81,227,232,46],"calldata":[],"asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@aa36a70000000000","amount_in":100,"asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000@aa36a70000000000","amount_out":100,"chain_id":[0,0,0,0,0,170,54,167]}'
        assert actual == expected
