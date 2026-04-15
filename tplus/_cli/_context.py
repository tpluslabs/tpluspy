from functools import cached_property

import click

from tplus.client.clearingengine import ClearingEngineClient
from tplus.client.orderbook import OrderBookClient
from tplus.utils.user.manager import UserManager
from tplus.utils.user.model import User


class CLIContext:
    def __init__(self):
        self.orderbook_base_url: str | None = None
        self.clearing_base_url: str | None = None
        self.account: str | None = None

    @cached_property
    def user_manager(self) -> UserManager:
        return UserManager()

    def load_user(self, alias: str | None = None) -> User:
        name = alias or self.account
        if not name:
            raise click.UsageError(
                "No account specified. Pass --account or set TPLUS_ACCOUNT."
            )
        return self.user_manager.load(name)

    def orderbook_client(self, alias: str | None = None) -> OrderBookClient:
        if not self.orderbook_base_url:
            raise click.UsageError(
                "No orderbook base URL specified. "
                "Pass --orderbook-base-url or set TPLUS_ORDERBOOK_BASE_URL."
            )
        return OrderBookClient(self.load_user(alias), base_url=self.orderbook_base_url)

    def clearing_engine_client(self, alias: str | None = None) -> ClearingEngineClient:
        if not self.clearing_base_url:
            raise click.UsageError(
                "No clearing engine base URL specified. "
                "Pass --clearing-base-url or set TPLUS_CLEARING_BASE_URL."
            )
        return ClearingEngineClient(self.load_user(alias), base_url=self.clearing_base_url)


pass_cli_context = click.make_pass_decorator(CLIContext, ensure=True)
