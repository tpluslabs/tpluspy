import re
from collections.abc import Callable
from typing import Any

import anyio

from tplus.client.base import BaseClient

REQUIRED_SEQ_PATTERNS = (
    re.compile(r"last_accepted_max (\d+)"),
    re.compile(r"anchor (\d+) outside"),
)


def parse_required_seq(rejection: str) -> int | None:
    """The seq a council window rejection says the CE will accept."""
    for pattern in REQUIRED_SEQ_PATTERNS:
        if match := pattern.search(rejection):
            return int(match.group(1))

    return None


class BaseClearingEngineClient(BaseClient):
    async def post_council_request(
        self,
        endpoint: str,
        build_request: Callable[[int, int], dict[str, Any]],
        attempts: int = 8,
    ) -> None:
        """POST a council-signed body, moving its seq window onto the anchor each rejection names.

        Args:
            build_request: Returns the signed body for a ``(min_seq, max_seq)`` window.
        """
        min_seq = max_seq = 0
        for _ in range(attempts):
            response = await self._send("POST", endpoint, json_data=build_request(min_seq, max_seq))
            if response.is_success:
                return

            if "not primary" in response.text.lower():
                await anyio.sleep(1)
                continue

            required_seq = parse_required_seq(response.text)
            if required_seq is None:
                break

            min_seq = max_seq = required_seq + 1 if required_seq == max_seq else required_seq

        self._handle_response(response)
