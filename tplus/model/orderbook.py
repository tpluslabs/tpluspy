from typing import List


class OrderBook:
    def __init__(self,
                 asks: List[List[int]] = None,
                 bids: List[List[int]] = None,
                 sequence_number: int = 0):
        self.asks = asks or []  # List of [price, quantity]
        self.bids = bids or []  # List of [price, quantity]
        self.sequence_number = sequence_number
