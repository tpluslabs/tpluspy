import os
from collections.abc import Callable
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

import click

if TYPE_CHECKING:
    from tplus.client.blockchain import BlockchainClient
    from tplus.client.clearingengine import ClearingEngineClient
    from tplus.client.market_data import MarketDataClient
    from tplus.client.orderbook import OrderBookClient
    from tplus.client.withdrawal import WithdrawalClient
    from tplus.utils.user.manager import UserManager
    from tplus.utils.user.model import User


_AUTH_CACHE_DIR = Path.home() / ".tplus" / "auth"


def _derive_market_data_base_url(oms_base_url: str) -> str:
    """Derive the market-data-service URL from the OMS URL (swap the host label
    ``oms``->``mds``). Returns the input unchanged for non-oms hosts (e.g. localhost)."""
    parsed = urlsplit(oms_base_url)
    host = parsed.hostname
    if host is None:
        return oms_base_url
    if host.startswith("oms."):
        mds_host = f"mds.{host.removeprefix('oms.')}"
    elif host.startswith("oms-"):
        mds_host = f"mds-{host.removeprefix('oms-')}"
    else:
        return oms_base_url
    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo = f"{userinfo}:{parsed.password}"
        userinfo = f"{userinfo}@"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (parsed.scheme, f"{userinfo}{mds_host}{port}", parsed.path, parsed.query, parsed.fragment)
    )


# ``dict`` base mirrors ``ape.cli.options.ApeCliContextObject`` so ape's
# ``network_option`` callback can do ``ctx.obj["network"] = value`` without
# importing ape here (which would slow down ``tplus --help``).
class CLIContext(dict):
    def __init__(self):
        super().__init__()
        self.api_base_url: str | None = None
        self.orderbook_base_url: str | None = None
        self.clearing_base_url: str | None = None
        self.market_data_base_url: str | None = None
        self.blockchain_base_url: str | None = None
        self.account: str | None = None
        self.ignore_ssl: bool = False

    @cached_property
    def user_manager(self) -> "UserManager":
        from tplus.utils.user.manager import UserManager

        return UserManager()

    def load_user(self, alias: str | None = None) -> "User":
        name = alias or self.account or self._resolve_default_account()
        if not name:
            raise click.UsageError(
                "No account specified and no default set. "
                "Pass --tplus-account, set TPLUS_ACCOUNT, "
                "or create one with `tplus accounts add`."
            )
        return self.user_manager.load(name)

    def _resolve_default_account(self) -> str | None:
        manager = self.user_manager
        return manager._default_user or next(iter(manager.usernames), None)

    def _api_base_url(self) -> str | None:
        """The single T+ base URL (the OMS). Per-service URLs derive from it; an
        explicit per-service flag / env var overrides it."""
        return self.api_base_url or os.environ.get("TPLUS_API_BASE_URL")

    def _resolved_orderbook_url(self) -> str:
        # The OMS host *is* the orderbook service, so TPLUS_API_BASE_URL is used directly.
        url = self.orderbook_base_url or self._api_base_url()
        if not url:
            raise click.UsageError(
                "No T+ base URL. Set TPLUS_API_BASE_URL (the OMS URL — the single T+ URL "
                "everything derives from), or pass --orderbook-base-url / set "
                "TPLUS_ORDERBOOK_BASE_URL to override."
            )
        return url

    def _resolved_market_data_url(self) -> str:
        if self.market_data_base_url:
            return self.market_data_base_url
        api = self._api_base_url()
        if not api:
            raise click.UsageError(
                "No T+ base URL. Set TPLUS_API_BASE_URL (the market-data URL is derived "
                "by swapping the host label oms->mds), or pass --market-data-base-url / "
                "set TPLUS_MARKET_DATA_BASE_URL to override."
            )
        return _derive_market_data_base_url(api)

    def orderbook_client(
        self, alias: str | None = None, *, anonymous: bool = False
    ) -> "OrderBookClient":
        from tplus.client.auth import Auth
        from tplus.client.orderbook import OrderBookClient
        from tplus.utils.user.model import User

        user = User() if anonymous else self.load_user(alias)
        return OrderBookClient(
            base_url=self._resolved_orderbook_url(),
            default_user=user,
            auth=Auth(cache_dir=_AUTH_CACHE_DIR),
            insecure_ssl=self.ignore_ssl,
        )

    def clearing_engine_client(
        self, alias: str | None = None, *, anonymous: bool = False
    ) -> "ClearingEngineClient":
        if not self.clearing_base_url:
            raise click.UsageError(
                "No clearing engine base URL specified. "
                "Pass --clearing-base-url or set TPLUS_CLEARING_BASE_URL."
            )

        from tplus.client.clearingengine import ClearingEngineClient
        from tplus.utils.user.model import User

        user = User() if anonymous else self.load_user(alias)
        return ClearingEngineClient(
            base_url=self.clearing_base_url,
            default_user=user,
            insecure_ssl=self.ignore_ssl,
        )

    def _oms_base_url(self) -> str:
        return self._resolved_orderbook_url()

    def withdrawal_client(self, alias: str | None = None) -> "WithdrawalClient":
        from tplus.client.withdrawal import WithdrawalClient

        return WithdrawalClient(
            base_url=self._oms_base_url(),
            default_user=self.load_user(alias),
            insecure_ssl=self.ignore_ssl,
        )

    def blockchain_client(self) -> "BlockchainClient":
        if not self.blockchain_base_url:
            raise click.UsageError(
                "No blockchain client base URL specified. "
                "Pass --blockchain-base-url or set TPLUS_BLOCKCHAIN_BASE_URL."
            )

        from tplus.client.blockchain import BlockchainClient

        return BlockchainClient(base_url=self.blockchain_base_url, insecure_ssl=self.ignore_ssl)

    def market_data_client(self) -> "MarketDataClient":
        from tplus.client.market_data import MarketDataClient

        return MarketDataClient(
            base_url=self._resolved_market_data_url(),
            insecure_ssl=self.ignore_ssl,
        )


pass_cli_context = click.make_pass_decorator(CLIContext, ensure=True)


def _set_on_ctx(field: str) -> Callable:
    def callback(ctx: click.Context, _param, value):
        if value is None:
            return
        cli_ctx = ctx.ensure_object(CLIContext)
        setattr(cli_ctx, field, value)

    return callback


def orderbook_url_option() -> Callable:
    return click.option(
        "--orderbook-base-url",
        envvar="TPLUS_ORDERBOOK_BASE_URL",
        help="T+ orderbook service base URL.",
        callback=_set_on_ctx("orderbook_base_url"),
        expose_value=False,
    )


def clearing_url_option() -> Callable:
    return click.option(
        "--clearing-base-url",
        envvar="TPLUS_CLEARING_BASE_URL",
        help="T+ clearing engine base URL.",
        callback=_set_on_ctx("clearing_base_url"),
        expose_value=False,
    )


def market_data_url_option() -> Callable:
    return click.option(
        "--market-data-base-url",
        envvar="TPLUS_MARKET_DATA_BASE_URL",
        help="T+ market-data service base URL.",
        callback=_set_on_ctx("market_data_base_url"),
        expose_value=False,
    )


def blockchain_url_option() -> Callable:
    return click.option(
        "--blockchain-base-url",
        envvar="TPLUS_BLOCKCHAIN_BASE_URL",
        help="T+ blockchain client base URL.",
        callback=_set_on_ctx("blockchain_base_url"),
        expose_value=False,
    )


def tplus_account_option() -> Callable:
    def callback(ctx: click.Context, _param, value):
        cli_ctx = ctx.ensure_object(CLIContext)
        cli_ctx.account = value or cli_ctx._resolve_default_account()

    return click.option(
        "--tplus-account",
        envvar="TPLUS_ACCOUNT",
        help="T+ account alias (Ed25519 signer). Defaults to the default account.",
        callback=callback,
        expose_value=False,
    )
