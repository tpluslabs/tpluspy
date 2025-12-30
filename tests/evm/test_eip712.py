import pytest
from ape.utils.misc import ZERO_ADDRESS
from hexbytes import HexBytes

try:
    from ape import convert
except ImportError:
    pytest.skip("ape is not installed", allow_module_level=True)

from tplus.evm.eip712 import Domain, Order
from tplus.utils.user import User


def test_settlement_order(chain, signer):
    """
    Mostly for demo-ing how to sign an order.
    """
    order = Order(
        eip712_domain=Domain(
            chain.chain_id,
            ZERO_ADDRESS,
        ),
        tokenOut="0x62622E77D1349Face943C6e7D5c01C61465FE1dc",  # type: ignore
        amountOut=convert("1 ether", int),  # type: ignore
        tokenIn="0x58372ab62269A52fA636aD7F200d93999595DCAF",  # type: ignore
        amountIn=convert("1 ether", int),  # type: ignore
        user=HexBytes(User().public_key),  # type: ignore
        nonce=1,  # type: ignore
        validUntil=1000000000,  # type: ignore
    )
    signature = signer.sign_message(order)
    assert signer.check_signature(order, signature)
