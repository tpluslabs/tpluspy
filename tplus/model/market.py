from pydantic import BaseModel

from tplus.model.asset_identifier import IndexAsset


class Market(BaseModel):
    asset_id: IndexAsset
    book_price_decimals: int
    book_quantity_decimals: int


def parse_market(data: dict) -> Market:
    return Market(
            asset_id=IndexAsset(**data["asset_id"]),
            book_price_decimals = data["book_price_decimals"],
            book_quantity_decimals = data["book_quantity_decimals"]
        )
