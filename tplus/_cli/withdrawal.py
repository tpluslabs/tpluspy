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
    describe_schedule_event,
    ignore_ssl_option,
    op_id_option,
    withdrawal_delay_options,
)

if TYPE_CHECKING:
    from tplus.evm.managers.registry import RegistryOwner
    from tplus.model.withdrawal import WithdrawalDelayParameters


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

    def _build_withdrawal_delay_parameters(
        min_delay: int,
        max_delay: int,
        delay_clamps: tuple[int, ...],
        delay_values: tuple[int, ...],
        cap_floor: int,
    ) -> "WithdrawalDelayParameters":
        from tplus.model.withdrawal import WithdrawalDelayParameters

        return WithdrawalDelayParameters(
            minDelay=min_delay,
            maxDelay=max_delay,
            delayClamps=list(delay_clamps) if delay_clamps else [0, 1_000_000],
            delayValues=list(delay_values) if delay_values else [0, 0],
            capFloor=cap_floor,
        )

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
    @withdrawal_delay_options()
    @click.option(
        "--execute/--no-execute",
        "execute_when_due",
        default=True,
        help=(
            "Execute the params once scheduled, when no delay applies. "
            "Pass `--no-execute` to leave them scheduled."
        ),
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
        execute_when_due: bool,
    ):
        """Schedule withdrawal-delay parameters, signed by the account as the risk council."""
        from tplus.evm.governance import is_operation_due

        params = _build_withdrawal_delay_parameters(
            min_delay, max_delay, delay_clamps, delay_values, cap_floor
        )
        owner = _build_owner(cli_ctx, account)
        if not execute_when_due:
            schedule_event = owner.schedule_operation("WITHDRAWAL_DELAY_PARAMETERS", [params])
            click.echo(describe_schedule_event(schedule_event))
            return

        schedule_event = owner.schedule_and_execute_if_due("WITHDRAWAL_DELAY_PARAMETERS", [params])
        if is_operation_due(schedule_event, owner.registry.backend):
            click.echo("withdrawal-delay parameters applied")
        else:
            click.echo(describe_schedule_event(schedule_event))

    @_params.command("execute", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @tplus_account_option()
    @account_option()
    @withdrawal_delay_options()
    @op_id_option()
    @pass_cli_context
    def _execute(
        cli_ctx: CLIContext,
        account,
        min_delay: int,
        max_delay: int,
        delay_clamps: tuple[int, ...],
        delay_values: tuple[int, ...],
        cap_floor: int,
        op_id: bytes,
    ):
        """Execute the scheduled withdrawal-delay parameters."""
        params = _build_withdrawal_delay_parameters(
            min_delay, max_delay, delay_clamps, delay_values, cap_floor
        )
        owner = _build_owner(cli_ctx, account)
        receipt = owner.execute_operation("WITHDRAWAL_DELAY_PARAMETERS", [params], op_id)
        click.echo(f"tx: {receipt.txn_hash}")
