from ape import convert

from tplus.evm.eip712 import Order
from tplus.evm.utils import address_to_bytes32


def test_settlement_order(signer):
    """
    Mostly for demo-ing how to sign an order.
    """
    order = Order(
        tokenOut="0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
        amountOut=convert("1 ether", int),
        tokenIn="0x58372ab62269A52fA636aD7F200d93999595DCAF",
        amountIn=convert("1 ether", int),
        userId=address_to_bytes32(signer.address),
        nonce=1,
        validUntil=1000000000,
    )
    signature = signer.sign_message(order)
    assert signer.check_signature(order, signature)
