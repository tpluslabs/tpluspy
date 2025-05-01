from dataclasses import dataclass


@dataclass
class OrderBook:
    def __init__(self,
                 asks: list[list[int]] = None,
                 bids: list[list[int]] = None,
                 sequence_number: int = 0):
        self.asks = asks or []  # List of [price, quantity]
        self.bids = bids or []  # List of [price, quantity]
        self.sequence_number = sequence_number
