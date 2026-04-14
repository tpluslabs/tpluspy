import pytest

from tplus.model.settlement import (
    BatchSettlementRequest,
    InnerMakerOrderAttachment,
    InnerSettlementRequest,
    MakerOrderAttachment,
    TxSettlementRequest,
)
from tplus.utils.user import User

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


class TestTxSettlementRequest:
    @pytest.fixture(scope="class")
    def settlement(self, user):
        return {
            "tplus_user": user.public_key,
            "sub_account_index": 0,
            "settler": user.public_key,
            **get_base_settlement_data(),
            "chain_id": CHAIN_ID,
        }

    def test_signing_payload(self, settlement, user):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        settlement = TxSettlementRequest(inner=settlement, signature=[])
        actual = settlement.signing_payload()
        expected = f'{{"tplus_user":"{user.public_key}","sub_account_index":0,"settler":"{user.public_key}","mode":"margin","asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000","amount_in":"9f4cfc56cd29b000","asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000","amount_out":"8e1bc9bf04000","chain_id":"000000000000aa36a7"}}'
        assert actual == expected

        # Show it is the same as the inner version.
        actual = settlement.inner.signing_payload()
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


class TestDelegatedSettlement:
    @pytest.fixture(scope="class")
    def mm_user(self):
        return User()

    @pytest.fixture(scope="class")
    def settler_user(self):
        return User()

    @pytest.fixture
    def maker_order(self, mm_user, settler_user):
        return MakerOrderAttachment(
            inner=InnerMakerOrderAttachment(
                mm_pubkey=mm_user.public_key,
                settler=settler_user.public_key,
                expires_at=1_700_000_000_000_000_000,
            ),
            signature=[],
        )

    def test_from_raw_delegated(self, user, mm_user):
        request = InnerSettlementRequest.from_raw_delegated(
            ASSET_IN,
            100,
            6,
            ASSET_OUT,
            100,
            18,
            user.public_key,
            CHAIN_ID,
            0,
            mm_user.public_key,
            1_700_000_000_000_000_000,
        )
        assert request.settler is None
        assert request.mm_pubkey == mm_user.public_key
        assert request.expires_at == 1_700_000_000_000_000_000
        assert request.amount_in == 100_000_000_000_000

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
            expires_at=1_700_000_000_000_000_000,
        )
        assert request.expires_at == 1_700_000_000_000_000_000
        assert request.mm_pubkey is None
        assert request.settler == user.public_key

    def test_signing_payload_delegated(self, user, mm_user):
        request = InnerSettlementRequest.from_raw_delegated(
            ASSET_IN,
            100,
            6,
            ASSET_OUT,
            100,
            18,
            user.public_key,
            CHAIN_ID,
            0,
            mm_user.public_key,
            1_700_000_000_000_000_000,
        )
        payload = request.signing_payload()
        # settler must be absent (None), mm_pubkey + expires_at appended at the end
        assert '"settler"' not in payload
        assert f'"mm_pubkey":"{mm_user.public_key}"' in payload
        assert '"expires_at":1700000000000000000' in payload
        # Field ordering: chain_id, then expires_at, then mm_pubkey (append order in signing_payload)
        assert payload.index('"chain_id"') < payload.index('"expires_at"')
        assert payload.index('"expires_at"') < payload.index('"mm_pubkey"')

    def test_create_signed_delegated(self, user, mm_user, maker_order):
        inner = InnerSettlementRequest.from_raw_delegated(
            ASSET_IN,
            100,
            6,
            ASSET_OUT,
            100,
            18,
            user.public_key,
            CHAIN_ID,
            0,
            mm_user.public_key,
            1_700_000_000_000_000_000,
        )
        signed = TxSettlementRequest.create_signed_delegated(inner, user, maker_order)
        assert signed.signature
        assert signed.maker_order is maker_order
        assert signed.inner.mm_pubkey == mm_user.public_key

    def test_create_signed_delegated_from_dict(self, user, mm_user, maker_order):
        inner_dict = {
            "sub_account_index": 0,
            "settler": None,
            **get_base_settlement_data(),
            "chain_id": CHAIN_ID,
            "mm_pubkey": mm_user.public_key,
            "expires_at": 1_700_000_000_000_000_000,
        }
        signed = TxSettlementRequest.create_signed_delegated(inner_dict, user, maker_order)
        assert signed.inner.tplus_user == user.public_key
        assert signed.signature

    def test_create_signed_delegated_missing_mm_pubkey(self, user, maker_order):
        inner = InnerSettlementRequest.from_raw(
            ASSET_IN,
            100,
            6,
            ASSET_OUT,
            100,
            18,
            user.public_key,
            CHAIN_ID,
            0,
            expires_at=1_700_000_000_000_000_000,
        )
        with pytest.raises(ValueError, match="mm_pubkey to be set"):
            TxSettlementRequest.create_signed_delegated(inner, user, maker_order)

    def test_create_signed_delegated_missing_expires_at(self, user, mm_user, maker_order):
        # Bypass from_raw_delegated's required expires_at to construct the bad state.
        inner = InnerSettlementRequest.model_validate(
            {
                "mode": "margin",
                "sub_account_index": 0,
                "settler": None,
                **get_base_settlement_data(),
                "tplus_user": user.public_key,
                "chain_id": CHAIN_ID,
                "mm_pubkey": mm_user.public_key,
            }
        )
        with pytest.raises(ValueError, match="expires_at to bound the replay window"):
            TxSettlementRequest.create_signed_delegated(inner, user, maker_order)

    def test_create_signed_delegated_mm_mismatch(self, user, maker_order):
        # Different MM than the one in maker_order.
        other_mm = User()
        inner = InnerSettlementRequest.from_raw_delegated(
            ASSET_IN,
            100,
            6,
            ASSET_OUT,
            100,
            18,
            user.public_key,
            CHAIN_ID,
            0,
            other_mm.public_key,
            1_700_000_000_000_000_000,
        )
        with pytest.raises(ValueError, match="MmPubkeyMismatch"):
            TxSettlementRequest.create_signed_delegated(inner, user, maker_order)


class TestBundleSettlementRequest:
    def test_signing_payload(self, user):
        """
        Show we serialize to the JSON the clearing-engine expects.
        """
        inner = {
            "tplus_user": user.public_key,
            "sub_account_index": 0,
            "settler": user.public_key,
            "orders": [get_base_settlement_data()],
            "transactions": [],
            "chain_id": CHAIN_ID,
        }
        settlement = BatchSettlementRequest.model_validate({"inner": inner})
        actual = settlement.signing_payload()
        expected = f'{{"tplus_user":"{user.public_key}","sub_account_index":0,"settler":"{user.public_key}","orders":[{{"mode":"margin","asset_in":"62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000","amount_in":"9f4cfc56cd29b000","asset_out":"58372ab62269a52fa636ad7f200d93999595dcaf000000000000000000000000","amount_out":"8e1bc9bf04000"}}],"transactions":[],"chain_id":"000000000000aa36a7"}}'
        assert actual == expected


def get_base_settlement_data() -> dict:
    return {
        "asset_in": ASSET_IN,
        "amount_in": 11478827000000000000,
        "asset_out": ASSET_OUT,
        "amount_out": 2500000000000000,
    }
