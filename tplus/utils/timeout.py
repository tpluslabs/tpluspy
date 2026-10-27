import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

NANOS_PER_SECOND = 1_000_000_000
DEFAULT_WAIT_NS = NANOS_PER_SECOND


async def wait_for_condition(
    update_fn: Callable[[], Awaitable[None]],
    get_fn: Callable[[], Awaitable[Any]],
    check_fn: Callable[[Any], bool],
    *,
    timeout: int = 10,
    initial_wait_ns: int = DEFAULT_WAIT_NS,
    inc_wait_ns: int = DEFAULT_WAIT_NS,
    error_msg: str = "Condition not met.",
    **kwargs: Any,
) -> None:
    """
    Repeatedly calls `update_fn` then `get_fn` until `check_fn` returns True
    or timeout is reached.

    Args:
        update_fn: async function to run each iteration (e.g. refresh state).
        get_fn: async function that fetches the current state.
        check_fn: function that checks whether the condition is satisfied.
        timeout: maximum number of seconds to wait.
        initial_wait_ns: nanoseconds to wait after the first check.
        inc_wait_ns: nanoseconds to wait after every later check.
        error_msg: message for the raised Exception if condition is not met.
        **kwargs: `interval`, the former seconds between retries. It sets whichever of
            `initial_wait_ns` and `inc_wait_ns` is left at its default.
    """
    interval = kwargs.pop("interval", None)
    if kwargs:
        raise TypeError(f"wait_for_condition() got unexpected keyword arguments: {sorted(kwargs)}")

    if interval is not None:
        interval_ns = int(interval * NANOS_PER_SECOND)
        if initial_wait_ns == DEFAULT_WAIT_NS:
            initial_wait_ns = interval_ns

        if inc_wait_ns == DEFAULT_WAIT_NS:
            inc_wait_ns = interval_ns

    start = time.monotonic()
    wait_ns = initial_wait_ns

    while time.monotonic() - start <= timeout:
        await update_fn()
        result = await get_fn()
        if check_fn(result):
            return

        await asyncio.sleep(wait_ns / NANOS_PER_SECOND)
        wait_ns = inc_wait_ns

    raise TimeoutError(error_msg)
