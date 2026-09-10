"""Compare the two-pass and single-pass control-frame encodings.

Run from ``tpluspy/`` with ``python benchmarks/order_wire.py --iterations 5000``.
"""

import argparse
import gc
import json
import time
import tracemalloc
from collections.abc import Callable

from tplus.client.orderbook import encode_control_frame
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.limit_order import create_limit_order_ob_request_payload
from tplus.utils.replace_order import create_replace_order_ob_request_payload
from tplus.utils.user import DelegatedUser, User

ASSET_ID = AssetIdentifier("200")
ACCOUNT = User(bytes(range(32)))
SESSION = User(bytes(range(1, 33)))
USER = DelegatedUser(ACCOUNT.public_key, SESSION)


def legacy_create() -> str:
    request = create_limit_order_ob_request_payload(
        quantity=1_000,
        price=10_500,
        side="Buy",
        signer=USER,
        book_quantity_decimals=3,
        book_price_decimals=2,
        asset_identifier=ASSET_ID,
        order_id="bench-order",
    )
    return json.dumps({"request_id": "bench", "data": {"CreateOrderRequest": request.model_dump()}})


def direct_create() -> str:
    request = create_limit_order_ob_request_payload(
        quantity=1_000,
        price=10_500,
        side="Buy",
        signer=USER,
        book_quantity_decimals=3,
        book_price_decimals=2,
        asset_identifier=ASSET_ID,
        order_id="bench-order",
    )
    return encode_control_frame("bench", {"CreateOrderRequest": request})


def legacy_replace() -> str:
    request = create_replace_order_ob_request_payload(
        original_order_id="bench-order",
        asset_identifier=ASSET_ID,
        signer=USER,
        new_price=10_501,
        new_quantity=1_000,
        book_price_decimals=2,
        book_quantity_decimals=3,
    )
    return json.dumps(
        {
            "request_id": "bench",
            "data": {"ReplaceOrderRequest": request.model_dump(exclude_none=True)},
        }
    )


def direct_replace() -> str:
    request = create_replace_order_ob_request_payload(
        original_order_id="bench-order",
        asset_identifier=ASSET_ID,
        signer=USER,
        new_price=10_501,
        new_quantity=1_000,
        book_price_decimals=2,
        book_quantity_decimals=3,
    )
    return encode_control_frame("bench", {"ReplaceOrderRequest": request}, exclude_none=True)


def elapsed_ns(operation: Callable[[], str], iterations: int) -> float:
    best = float("inf")
    for _ in range(5):
        start = time.perf_counter_ns()
        for _ in range(iterations):
            operation()
        best = min(best, (time.perf_counter_ns() - start) / iterations)
    return best


def peak_bytes(operation: Callable[[], str], iterations: int) -> int:
    gc.collect()
    tracemalloc.start()
    for _ in range(iterations):
        operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def report(
    name: str, legacy: Callable[[], str], direct: Callable[[], str], iterations: int
) -> None:
    legacy()
    direct()
    legacy_ns = elapsed_ns(legacy, iterations)
    direct_ns = elapsed_ns(direct, iterations)
    memory_iterations = min(iterations, 1_000)
    legacy_peak = peak_bytes(legacy, memory_iterations)
    direct_peak = peak_bytes(direct, memory_iterations)
    print(
        f"{name:<8} {legacy_ns / 1_000:>10.1f} us two-pass "
        f"{direct_ns / 1_000:>10.1f} us one-pass "
        f"{legacy_ns / direct_ns:>6.2f}x faster "
        f"peak {legacy_peak / 1024:>7.1f} -> {direct_peak / 1024:>7.1f} KiB"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5_000)
    args = parser.parse_args()
    report("create", legacy_create, direct_create, args.iterations)
    report("replace", legacy_replace, direct_replace, args.iterations)


if __name__ == "__main__":
    main()
