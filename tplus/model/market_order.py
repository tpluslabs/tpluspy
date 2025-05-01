from dataclasses import dataclass, asdict


@dataclass
class MarketOrderDetails:
    quantity: int
    fill_or_kill: bool

    def to_dict(self):
        return {
            "Market": {
                "quantity": {"BaseAsset" : self.quantity},
                "fill_or_kill": self.fill_or_kill
            }
        }


