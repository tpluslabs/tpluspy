import asyncio
import importlib.util
from typing import TYPE_CHECKING, cast

import click

from tplus._cli._context import (
    CLIContext,
    clearing_url_option,
    orderbook_url_option,
    pass_cli_context,
    tplus_account_option,
)
from tplus.cli_tools import (
    chain_address_record,
    credential_manager_address_option,
    echo_with_pager,
    ignore_ssl_option,
    no_pager_option,
    output_format_option,
    render,
    vault_address_option,
)

if TYPE_CHECKING:
    from tplus.evm.managers.credential_manager import CredentialManagerOwner
    from tplus.evm.managers.vault import VaultOwner


_EVM_AVAILABLE = importlib.util.find_spec("ape") is not None


@click.group()
def vaults():
    """Manage T+ vaults (contract owner)."""


def _list_via_oms(cli_ctx: CLIContext, output_format: str, no_pager: bool):
    from tplus.model.chain_address import ChainAddress

    client = cli_ctx.orderbook_client(anonymous=True)
    raw = asyncio.run(client.assets.get_vaults())
    addresses = [ChainAddress.model_validate(a) for a in raw]

    if output_format == "raw":
        echo_with_pager([str(a) for a in addresses], no_pager=no_pager)
        return

    render(
        [chain_address_record(a) for a in addresses],
        output_format,
        no_pager=no_pager,
    )


@vaults.command("update-ce")
@clearing_url_option()
@ignore_ssl_option()
@pass_cli_context
def _update_ce(cli_ctx: CLIContext):
    """Re-ingest vaults from the credential manager."""
    client = cli_ctx.clearing_engine_client(anonymous=True)
    asyncio.run(client.vaults.update())
    click.echo("CE vault update requested.")


if _EVM_AVAILABLE:
    from ape.cli import ConnectedProviderCommand, account_option
    from ape.utils.misc import ZERO_ADDRESS

    from tplus.cli_tools import tplus_network_option

    @vaults.command("list")
    @click.option(
        "--oms",
        "use_oms",
        is_flag=True,
        help="Query OMS instead of the CredentialManager contract.",
    )
    @output_format_option()
    @no_pager_option()
    @tplus_network_option()
    @orderbook_url_option()
    @ignore_ssl_option()
    @credential_manager_address_option()
    @pass_cli_context
    def _list(
        cli_ctx: CLIContext,
        use_oms: bool,
        output_format: str,
        no_pager: bool,
        credential_manager_address: str | None,
        provider,
    ):
        """List vaults registered in the credential manager."""
        if use_oms:
            _list_via_oms(cli_ctx, output_format, no_pager)
            return

        from tplus.evm.contracts import CredentialManager

        with provider.connection():
            credman = (
                CredentialManager.at(credential_manager_address)
                if credential_manager_address
                else CredentialManager()
            )
            if not credman.is_deployed:
                click.echo("CredentialManager not deployed on this network.")
                return

            addresses = [v.chain_address for v in credman.get_vaults()]

        if output_format == "raw":
            echo_with_pager([str(a) for a in addresses], no_pager=no_pager)
            return

        render(
            [chain_address_record(a) for a in addresses],
            output_format,
            no_pager=no_pager,
        )

    def _build_owner(cli_ctx: CLIContext, signer, vault_address: str | None = None) -> "VaultOwner":
        from tplus.evm.contracts import DepositVault
        from tplus.evm.managers.vault import VaultOwner

        try:
            ce = cli_ctx.clearing_engine_client(anonymous=True)
        except click.UsageError:
            ce = None

        vault = cast("DepositVault", DepositVault.at(vault_address)) if vault_address else None
        return VaultOwner(owner=signer, vault=vault, clearing_engine=ce)

    @vaults.command("deploy", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @account_option()
    @click.argument("credential_manager")
    @click.option(
        "--owner",
        help="Vault owner address. Defaults to --account.",
    )
    @click.option(
        "--skip-if-deployed",
        is_flag=True,
        help="Reuse the latest CE-registered vault on this chain if live.",
    )
    def _deploy(account, credential_manager: str, owner: str | None, skip_if_deployed: bool):
        """Deploy a new DepositVault pointing at CREDENTIAL_MANAGER."""
        from tplus.evm.contracts import DepositVault

        if skip_if_deployed and (adopted := DepositVault()._adopt_ce_deployment()):
            click.echo(f"reused: {adopted.address}")
            return

        instance = DepositVault.deploy(owner or account, credential_manager, sender=account)
        click.echo(f"deployed: {instance.address}")

    @vaults.command("deploy-registry", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @account_option()
    @click.argument("registry_address")
    @click.option(
        "--operator",
        "operators",
        multiple=True,
        help="Operator address. May be repeated. Defaults to the sender.",
    )
    @click.option(
        "--quorum", type=int, help="Operator quorum threshold. Defaults to len(operators)."
    )
    @click.option(
        "--measurement",
        "measurements",
        multiple=True,
        help="Initial approved measurement (hex). May be repeated.",
    )
    @click.option(
        "--automata-verifier",
        "automata_verifier",
        default=ZERO_ADDRESS,
        show_default=True,
        help="Automata verifier contract address.",
    )
    @click.option(
        "--skip-if-deployed",
        is_flag=True,
        help="Reuse the CE-registered CredentialManager on this chain if live.",
    )
    def _deploy_registry(
        account,
        registry_address: str,
        operators: tuple[str, ...],
        quorum: int | None,
        measurements: tuple[str, ...],
        automata_verifier: str,
        skip_if_deployed: bool,
    ):
        """Deploy a new CredentialManager pointing at REGISTRY_ADDRESS."""
        from tplus.evm.contracts import CredentialManager

        if skip_if_deployed and (adopted := CredentialManager()._adopt_ce_deployment()):
            click.echo(f"reused: {adopted.address}")
            return

        op_list = list(operators) or [account.address]
        threshold = quorum if quorum is not None else len(op_list)
        meas = [bytes.fromhex(m.removeprefix("0x")) for m in measurements]
        instance = CredentialManager.deploy(
            op_list,
            threshold,
            account,
            registry_address,
            meas,
            automata_verifier,
            sender=account,
        )
        click.echo(f"deployed: {instance.address}")

    def _build_credential_manager_owner(
        cli_ctx: CLIContext, signer, credential_manager_address: str | None = None
    ) -> "CredentialManagerOwner":
        from tplus.evm.contracts import CredentialManager
        from tplus.evm.managers.credential_manager import CredentialManagerOwner

        try:
            ce = cli_ctx.clearing_engine_client(anonymous=True)
        except click.UsageError:
            ce = None

        credman = (
            cast("CredentialManager", CredentialManager.at(credential_manager_address))
            if credential_manager_address
            else None
        )
        return CredentialManagerOwner(
            admin=signer, signers=[signer], credential_manager=credman, clearing_engine=ce
        )

    @vaults.command("register", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @credential_manager_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("vault_address")
    @click.option(
        "--chain-id",
        "chain_id",
        type=int,
        help="Chain ID (EVM) if VAULT_ADDRESS doesn't include @chain.",
    )
    @click.option("--block-time-ms", "block_time_ms", type=int, default=0, show_default=True)
    @click.option(
        "--default-confirmations", "default_confirmations", type=int, default=0, show_default=True
    )
    @click.option(
        "--deposit-confirmations", "deposit_confirmations", type=int, default=0, show_default=True
    )
    @click.option(
        "--withdrawal-confirmations",
        "withdrawal_confirmations",
        type=int,
        default=0,
        show_default=True,
    )
    @click.option(
        "--settlement-confirmations",
        "settlement_confirmations",
        type=int,
        default=0,
        show_default=True,
    )
    @click.option("--wait/--no-wait", default=False, help="Wait for CE ingestion.")
    @pass_cli_context
    def _register(
        cli_ctx: CLIContext,
        account,
        vault_address: str,
        chain_id: int | None,
        block_time_ms: int,
        default_confirmations: int,
        deposit_confirmations: int,
        withdrawal_confirmations: int,
        settlement_confirmations: int,
        wait: bool,
        credential_manager_address: str | None,
    ):
        """Register VAULT_ADDRESS with the credential manager."""
        from tplus.model.asset_identifier import ChainAddress
        from tplus.model.config import ChainConfig

        if "@" in vault_address:
            chain_addr = ChainAddress.from_str(vault_address)
        elif chain_id is not None:
            chain_addr = ChainAddress.from_evm_address(vault_address, chain_id)
        else:
            raise click.UsageError("Pass --chain-id or include @<chain> in VAULT_ADDRESS.")

        config = ChainConfig(
            blockTimeMs=block_time_ms,
            defaultConfirmations=default_confirmations,
            depositIngestConfirmations=deposit_confirmations,
            withdrawalIngestConfirmations=withdrawal_confirmations,
            settlementIngestConfirmations=settlement_confirmations,
        )
        owner = _build_credential_manager_owner(
            cli_ctx, account, credential_manager_address=credential_manager_address
        )
        receipt = asyncio.run(owner.add_vault(chain_addr, config, sender=account, wait=wait))
        click.echo(f"tx: {receipt.txn_hash}")

    @vaults.command("set-domain-separator", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @vault_address_option()
    @tplus_account_option()
    @account_option()
    @click.option("--separator", help="Hex-encoded domain separator. Computed if omitted.")
    @pass_cli_context
    def _set_domain_separator(
        cli_ctx: CLIContext, account, separator: str | None, vault_address: str | None
    ):
        """Set the vault's domain separator."""
        owner = _build_owner(cli_ctx, account, vault_address=vault_address)
        value = bytes.fromhex(separator.removeprefix("0x")) if separator else None
        receipt = owner.set_domain_separator(value)
        click.echo(f"tx: {receipt.txn_hash}")

    @vaults.command("set-credential-manager", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @vault_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("address")
    @pass_cli_context
    def _set_credential_manager(
        cli_ctx: CLIContext, account, address: str, vault_address: str | None
    ):
        """Set the vault's stored credentialManager pointer to ADDRESS."""
        owner = _build_owner(cli_ctx, account, vault_address=vault_address)
        receipt = owner.set_credential_manager(address)
        click.echo(f"tx: {receipt.txn_hash}")

    @vaults.command("admins")
    @output_format_option()
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @vault_address_option()
    @pass_cli_context
    def _admins(cli_ctx: CLIContext, output_format: str, vault_address: str | None, provider):
        """Show vault admins and CE verifying key.

        If ``settle execute`` reverts with ``InvalidSignature()`` the address
        derived from the CE's verifying key must appear in the on-chain admin list
        — otherwise the vault's ``checkApproval`` will never accept a CE signature.
        """
        from tplus.evm.address import public_key_to_address
        from tplus.evm.contracts import DepositVault

        on_chain: list[str] = []
        with provider.connection():
            vault_instance = (
                DepositVault.at(vault_address) if vault_address else DepositVault.from_ce_address()
            )
            i = 0
            while True:
                try:
                    on_chain.append(str(vault_instance.contract.administrators(i)))
                except Exception:
                    break
                i += 1

        try:
            ce = cli_ctx.clearing_engine_client(anonymous=True)
            verifying_key = asyncio.run(ce.admin.get_verifying_key())
            ce_error: str | None = None
        except Exception as err:
            verifying_key = None
            ce_error = str(err)

        ce_admin_address = public_key_to_address(verifying_key) if verifying_key else None
        on_chain_norm = {a.lower() for a in on_chain}
        matches = ce_admin_address is not None and ce_admin_address.lower() in on_chain_norm

        record = {
            "on_chain_admins": on_chain,
            "ce_verifying_key": verifying_key,
            "ce_admin_address": ce_admin_address,
            "ce_key_is_admin": matches,
            "ce_error": ce_error,
        }
        render([record], output_format)

    @vaults.command("set-administrators", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @vault_address_option()
    @tplus_account_option()
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
        cli_ctx: CLIContext,
        account,
        admin_keys: tuple[str, ...],
        quorum: int | None,
        vault_address: str | None,
    ):
        """Set vault administrators."""
        owner = _build_owner(cli_ctx, account, vault_address=vault_address)
        receipt = asyncio.run(
            owner.set_administrators(
                admin_keys=list(admin_keys) if admin_keys else None,
                withdrawal_quorum=quorum,
            )
        )
        click.echo(f"tx: {receipt.txn_hash}")

    @vaults.command("register-settler", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @vault_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("settler")
    @click.option("--executor", required=True, help="Executor address.")
    @click.option("--wait/--no-wait", default=False, help="Wait for CE ingestion.")
    @pass_cli_context
    def _register_settler(
        cli_ctx: CLIContext,
        account,
        settler: str,
        executor: str,
        wait: bool,
        vault_address: str | None,
    ):
        """Register SETTLER (tplus alias or public key) with EXECUTOR."""
        from tplus.model.types import UserPublicKey

        owner = _build_owner(cli_ctx, account, vault_address=vault_address)

        try:
            user = cli_ctx.user_manager.load(settler)
            settler_arg = user.public_key
        except ValueError:
            settler_arg = UserPublicKey(settler)

        receipt = asyncio.run(owner.register_settler(settler_arg, executor, wait=wait))
        click.echo(f"tx: {receipt.txn_hash}")

    @vaults.command("register-depositor", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @vault_address_option()
    @tplus_account_option()
    @account_option()
    @click.argument("depositor")
    @pass_cli_context
    def _register_depositor(
        cli_ctx: CLIContext, account, depositor: str, vault_address: str | None
    ):
        """Allow DEPOSITOR to call deposit()."""
        owner = _build_owner(cli_ctx, account, vault_address=vault_address)
        receipt = asyncio.run(owner.register_depositor(depositor))
        click.echo(f"tx: {receipt.txn_hash}")

else:

    @vaults.command("list")
    @output_format_option()
    @no_pager_option()
    @orderbook_url_option()
    @ignore_ssl_option()
    @pass_cli_context
    def _list(
        cli_ctx: CLIContext,
        output_format: str,
        no_pager: bool,
    ):
        """List vaults (queried from OMS).

        Reading directly from the CredentialManager contract requires the
        ``[evm]`` extras: ``pip install 'tpluspy[evm]'``.
        """
        _list_via_oms(cli_ctx, output_format, no_pager)
