import click

from tplus._cli._context import CLIContext, pass_cli_context, tplus_account_option


@click.command()
@tplus_account_option()
@click.option("--message", "-m", "message", help="Message to sign. Prompts if omitted.")
@pass_cli_context
def sign(cli_ctx: CLIContext, message: str | None):
    """Sign a message with the active account's key."""
    payload = message if message is not None else click.prompt("Message", type=str)
    if not payload:
        raise click.UsageError("No message provided.")

    user = cli_ctx.load_user()
    signature = user.sign(payload)
    click.echo(signature.hex())
