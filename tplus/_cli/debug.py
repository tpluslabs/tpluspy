import asyncio

import click

from tplus._cli._context import CLIContext, clearing_url_option, pass_cli_context
from tplus.cli_tools import ignore_ssl_option


@click.group()
def debug():
    """Debug admin endpoints. Dev/test only."""


@debug.command("set-registry-address")
@click.argument("address")
@click.option("--chain-id", "chain_id", type=int, required=True)
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _set_registry_address(cli_ctx: CLIContext, address: str, chain_id: int):
    """Set the CE's on-chain Registry address to ADDRESS on CHAIN_ID."""
    from tplus.model.chain_address import ChainAddress
    from tplus.model.types import ChainID

    client = cli_ctx.clearing_engine_client(anonymous=True)
    chain_addr = ChainAddress.from_evm_address(address, ChainID.evm(chain_id))
    asyncio.run(client.assets.set_registry_address(chain_addr))
    click.echo(f"Registry address set: {chain_addr}")


@debug.command("set-credential-manager-address")
@click.argument("address")
@click.option("--chain-id", "chain_id", type=int, required=True)
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _set_credential_manager_address(cli_ctx: CLIContext, address: str, chain_id: int):
    """Set the CE's on-chain CredentialManager address to ADDRESS on CHAIN_ID."""
    from tplus.model.chain_address import ChainAddress
    from tplus.model.types import ChainID

    client = cli_ctx.clearing_engine_client(anonymous=True)
    chain_addr = ChainAddress.from_evm_address(address, ChainID.evm(chain_id))
    asyncio.run(client.vaults.set_credential_manager_address(chain_addr))
    click.echo(f"CredentialManager address set: {chain_addr}")


@debug.command("set-withdrawal-delay")
@click.option("--min-delay", "min_delay", type=int, default=0, show_default=True)
@click.option("--max-delay", "max_delay", type=int, default=0, show_default=True)
@click.option(
    "--clamp",
    "delay_clamps",
    type=int,
    multiple=True,
    help="Delay clamp boundary (repeatable). Defaults to [0, 1_000_000] if omitted.",
)
@click.option(
    "--value",
    "delay_values",
    type=int,
    multiple=True,
    help="Delay value at each clamp (repeatable). Defaults to [0, 0] if omitted.",
)
@click.option("--cap-floor", "cap_floor", type=int, default=50_000, show_default=True)
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _set_withdrawal_delay(
    cli_ctx: CLIContext,
    min_delay: int,
    max_delay: int,
    delay_clamps: tuple[int, ...],
    delay_values: tuple[int, ...],
    cap_floor: int,
):
    """Set the CE's withdrawal-delay parameters."""
    clamps = list(delay_clamps) if delay_clamps else [0, 1_000_000]
    values = list(delay_values) if delay_values else [0, 0]
    client = cli_ctx.clearing_engine_client(anonymous=True)
    asyncio.run(
        client.admin.set_withdrawal_delay_params(
            min_delay=min_delay,
            max_delay=max_delay,
            delay_clamps=clamps,
            delay_values=values,
            cap_floor=cap_floor,
        )
    )
    click.echo("Withdrawal delay parameters updated.")


@debug.command("reset-users")
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _reset_users(cli_ctx: CLIContext):
    """Wipe all user state on the CE."""
    client = cli_ctx.clearing_engine_client(anonymous=True)
    asyncio.run(client.admin.reset_users())
    click.echo("Users reset.")


@debug.command("modify-inventory")
@click.argument("user_pubkey")
@click.option("--asset", "asset", required=True, help="Asset index or identifier.")
@click.option("--base-credits", "base_credits", type=str, default="0", show_default=True)
@click.option("--base-liabilities", "base_liabilities", type=str, default="0", show_default=True)
@click.option("--quote-credits", "quote_credits", type=str, default="0", show_default=True)
@click.option("--quote-liabilities", "quote_liabilities", type=str, default="0", show_default=True)
@click.option("--spot", "spot", type=str, default="0", show_default=True)
@click.option(
    "--avg-spot-deposit",
    "avg_spot_deposit",
    type=str,
    help="Average spot deposit. Defaults to --spot.",
)
@click.option("--sub-account", "sub_account", type=int, default=1, show_default=True)
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _modify_inventory(
    cli_ctx: CLIContext,
    user_pubkey: str,
    asset: str,
    base_credits: str,
    base_liabilities: str,
    quote_credits: str,
    quote_liabilities: str,
    spot: str,
    avg_spot_deposit: str | None,
    sub_account: int,
):
    """Seed a user's inventory (admin-only; dev/test)."""
    from tplus.model.asset_identifier import AssetIdentifier
    from tplus.model.types import UserPublicKey

    client = cli_ctx.clearing_engine_client(anonymous=True)
    asyncio.run(
        client.admin.modify_user_inventory(
            user=UserPublicKey.__validate_user__(user_pubkey),
            asset=AssetIdentifier.model_validate(asset),
            base_balance={"credits": base_credits, "liabilities": base_liabilities},
            quote_balance={"credits": quote_credits, "liabilities": quote_liabilities},
            spot_balance=spot,
            average_spot_deposit=avg_spot_deposit if avg_spot_deposit is not None else spot,
            sub_account_index=sub_account,
        )
    )
    click.echo(f"Inventory updated for {user_pubkey} sub_account={sub_account}.")
