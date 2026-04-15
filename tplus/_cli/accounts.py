import click

from tplus._cli._context import CLIContext, pass_cli_context


@click.group()
def accounts():
    """Manage local T+ accounts."""


@accounts.command("list")
@pass_cli_context
def _list(cli_ctx: CLIContext):
    """List all local accounts."""
    names = list(cli_ctx.user_manager.usernames)
    if not names:
        click.echo("No accounts found.")
        return

    for name in names:
        click.echo(name)


def _prompt_private_key(ctx, param, value):
    if value is not None or ctx.params.get("generate"):
        return value

    return click.prompt("Enter private key (hex)", hide_input=True)


@accounts.command("add")
@click.argument("alias")
@click.option(
    "--generate",
    is_flag=True,
    is_eager=True,
    help="Generate a new Ed25519 key instead of importing one.",
)
@click.option(
    "--private-key",
    "private_key",
    callback=_prompt_private_key,
    help="Hex-encoded Ed25519 private key. Prompts if omitted.",
)
@pass_cli_context
def _add(cli_ctx: CLIContext, alias: str, generate: bool, private_key: str | None):
    """Add a new account under ALIAS."""
    manager = cli_ctx.user_manager
    if generate:
        user = manager.generate(alias)
    else:
        user = manager.add(alias, private_key)

    click.echo(f"Added account '{alias}' (pubkey: {user.public_key}).")


@accounts.command("show")
@click.argument("alias")
@pass_cli_context
def _show(cli_ctx: CLIContext, alias: str):
    """Show the public key for ALIAS."""
    user = cli_ctx.user_manager.load(alias)
    click.echo(user.public_key)
