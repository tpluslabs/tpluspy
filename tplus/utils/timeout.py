import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


async def wait_for_condition(
    update_fn: Callable[[], Awaitable[None]],
    get_fn: Callable[[], Awaitable[Any]],
    check_fn: Callable[[Any], bool],
    *,
    timeout: int = 10,
    interval: int = 1,
    error_msg: str = "Condition not met.",
) -> None:
    """
    Repeatedly calls `update_fn` then `get_fn` until `check_fn` returns True
    or timeout is reached.

    Args:
        update_fn: async function to run each iteration (e.g. refresh state).
        get_fn: async function that fetches the current state.
        check_fn: function that checks whether the condition is satisfied.
        timeout: maximum number of seconds to wait.
        interval: seconds between retries.
        error_msg: message for the raised Exception if condition is not met.
    """
    start = time.monotonic()

    while time.monotonic() - start <= timeout:
        await update_fn()
        result = await get_fn()
        if check_fn(result):
            return
        await asyncio.sleep(interval)

    raise TimeoutError(error_msg)
