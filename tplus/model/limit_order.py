from dataclasses import dataclass


@dataclass
class GTC:
    post_only: bool

    def to_dict(self):
        return {"GTC": {"post_only": self.post_only}}


@dataclass
class LimitOrderDetails:
    limit_price: int
    quantity: int
    time_in_force: GTC

    def to_dict(self):
        return {
            "Limit": {
                "limit_price": self.limit_price,
                "quantity": self.quantity,
                "time_in_force": self.time_in_force.to_dict()
            }
        }

