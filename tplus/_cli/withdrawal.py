import asyncio
import importlib.util
from typing import TYPE_CHECKING

import click

from tplus._cli._context import (
    CLIContext,
    clearing_url_option,
    pass_cli_context,
    tplus_account_option,
)
from tplus.cli_tools import (
    ignore_ssl_option,
)

if TYPE_CHECKING:
    from tplus.evm.managers.registry import RegistryOwner


_EVM_AVAILABLE = importlib.util.find_spec("ape") is not None


@click.group()
def withdrawal():
    """Admin operations around withdrawals."""


@withdrawal.group("params")
def _params():
    """Withdrawal-delay parameters on the Registry contract."""


@_params.command("update-ce")
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _update_ce(cli_ctx: CLIContext):
    """Re-ingest withdrawal-delay params."""
    client = cli_ctx.clearing_engine_client(anonymous=True)
    asyncio.run(client.assets.update_withdrawal_delay_parameters())
    click.echo("CE withdrawal-delay update requested.")


if _EVM_AVAILABLE:
    from ape.cli import ConnectedProviderCommand, account_option

    from tplus.cli_tools import tplus_network_option

    def _build_owner(cli_ctx: CLIContext, signer) -> "RegistryOwner":
        from tplus.evm.managers.registry import RegistryOwner

        try:
            ce = cli_ctx.clearing_engine_client(anonymous=True)
        except click.UsageError:
            ce = None

        return RegistryOwner(owner=signer, clearing_engine=ce)

    @_params.command("set", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @tplus_account_option()
    @account_option()
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
    @click.option(
        "--apply/--no-apply",
        "apply_pending",
        default=True,
        help="Apply pending params after set. Omit to leave pending-only.",
    )
    @pass_cli_context
    def _set(
        cli_ctx: CLIContext,
        account,
        min_delay: int,
        max_delay: int,
        delay_clamps: tuple[int, ...],
        delay_values: tuple[int, ...],
        cap_floor: int,
        apply_pending: bool,
    ):
        """Set withdrawal-delay parameters on-chain."""
        from tplus.model.withdrawal import WithdrawalDelayParameters

        clamps = list(delay_clamps) if delay_clamps else [0, 1_000_000]
        values = list(delay_values) if delay_values else [0, 0]
        params = WithdrawalDelayParameters(
            minDelay=min_delay,
            maxDelay=max_delay,
            delayClamps=clamps,
            delayValues=values,
            capFloor=cap_floor,
        )
        owner = _build_owner(cli_ctx, account)
        receipt = owner.set_pending_withdrawal_delay_parameters(params)
        click.echo(f"set-pending tx: {receipt.txn_hash}")

        if apply_pending:
            applied = owner.apply_pending_withdrawal_delay_parameters()
            click.echo(f"apply tx: {applied.txn_hash}")
