"""Unified client for the T+ API gateway (one origin fronting OMS + MDS)."""

from typing import Any

from tplus.client.auth import Auth, AuthenticatedClient
from tplus.client.market_data import MarketDataClient
from tplus.client.orderbook import OrderBookClient

DEFAULT_BASE_URL = "http://localhost:8080"


class TplusApiClient(AuthenticatedClient):
    """Client for the T+ API gateway.

    The gateway is a reverse proxy exposing both the OMS and the MDS behind one
    origin. OMS and MDS are separate token authorities, so the service namespaces
    share one HTTP connection but maintain independent auth sessions:

    - ``.oms`` — :class:`OrderBookClient` (orders, inventory, positions, margin).
    - ``.mds`` — :class:`MarketDataClient` (klines, depth, tickers, user trades).

    It is a **drop-in replacement** for either sub-client: any method not defined
    on the facade itself is proxied to ``.oms`` first, then ``.mds`` (OMS is the
    primary trading surface), so code written against one sub-client keeps working
    when swapped to this facade. Use ``.oms`` / ``.mds`` explicitly to disambiguate
    when both define the same name.

    Closing this client (or exiting its ``async with`` block) closes the one
    shared connection.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, **kwargs) -> None:
        super().__init__(base_url, **kwargs)
        self.oms = OrderBookClient.from_client(self)
        self.mds = MarketDataClient.from_client(
            self,
            auth=Auth(cache_dir=self._auth.cache_dir),
            auth_path_prefix="/market-data",
        )

    def __getattr__(self, name: str) -> Any:
        # Only reached when normal lookup fails, so real inherited attributes
        # (_client, _auth, oms, mds, close, …) never hit this path.
        if name.startswith("_"):
            raise AttributeError(name)

        for sub_client in ("oms", "mds"):
            # __dict__ avoids re-entering __getattr__ before __init__ assigns them.
            client = self.__dict__.get(sub_client)
            if client is not None and hasattr(client, name):
                return getattr(client, name)

        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
