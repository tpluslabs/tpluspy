import os

import click

from tplus._cli._context import CLIContext
from tplus.cli_tools import output_format_option, render
from tplus.cli_tools.options import TPLUS_DEFAULT_BLOCKCHAIN_NETWORK


def _default_account() -> str:
    try:
        return CLIContext()._resolve_default_account() or ""
    except Exception:
        return ""


@click.command("env")
@output_format_option()
def env(output_format: str):
    """Show CLI-relevant environment variables and their current values."""
    entries: list[tuple[str, str, str]] = [
        ("TPLUS_ACCOUNT", _default_account(), "Default local account alias."),
        ("TPLUS_ORDERBOOK_BASE_URL", "", "Orderbook service base URL."),
        ("TPLUS_CLEARING_BASE_URL", "", "Clearing engine base URL."),
        ("TPLUS_IGNORE_SSL", "false", "Skip TLS certificate verification."),
        ("TPLUS_OUTPUT_FORMAT", "table", "Default output format (table | json)."),
        (
            "TPLUS_DEFAULT_BLOCKCHAIN_NETWORK",
            TPLUS_DEFAULT_BLOCKCHAIN_NETWORK,
            "Default Ape network for --network.",
        ),
        (
            "TPLUS_CONTRACTS_PATH",
            "~/tplus/tplus-contracts",
            "Path to a local tplus-contracts checkout.",
        ),
    ]
    records = [
        {
            "name": name,
            "set": name in os.environ,
            "value": os.environ.get(name, ""),
            "default": default,
            "purpose": purpose,
        }
        for name, default, purpose in entries
    ]
    render(records, output_format)
