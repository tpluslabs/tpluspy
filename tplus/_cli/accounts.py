import click

from tplus._cli._context import CLIContext, pass_cli_context
from tplus.cli_tools import echo_with_pager, no_pager_option, output_format_option, render


@click.group()
def accounts():
    """Manage local T+ accounts."""


@accounts.command("list")
@output_format_option()
@no_pager_option()
@pass_cli_context
def _list(cli_ctx: CLIContext, output_format: str, no_pager: bool):
    """List all local accounts."""
    names = list(cli_ctx.user_manager.usernames)
    if not names:
        click.echo("No accounts found.")
        return

    if output_format == "raw":
        echo_with_pager(names, no_pager=no_pager)
        return

    render([{"name": n} for n in names], output_format, no_pager=no_pager)


def _prompt_private_key(ctx, param, value):
    if value is not None:
        return value

    return click.prompt("Enter private key (hex)", hide_input=True)


@accounts.command("add")
@click.argument("alias")
@click.option(
    "--private-key",
    "private_key",
    callback=_prompt_private_key,
    help="Hex-encoded Ed25519 private key. Prompts if omitted.",
)
@pass_cli_context
def _add(cli_ctx: CLIContext, alias: str, private_key: str):
    """Import an existing private key as a new account under ALIAS."""
    user = cli_ctx.user_manager.add(alias, private_key)
    click.echo(f"Added account '{alias}' (pubkey: {user.public_key}).")


@accounts.command("generate")
@click.argument("alias")
@pass_cli_context
def _generate(cli_ctx: CLIContext, alias: str):
    """Generate a new Ed25519 account under ALIAS."""
    user = cli_ctx.user_manager.generate(alias)
    click.echo(f"Generated account '{alias}' (pubkey: {user.public_key}).")


@accounts.command("show")
@click.argument("alias")
@pass_cli_context
def _show(cli_ctx: CLIContext, alias: str):
    """Show the public key for ALIAS."""
    user = cli_ctx.user_manager.load(alias)
    click.echo(user.public_key)
