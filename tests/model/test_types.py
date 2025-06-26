import pytest
from pydantic import BaseModel

from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.user import User


class TestChainID:
    @pytest.mark.parametrize(
        "value",
        [
            11155111,
            "0xaA36A7",
            (11155111).to_bytes(8, "big"),
            [0, 0, 0, 0, 0, 170, 54, 167],
        ],
    )
    def test_chain_id(self, value):
        class MyModel(BaseModel):
            chain_id: ChainID

        model = MyModel(chain_id=value)
        assert model.chain_id == 11155111

        # Show it serializes back to equivalent of rust's [u8; 8].
        model_json = model.model_dump_json()
        assert model_json == '{"chain_id":[0,0,0,0,0,170,54,167]}'


class TestUserPublicKey:
    @pytest.mark.parametrize(
        "value",
        [
            106534544547867510712044657293315148109814522807111346850843650182212281952302,
            "0xeb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e",
            (
                106534544547867510712044657293315148109814522807111346850843650182212281952302
            ).to_bytes(32, "big"),
            [
                235,
                136,
                106,
                86,
                249,
                240,
                239,
                166,
                68,
                50,
                103,
                140,
                235,
                241,
                39,
                14,
                147,
                20,
                167,
                88,
                230,
                235,
                105,
                122,
                96,
                98,
                2,
                164,
                81,
                227,
                232,
                46,
            ],
        ],
    )
    def test_user_public_key(self, value):
        class MyModel(BaseModel):
            user: UserPublicKey

        model = MyModel(user=value)
        assert model.user == "eb886a56f9f0efa64432678cebf1270e9314a758e6eb697a606202a451e3e82e"

        # Show it serializes back to equivalent of rust's [u8; 8].
        model_json = model.model_dump_json()
        assert (
            model_json
            == '{"user":[235,136,106,86,249,240,239,166,68,50,103,140,235,241,39,14,147,20,167,88,230,235,105,122,96,98,2,164,81,227,232,46]}'
        )

    def test_validate_user_for_key(self):
        class MyModel(BaseModel):
            user: UserPublicKey

        user = User()
        model = MyModel(user=user)
        assert model.user == user.public_key
