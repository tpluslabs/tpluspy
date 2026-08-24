from collections.abc import Awaitable, Callable
from logging import Logger

from tplus.client.base import WebSocketConnection
from tplus.exceptions import is_unauthenticated_status


def resolve_rejected_status_code(error: BaseException) -> int | None:
    status_code = getattr(error, "status_code", None)
    if status_code is not None:
        return status_code

    rejected_response = getattr(error, "response", None)
    return getattr(rejected_response, "status_code", None)


class TplusWebSocket:
    """
    An async context manager wrapping a WebSocket connection that has not been
    opened yet. Entering it performs the handshake and yields the connection.

    A handshake the server rejects as unauthenticated is retried once against a
    freshly issued token, so a connection outliving its token recovers instead of
    presenting the rejected one forever. Any other failure, including a second
    rejection, is raised to the caller.
    """

    def __init__(
        self,
        connection: WebSocketConnection,
        reconnect_after_rejection: Callable[[], Awaitable[WebSocketConnection]],
        logger: Logger,
        path: str,
    ) -> None:
        self._connection = connection
        self._reconnect_after_rejection = reconnect_after_rejection
        self._logger = logger
        self._path = path

    async def __aenter__(self):
        try:
            return await self._connection.__aenter__()
        except Exception as err:
            rejected_status_code = resolve_rejected_status_code(err)
            if rejected_status_code is None or not is_unauthenticated_status(rejected_status_code):
                raise

            self._logger.debug(
                "Received %s for WS %s, refreshing auth token and retrying once.",
                rejected_status_code,
                self._path,
            )

        self._connection = await self._reconnect_after_rejection()
        return await self._connection.__aenter__()

    async def __aexit__(self, exc_type, exc_value, traceback):
        return await self._connection.__aexit__(exc_type, exc_value, traceback)
