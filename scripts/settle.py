import click
from ape.cli import ConnectedProviderCommand, account_option

from tplus.contracts import address_to_bytes32, registry, vault
from tplus.eip712 import Order


@click.command(cls=ConnectedProviderCommand)
@account_option()
def cli(account, network):
    # Load registered assets for settling.
    tokens = registry.get_assets(chain_id=11155111)

    # t+ user IDs are bytes32 addresses.
    user_id = address_to_bytes32(account.address)

    # This is assuming we have both of each token (which I do).
    # We are swapping 1 for the other.
    sub_order = {
        "tokenOut": tokens[0].address,
        "amountOut": 100_000,
        "tokenIn": tokens[1].address,
        "amountIn": 100_000,
    }
    valid_until = registry.chain_manager.blocks.height

    if network.is_local:
        vault.deploy(account)

    deposit_nonce = vault.getDepositNonce(account)

    order = Order(
        **sub_order,
        userId=user_id,
        nonce=deposit_nonce,
        validUntil=valid_until,
    )

    signature = account.sign_message(order).encode_vrs()
    print(signature)

    vault.checkSignature(sub_order, account, signature, 1)


if __name__ == "__main__":
    main()
