import sys

import click

from tplus._cli._context import CLIContext, pass_cli_context


@click.command()
@click.option("--account", "alias", required=True, help="Account alias to sign with.")
@click.option("--message", "-m", "message", help="Message to sign. If omitted, read from stdin.")
@pass_cli_context
def sign(cli_ctx: CLIContext, alias: str, message: str | None):
    """Sign a message with the given account's key."""
    payload = message if message is not None else sys.stdin.read()
    if not payload:
        raise click.UsageError("No message provided (pass --message or pipe via stdin).")

    user = cli_ctx.user_manager.load(alias)
    signature = user.sign(payload)
    click.echo(signature.hex())
