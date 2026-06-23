import copy
import importlib
import importlib.util
import logging
import logging.handlers
from pathlib import Path

import click

from tplus.exceptions import BadPasswordError

LOG_DIR = Path.home() / ".tplus" / "cli" / "logs"
LOG_FILE = "tplus.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3

_CORE_COMMANDS = {
    "accounts": "tplus._cli.accounts:accounts",
    "assets": "tplus._cli.assets:assets",
    "balance": "tplus._cli.balance:balance",
    "debug": "tplus._cli.debug:debug",
    "decimals": "tplus._cli.decimals:decimals",
    "env": "tplus._cli.env:env",
    "markets": "tplus._cli.markets:markets",
    "orders": "tplus._cli.orders:orders",
    "params": "tplus._cli.params:params",
    "sign": "tplus._cli.sign:sign",
    "stream": "tplus._cli.stream:stream",
    "trades": "tplus._cli.trades:trades",
    "vaults": "tplus._cli.vaults:vaults",
    "withdraw": "tplus._cli.withdraw:withdraw",
    "withdrawal": "tplus._cli.withdrawal:withdrawal",
}

_EVM_COMMANDS = {
    "deposit": "tplus._cli.deposit:deposit",
    "settle": "tplus._cli.settle:settle",
}

_HIDDEN_ALIASES = {
    "wd": "tplus._cli.withdraw:withdraw",
}


def _configure_logging():
    root = logging.getLogger()
    if root.handlers:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _evm_available() -> bool:
    return importlib.util.find_spec("ape") is not None


def _resolve_lazy(import_path: str):
    modname, _, attr = import_path.partition(":")
    return getattr(importlib.import_module(modname), attr)


class LazyGroup(click.Group):
    def __init__(self, *args, lazy_subcommands=None, hidden_aliases=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lazy_subcommands = dict(lazy_subcommands or {})
        self.hidden_aliases = dict(hidden_aliases or {})

    def list_commands(self, ctx):
        return sorted({*super().list_commands(ctx), *self.lazy_subcommands.keys()})

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except BadPasswordError as e:
            raise click.ClickException(str(e)) from e

    def get_command(self, ctx, cmd_name):
        if cmd_name in self.lazy_subcommands:
            return _resolve_lazy(self.lazy_subcommands[cmd_name])

        if cmd_name in self.hidden_aliases:
            cmd = copy.copy(_resolve_lazy(self.hidden_aliases[cmd_name]))
            cmd.hidden = True
            return cmd

        return super().get_command(ctx, cmd_name)


def _build_subcommands() -> dict[str, str]:
    if _evm_available():
        return {**_CORE_COMMANDS, **_EVM_COMMANDS}

    return _CORE_COMMANDS


@click.group(
    cls=LazyGroup,
    lazy_subcommands=_build_subcommands(),
    hidden_aliases=_HIDDEN_ALIASES if _evm_available() else {},
)
@click.version_option(package_name="tpluspy")
def cli():
    """T+ command line interface."""
    _configure_logging()


if not _evm_available():
    cli.epilog = (
        "On-chain commands (deposit, settle) and on-chain subcommands of "
        "assets/vault/params/withdraw/withdrawal (deploy, set, register, init, "
        "execute, ...) require the 'evm' extra: pip install 'tpluspy[evm]'. "
        "Read-only CE-backed subcommands (e.g. 'list', 'get', 'update-ce') "
        "remain available."
    )
