import json
import os

from tplus._cli import cli
from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.market import MarketResponse, MarketsPage

from .conftest import PRIVATE_KEY_HEX

ORDERBOOK_URL = "http://orderbook.test"


def _page(asset_id: str, page: int, next_page: int | None) -> MarketsPage:
    return MarketsPage(
        page=page,
        limit=1,
        total_pages=2,
        cursor_size=1,
        has_next_page=next_page is not None,
        next_page=next_page,
        markets=[
            MarketResponse(
                asset_id=AssetIdentifier(asset_id),
                book_price_decimals=2,
                book_quantity_decimals=4,
            )
        ],
        total_markets=2,
    )


def test_markets_list_follows_pagination(runner, user_dir, mocker):
    runner.invoke(cli, ["accounts", "add", "trader", "--private-key", PRIVATE_KEY_HEX])
    mocker.patch.dict(
        os.environ, {"TPLUS_ACCOUNT": "trader", "TPLUS_ORDERBOOK_BASE_URL": ORDERBOOK_URL}
    )

    requested: list[int | None] = []

    async def fake_get_markets(self, include_symbol_map=False, *, page=None, limit=None):
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

    async def fake_get_markets(self, include_symbol_map=False, *, page=None, limit=None):
        requested.append(page)
        return _page("1", 0, 1)

    mocker.patch.object(OrderBookClient, "get_markets", fake_get_markets)

    result = runner.invoke(
        cli, ["markets", "list", "--output-format", "raw", "--no-pager", "--page", "0"]
    )
    assert result.exit_code == 0, result.output
    assert requested == [0]
