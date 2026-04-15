import asyncio

import click
from ape.cli import ConnectedProviderCommand, account_option

from tplus._cli._context import CLIContext, pass_cli_context
from tplus.evm.managers.vault import VaultOwner


@click.group()
def vault():
    """Manage T+ vault (contract owner)."""


def _build_owner(cli_ctx: CLIContext, signer) -> VaultOwner:
    try:
        ce = cli_ctx.clearing_engine_client()
    except click.UsageError:
        ce = None
    return VaultOwner(owner=signer, clearing_engine=ce)


@vault.command("set-domain-separator", cls=ConnectedProviderCommand)
@account_option()
@click.option("--separator", help="Hex-encoded domain separator. Computed if omitted.")
@pass_cli_context
def _set_domain_separator(cli_ctx: CLIContext, account, separator: str | None):
    """Set the vault's EIP-712 domain separator."""
    owner = _build_owner(cli_ctx, account)
    value = bytes.fromhex(separator.removeprefix("0x")) if separator else None
    receipt = owner.set_domain_separator(value)
    click.echo(f"tx: {receipt.txn_hash}")


@vault.command("set-administrators", cls=ConnectedProviderCommand)
@account_option()
@click.option(
    "--admin-key",
    "admin_keys",
    multiple=True,
    help="Admin public key (hex). May be repeated. Defaults to the CE verifying key.",
)
@click.option("--quorum", type=int, help="Withdrawal quorum. Defaults to number of admins.")
@pass_cli_context
def _set_administrators(
    cli_ctx: CLIContext, account, admin_keys: tuple[str, ...], quorum: int | None
):
    """Set vault administrators."""
    owner = _build_owner(cli_ctx, account)
    receipt = asyncio.run(
        owner.set_administrators(
            admin_keys=list(admin_keys) if admin_keys else None,
            withdrawal_quorum=quorum,
        )
    )
    click.echo(f"tx: {receipt.txn_hash}")


@vault.command("register-settler", cls=ConnectedProviderCommand)
@account_option()
@click.argument("settler")
@click.option("--executor", required=True, help="Executor address.")
@click.option("--wait/--no-wait", default=False, help="Wait for CE ingestion.")
@pass_cli_context
def _register_settler(
    cli_ctx: CLIContext, account, settler: str, executor: str, wait: bool
):
    """Register SETTLER (tplus alias or public key) with EXECUTOR."""
    owner = _build_owner(cli_ctx, account)

    try:
        user = cli_ctx.user_manager.load(settler)
        settler_arg = user.public_key
    except ValueError:
        settler_arg = settler

    receipt = asyncio.run(owner.register_settler(settler_arg, executor, wait=wait))
    click.echo(f"tx: {receipt.txn_hash}")


@vault.command("register-depositor", cls=ConnectedProviderCommand)
@account_option()
@click.argument("depositor")
@pass_cli_context
def _register_depositor(cli_ctx: CLIContext, account, depositor: str):
    """Allow DEPOSITOR to call deposit()."""
    owner = _build_owner(cli_ctx, account)
    receipt = asyncio.run(owner.register_depositor(depositor))
    click.echo(f"tx: {receipt.txn_hash}")
