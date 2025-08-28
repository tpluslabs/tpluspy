from tplus.model.withdrawal import InnerWithdrawalRequest, WithdrawalRequest


class TestWithdrawal:
    def test_signing_payload(self):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        inner = InnerWithdrawalRequest(
            tplus_user="0xeb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e",
            asset="62622E77D1349Face943C6e7D5c01C61465FE1dc@a4b1",
            amount=100,
            chain_id=42161,
        )
        withdrawal = WithdrawalRequest(inner=inner, signature=[])
        actual = withdrawal.inner.signing_payload()
        expected = '{"tplus_user":"eb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e","asset":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000a4b1","amount":"64","chain_id":42161}'
        assert actual == expected
