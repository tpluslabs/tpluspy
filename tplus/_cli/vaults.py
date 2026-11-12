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
    resolve_universe,
    universe_option,
    vault_address_option,
)
from tplus.utils.universe import compute_universe_id

if TYPE_CHECKING:
    from tplus.evm.managers.credential_manager import CredentialManagerOwner
    from tplus.evm.managers.vault import VaultOwner
    from tplus.model.config import ChainConfig


_EVM_AVAILABLE = importlib.util.find_spec("ape") is not None


@click.group()
def vaults():
    """Manage T+ vaults (contract owner)."""


def _list_via_oms(cli_ctx: CLIContext, output_format: str, no_pager: bool):
    client = cli_ctx.orderbook_client(anonymous=True)
    addresses = asyncio.run(client.assets.get_vaults())

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
    from tplus.evm.governance import (
        OperatorKey,
        compute_majority_threshold,
        parse_operator_public_key,
    )

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
    @click.option(
        "--genesis-manager",
        help=(
            "CredentialManager the vault's genesis snapshot is read from. Defaults to"
            " CREDENTIAL_MANAGER. Set it where that is a receiver, as on an L2."
        ),
    )
    @click.option(
        "--genesis-rpc-url",
        help="RPC of the genesis manager's chain. Defaults to the connected chain.",
    )
    def _deploy(
        account,
        credential_manager: str,
        owner: str | None,
        skip_if_deployed: bool,
        genesis_manager: str | None,
        genesis_rpc_url: str | None,
    ):
        """Deploy a new DepositVault pointing at CREDENTIAL_MANAGER."""
        from tplus.evm.contracts import DepositVault, read_genesis

        if skip_if_deployed and (adopted := DepositVault()._adopt_ce_deployment()):
            click.echo(f"reused: {adopted.address}")
            return

        genesis = None
        if genesis_manager or genesis_rpc_url:
            genesis = read_genesis(genesis_manager or credential_manager, rpc_url=genesis_rpc_url)

        instance = DepositVault.deploy_proxy(
            owner or account, credential_manager, sender=account, genesis=genesis
        )
        click.echo(f"deployed: {instance.address}")

    @vaults.command("deploy-registry", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @account_option()
    @click.argument("registry_address")
    @click.option(
        "--operator",
        "operators",
        multiple=True,
        help=(
            "Operator as ADDRESS:PUBLIC_KEY, a 64-byte public key or an Ape account alias."
            " May be repeated. Defaults to the sender."
        ),
    )
    @click.option("--quorum", type=int, help="Committee threshold. Defaults to the operator count.")
    @universe_option(help="Governance universe. Required off the local network.")
    @click.option(
        "--automata-verifier",
        "automata_verifier",
        default=ZERO_ADDRESS,
        show_default=True,
        help="Automata verifier contract address; zero accepts unverified attestation.",
    )
    @click.option(
        "--allow-unverified-attestation",
        is_flag=True,
        help="Allow a zero Automata verifier off the local network.",
    )
    @click.option(
        "--council-member",
        "security_council",
        multiple=True,
        help="Security council member address. May be repeated. Required off the local network.",
    )
    @click.option(
        "--council-threshold",
        type=int,
        help="Security council threshold. Defaults to a strict majority of the council.",
    )
    @click.option(
        "--withdrawal-quorum",
        type=int,
        default=1,
        show_default=True,
        help="Approvals required to release a withdrawal.",
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
        universe: str | None,
        automata_verifier: str,
        allow_unverified_attestation: bool,
        security_council: tuple[str, ...],
        council_threshold: int | None,
        withdrawal_quorum: int,
        skip_if_deployed: bool,
    ):
        """Deploy a new CredentialManager pointing at REGISTRY_ADDRESS."""
        from ape import chain

        from tplus.evm.contracts import CredentialManager

        if skip_if_deployed and (adopted := CredentialManager()._adopt_ce_deployment()):
            click.echo(f"reused: {adopted.address}")
            return

        is_local = chain.provider.network.is_local
        operator_public_keys = _parse_operator_public_keys(operators, account)
        universe = resolve_universe(universe, is_local)
        _validate_attestation_verifier(automata_verifier, is_local, allow_unverified_attestation)
        council = _resolve_security_council(security_council, account, is_local)
        instance = CredentialManager.deploy(
            sender=account,
            universe_id=bytes(compute_universe_id(universe)),
            operator_public_keys=operator_public_keys,
            committee_threshold=quorum or len(operator_public_keys),
            security_council=council,
            security_council_threshold=council_threshold
            or compute_majority_threshold(len(council)),
            automata_verifier=automata_verifier,
            registry=registry_address,
            withdrawal_quorum=withdrawal_quorum,
        )
        click.echo(f"deployed: {instance.address}")

    def _parse_operator_public_keys(operators: tuple[str, ...], account) -> list[bytes]:
        try:
            operator_public_keys = [parse_operator_public_key(operator) for operator in operators]
        except ValueError as err:
            raise click.BadParameter(str(err), param_hint="--operator") from err

        return operator_public_keys or [OperatorKey.from_ape_account(account).public_key]

    def _validate_attestation_verifier(
        automata_verifier: str, is_local: bool, allow_unverified_attestation: bool
    ):
        if automata_verifier == ZERO_ADDRESS and not is_local and not allow_unverified_attestation:
            raise click.UsageError(
                "--automata-verifier is required off the local network"
                " (or pass --allow-unverified-attestation)."
            )

    def _require_mainnet_confirmations(
        config: "ChainConfig", production: "ChainConfig | None", allow_zero_confirmations: bool
    ):
        from ape import chain

        on_mainnet = production is not None or chain.provider.network.is_mainnet
        if not on_mainnet or allow_zero_confirmations:
            return

        if unexpected := config.find_unexpected_zero_confirmations(production):
            raise click.UsageError(
                f"Zero {', '.join(unexpected)} on mainnet; pass non-zero counts or "
                "--allow-zero-confirmations, since a zero count credits an event before reorgs settle."
            )

    def _resolve_security_council(
        security_council: tuple[str, ...], account, is_local: bool
    ) -> list[str]:
        if security_council:
            return list(security_council)

        if not is_local:
            raise click.UsageError("--council-member is required off the local network.")

        return [account.address]

    def _build_credential_manager_owner(
        cli_ctx: CLIContext, signer, credential_manager_address: str | None = None
    ) -> "CredentialManagerOwner":
        from tplus.evm.contracts import CredentialManager
        from tplus.evm.managers.credential_manager import CredentialManagerOwner

        try:
            ce = cli_ctx.clearing_engine_client(anonymous=True)
        except click.UsageError:
            ce = None

        # Waiting on vault registration reads the vault list back from the OMS.
        try:
            assets = cli_ctx.orderbook_client(anonymous=True).assets
        except click.UsageError:
            assets = None

        credman = (
            cast("CredentialManager", CredentialManager.at(credential_manager_address))
            if credential_manager_address
            else None
        )
        return CredentialManagerOwner(
            signers=[signer],
            credential_manager=credman,
            clearing_engine=ce,
            asset_registry_client=assets,
        )

    @vaults.command("register", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @orderbook_url_option()
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
    @click.option(
        "--block-time-ms",
        "block_time_ms",
        type=int,
        help="Defaults to the chain's production value, or 0 for an unknown chain.",
    )
    @click.option(
        "--default-confirmations",
        "default_confirmations",
        type=int,
        help="Defaults to the chain's production value, or 0 for an unknown chain.",
    )
    @click.option(
        "--deposit-confirmations",
        "deposit_confirmations",
        type=int,
        help="Defaults to the chain's production value, or 0 for an unknown chain.",
    )
    @click.option(
        "--withdrawal-confirmations",
        "withdrawal_confirmations",
        type=int,
        help="Defaults to the chain's production value, or 0 for an unknown chain.",
    )
    @click.option(
        "--settlement-confirmations",
        "settlement_confirmations",
        type=int,
        help="Defaults to the chain's production value, or 0 for an unknown chain.",
    )
    @click.option(
        "--allow-zero-confirmations",
        is_flag=True,
        help="Allow a zero confirmation count on mainnet that the chain's production value does not set.",
    )
    @click.option("--wait/--no-wait", default=False, help="Wait for CE ingestion.")
    @pass_cli_context
    def _register(
        cli_ctx: CLIContext,
        account,
        vault_address: str,
        chain_id: int | None,
        block_time_ms: int | None,
        default_confirmations: int | None,
        deposit_confirmations: int | None,
        withdrawal_confirmations: int | None,
        settlement_confirmations: int | None,
        allow_zero_confirmations: bool,
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

        production = (
            ChainConfig.for_evm_chain(chain_addr.chain_id.vm_id)
            if chain_addr.chain_id.routing_id == 0
            else None
        )
        values = (production or ChainConfig.dev()).model_dump()
        overrides = {
            "blockTimeMs": block_time_ms,
            "defaultConfirmations": default_confirmations,
            "depositIngestConfirmations": deposit_confirmations,
            "withdrawalIngestConfirmations": withdrawal_confirmations,
            "settlementIngestConfirmations": settlement_confirmations,
        }
        values.update({name: value for name, value in overrides.items() if value is not None})
        config = ChainConfig(**values)
        _require_mainnet_confirmations(config, production, allow_zero_confirmations)
        owner = _build_credential_manager_owner(
            cli_ctx, account, credential_manager_address=credential_manager_address
        )
        op_id = asyncio.run(owner.add_vault(chain_addr, config, sender=account, wait=wait))
        click.echo(f"operation: {op_id.hex()}")

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

    @vaults.command("attest-signer", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @clearing_url_option()
    @ignore_ssl_option()
    @credential_manager_address_option()
    @tplus_account_option()
    @account_option()
    @click.option(
        "--signer-key",
        help="Signer public key (hex). Defaults to the CE verifying key.",
    )
    @pass_cli_context
    def _attest_signer(
        cli_ctx: CLIContext,
        account,
        signer_key: str | None,
        credential_manager_address: str | None,
    ):
        """Attest the CE signer for --account's operator, on a manager with no verifier.

        The manager commits its first governance snapshot once attested keys reach the
        withdrawal quorum, and a vault is deployed from that snapshot.
        """
        owner = _build_credential_manager_owner(
            cli_ctx, account, credential_manager_address=credential_manager_address
        )
        attested = asyncio.run(owner.attest_signer(signer_key, sender=account))
        click.echo("attested" if attested else "unchanged")

    @vaults.command("register-strategy", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @credential_manager_address_option()
    @tplus_account_option()
    @account_option()
    @pass_cli_context
    def _register_strategy(cli_ctx: CLIContext, account, credential_manager_address: str | None):
        """Register the strategy that delivers snapshots to a vault on the manager's chain."""
        owner = _build_credential_manager_owner(
            cli_ctx, account, credential_manager_address=credential_manager_address
        )
        strategy = owner.ensure_intra_chain_strategy(sender=account)
        click.echo(f"registered: {strategy}" if strategy else "unchanged")

    @vaults.command("sync", cls=ConnectedProviderCommand)
    @tplus_network_option()
    @credential_manager_address_option()
    @tplus_account_option()
    @account_option()
    @pass_cli_context
    def _sync(cli_ctx: CLIContext, account, credential_manager_address: str | None):
        """Deliver the manager's governance snapshot to the vault on this chain."""
        owner = _build_credential_manager_owner(
            cli_ctx, account, credential_manager_address=credential_manager_address
        )
        receipt = owner.sync_vault(sender=account)
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
