import click
from ape.cli import ConnectedProviderCommand, account_option

from tplus.contracts import registry, vault

from .deploy import deploy


@click.command(cls=ConnectedProviderCommand)
@account_option()
def cli(account, network):
    if network.is_local:
        # Simulation - ensure deployed first.
        deploy(account, network)

    if not (tokens := registry.get_assets()):
        print("No tokens available")
        return

    # Ensure we have tokens.
    tokens[0].mint(account, "1 ether", sender=account)
    tokens[1].mint(account, "1 ether", sender=account)

    # Approve the vault to spend the tokens first.
    tokens[0].approve(vault.contract, "1 ether", sender=account)
    tokens[1].approve(vault.contract, "1 ether", sender=account)

    # Deposit the tokens into your t+ account.
    vault.deposit(account, account, tokens[0], "1 ether", sender=account)
    vault.deposit(account, account, tokens[1], "1 ether", sender=account)

    # Now, you can check your deposits using another call.
    print(vault.getDeposits(0, account))


if __name__ == "__main__":
    main()
