import pytest
from ape import convert

from tplus.evm.utils import address_to_bytes32
from tplus.evm.eip712 import Order


@pytest.fixture
def signer(accounts):
    return accounts[0]


@pytest.fixture
def order(signer):
    return Order(
        tokenOut="0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
        amountOut=convert("1 ether", int),
        tokenIn="0x58372ab62269A52fA636aD7F200d93999595DCAF",
        amountIn=convert("1 ether", int),
        userId=address_to_bytes32(signer.address),
        nonce=1,
        validUntil=1000000000,
    )

