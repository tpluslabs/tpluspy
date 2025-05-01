from dataclasses import dataclass

from tplus.model.asset_identifier import IndexAsset


@dataclass
class Trade:
    asset_id: IndexAsset
    trade_id: int
    order_id: str
    price: float
    quantity: int
    timestamp_ns: int
    is_maker: bool
    is_buyer: bool
    confirmed: bool

    def to_dict(self):
        """Converts the Trade object to a dictionary."""
        return {
            "asset_id": {"Index": self.asset_id.Index}, # Handle IndexAsset specifically
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "price": self.price,
            "quantity": self.quantity,
            "timestamp_ns": self.timestamp_ns,
            "is_maker": self.is_maker,
            "is_buyer": self.is_buyer,
            "confirmed": self.confirmed,
        }

def parse_trades(data: list[dict]) -> list[Trade]:
    return [
        Trade(
            asset_id=IndexAsset(**item["asset_id"]),
            trade_id=item["trade_id"],
            order_id=item["order_id"],
            price=item["price"],
            quantity=item["quantity"],
            timestamp_ns=item["timestamp_ns"],
            is_maker=item["is_maker"],
            is_buyer=item["is_buyer"],
            confirmed=item["confirmed"]
        )
        for item in data
    ]
