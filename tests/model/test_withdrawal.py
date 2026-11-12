import pytest
from cryptography.exceptions import InvalidSignature

from tplus.model.withdrawal import InnerWithdrawalRequest, WithdrawalRequest


class TestWithdrawal:
    @pytest.fixture
    def inner_withdrawal(self):
        return InnerWithdrawalRequest.model_validate(
            {
                "tplus_user": "0xeb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e",
                "asset": "62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7",
                "amount": 100,
            }
        )

    def test_signing_payload(self, inner_withdrawal):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        withdrawal = WithdrawalRequest(inner=inner_withdrawal, signature=[])
        actual = withdrawal.inner.signing_payload()
        expected = '{"tplus_user":"eb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e","asset":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000aa36a7","amount":"100","nonce":null,"target":"0000000000000000000000000000000000000000000000000000000000000000","max_fee":null}'
        assert actual == expected

    def test_bounded_signing_payload(self, inner_withdrawal):
        """
        The fee bound is signed as the decimal string the wire carries.
        """
        bounded = inner_withdrawal.model_copy(update={"max_fee": 25})
        actual = bounded.signing_payload()
        assert actual.endswith('"max_fee":"25"}')
        assert actual != inner_withdrawal.signing_payload()

    def test_create_signed(self, inner_withdrawal, user):
        asset = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7"
        signed = WithdrawalRequest.create_signed(user, asset, 100)
        assert signed.signature  # truthiness
        assert (
            signed.inner.asset.root
            == "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000aa36a7"
        )
        assert signed.inner.max_fee is None

    def test_create_signed_with_max_fee(self, user):
        """
        Adding the bound changes what is signed: the unbounded signature no longer verifies.
        """
        asset = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7"
        bounded = WithdrawalRequest.create_signed(user, asset, 100, max_fee=25)
        unbounded = WithdrawalRequest.create_signed(user, asset, 100)
        assert bounded.inner.max_fee == 25
        assert bounded.signature != unbounded.signature

    def test_tampering_with_the_bound_breaks_the_signature(self, user):
        """
        A signature covers the bound it was made with: changing, removing or adding one
        afterwards no longer verifies.
        """
        asset = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7"
        bounded = WithdrawalRequest.create_signed(user, asset, 100, max_fee=25)
        unbounded = WithdrawalRequest.create_signed(user, asset, 100)
        for signed in (bounded, unbounded):
            user.vk.verify(bytes(signed.signature), signed.signing_payload().encode())

        tampered = [
            (bounded.inner.model_copy(update={"max_fee": 26}), bounded.signature),
            (bounded.inner.model_copy(update={"max_fee": None}), bounded.signature),
            (unbounded.inner.model_copy(update={"max_fee": 25}), unbounded.signature),
        ]
        for inner, signature in tampered:
            with pytest.raises(InvalidSignature):
                user.vk.verify(bytes(signature), inner.signing_payload().encode())
