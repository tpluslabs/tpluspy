from tplus.model.withdrawal import InnerWithdrawalRequest, WithdrawalRequest


class TestWithdrawal:
    def test_signing_payload(self):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        inner = InnerWithdrawalRequest(
            tplus_user="0xeb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e",
            asset="62622E77D1349Face943C6e7D5c01C61465FE1dc@aa36a7",
            amount=100,
            chain_id=11155111,
        )
        withdrawal = WithdrawalRequest(inner=inner, signature=[])
        actual = withdrawal.inner.signing_payload()
        expected = '{"tplus_user":[235,136,106,86,249,240,239,166,68,50,103,140,235,241,39,14,147,20,167,88,230,235,105,122,96,98,2,164,81,227,232,46],"asset":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@0000000000aa36a7","amount":"0x64","chain_id":[0,0,0,0,0,170,54,167]}'
        assert actual == expected
