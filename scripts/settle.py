from ape import accounts

from tplus.eip712 import OrderMessage
from tplus.contracts import Registry


def main():
    account = accounts.load("antazoey")

    registry = Registry()
    tokens = registry.get_assets()

    # TODO: Move address padding to a better API.
    addr_bytes = bytes.fromhex(account.address[2:])
    user_id = addr_bytes.rjust(32, b'\x00')

    order = OrderMessage(
        tokenOut=tokens[0].address,
        amountOut=100_000,
        tokenIn=tokens[1].address,
        amountIn=100_000,
        userId=user_id,
        nonce=1,
        validUntil=registry.chain_manager.blocks.height,
    )

    signature = account.sign_message(order)
    print(signature)


if __name__ == "__main__":
    main()
