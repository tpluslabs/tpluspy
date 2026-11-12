import json
import os

from tplus._cli import cli
from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.market import ChainAsset, MarketAsset, MarketResponse, MarketsPage

from .conftest import PRIVATE_KEY_HEX

ORDERBOOK_URL = "http://orderbook.test"


def _market(asset_id: str, asset: MarketAsset | None = None) -> MarketResponse:
    return MarketResponse(
        asset_id=AssetIdentifier(asset_id),
        book_price_decimals=2,
        book_quantity_decimals=4,
        asset=asset or MarketAsset(),
    )


def _page_of(markets: list[MarketResponse], page: int, next_page: int | None) -> MarketsPage:
    return MarketsPage(
        page=page,
        limit=len(markets),
        total_pages=2,
        cursor_size=len(markets),
        has_next_page=next_page is not None,
        next_page=next_page,
        markets=markets,
        total_markets=2 * len(markets),
    )


def _page(asset_id: str, page: int, next_page: int | None) -> MarketsPage:
    return _page_of([_market(asset_id)], page, next_page)


def test_markets_list_follows_pagination(runner, user_dir, mocker):
    runner.invoke(cli, ["accounts", "add", "trader", "--private-key", PRIVATE_KEY_HEX])
    mocker.patch.dict(
        os.environ, {"TPLUS_ACCOUNT": "trader", "TPLUS_ORDERBOOK_BASE_URL": ORDERBOOK_URL}
    )

    requested: list[int | None] = []

    async def fake_get_markets(self, *, page=None, limit=None):
        requested.append(page)
        return _page("1", 0, 1) if page is None else _page("2", 1, None)

    mocker.patch.object(OrderBookClient, "get_markets", fake_get_markets)

    result = runner.invoke(cli, ["markets", "list", "--output-format", "raw", "--no-pager"])
    assert result.exit_code == 0, result.output
    assert requested == [None, 1]
    assert [market["asset_id"] for market in json.loads(result.output)] == ["1", "2"]


def test_markets_list_page_option_fetches_one_page(runner, user_dir, mocker):
    runner.invoke(cli, ["accounts", "add", "trader", "--private-key", PRIVATE_KEY_HEX])
    mocker.patch.dict(
        os.environ, {"TPLUS_ACCOUNT": "trader", "TPLUS_ORDERBOOK_BASE_URL": ORDERBOOK_URL}
    )

    requested: list[int | None] = []

    async def fake_get_markets(self, *, page=None, limit=None):
        requested.append(page)
        return _page("1", 0, 1)

    mocker.patch.object(OrderBookClient, "get_markets", fake_get_markets)

    result = runner.invoke(
        cli, ["markets", "list", "--output-format", "raw", "--no-pager", "--page", "0"]
    )
    assert result.exit_code == 0, result.output
    assert requested == [0]


ADDRESS_ASSET_ID = (
    "82af49447d8a07e3bd95bd0d56f35241523fbab1000000000000000000000000@00000000000000a4b1"
)
ETH_CHAIN_ASSET = ChainAsset(
    chain="arbitrum",
    chain_id="42161",
    address="0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
)


def _symbol_map_markets_pages(mocker):
    """Serve `/markets` in an order the command has to regroup."""
    mocker.patch.dict(
        os.environ, {"TPLUS_ACCOUNT": "trader", "TPLUS_ORDERBOOK_BASE_URL": ORDERBOOK_URL}
    )
    pages = {
        None: _page_of([_market(ADDRESS_ASSET_ID), _market("1")], 0, 1),
        1: _page_of(
            [
                _market(
                    "2",
                    MarketAsset(
                        symbol="BTC",
                        name="Bitcoin",
                        asset_class="crypto",
                        representations=["BTC", "XBT"],
                    ),
                ),
                _market(
                    "3",
                    MarketAsset(
                        symbol="ETH",
                        name="Ether",
                        asset_class="crypto",
                        representations=["ETH"],
                        chain_assets=[ETH_CHAIN_ASSET],
                    ),
                ),
            ],
            1,
            None,
        ),
    }

    async def fake_get_markets(self, *, page=None, limit=None):
        return pages[page]

    mocker.patch.object(OrderBookClient, "get_markets", fake_get_markets)


def test_markets_symbol_map_raw_groups_markets_by_symbol(runner, user_dir, mocker):
    runner.invoke(cli, ["accounts", "add", "trader", "--private-key", PRIVATE_KEY_HEX])
    _symbol_map_markets_pages(mocker)

    result = runner.invoke(cli, ["markets", "symbol-map", "--output-format", "raw", "--no-pager"])
    assert result.exit_code == 0, result.output

    raw = json.loads(result.output)
    # Symbols first, then the index id without one, then the address id; each group keeps the
    # `/markets` order.
    assert list(raw) == ["2", "3", "1", ADDRESS_ASSET_ID]
    assert raw["2"] == {
        "symbol": "BTC",
        "name": "Bitcoin",
        "asset_class": "crypto",
        "representations": ["BTC", "XBT"],
        "chain_assets": None,
    }
    assert raw["3"]["chain_assets"] == [
        {
            "chain": "arbitrum",
            "chain_id": "42161",
            "address": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
        }
    ]
    assert raw["1"] == raw[ADDRESS_ASSET_ID] == MarketAsset().model_dump()


def test_markets_symbol_map_table_renders_every_column(runner, user_dir, mocker):
    runner.invoke(cli, ["accounts", "add", "trader", "--private-key", PRIVATE_KEY_HEX])
    _symbol_map_markets_pages(mocker)

    result = runner.invoke(cli, ["markets", "symbol-map", "--no-pager"])
    assert result.exit_code == 0, result.output

    lines = result.output.splitlines()
    assert [line for line in lines if line.startswith("asset_id=")] == [
        "asset_id=2",
        "asset_id=3",
        "asset_id=1",
        f"asset_id={ADDRESS_ASSET_ID}",
    ]
    assert any(line.split() == ["representations", "BTC,", "XBT"] for line in lines), result.output
    assert any(
        line.split() == ["chain_assets", "arbitrum", ETH_CHAIN_ASSET.address] for line in lines
    ), result.output
