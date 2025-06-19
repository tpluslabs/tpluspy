import json
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from tplus.logger import logger
from tplus.utils.user import User


class BaseClient:
    """
    Base client to use across T+ services.
    """

    DEFAULT_TIMEOUT = 10.0  # Default request timeout

    def __init__(
        self,
        user: User,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        client: Optional[httpx.Client] = None,
    ):
        self.user = user
        # Convert default_asset_id string to AssetIdentifier object upon initialization
        self.base_url = base_url.rstrip("/")
        self._parsed_base_url = urlparse(self.base_url)
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

    @classmethod
    def from_client(cls, client: "BaseClient") -> "BaseClient":
        """
        Easy way to clone clients without initializing multiple AsyncClients.

        Args:
            client ("BaseClient"): The other client.

        Returns:
            A new client.
        """
        return cls(client.user, client.base_url, client=client._client)

    # --- Async HTTP Request Handling ---

    async def _get(
        self, endpoint: str, json_data: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return self._request("GET", endpoint, json_data=json_data)

    async def _post(
        self, endpoint: str, json_data: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return self._request("POST", endpoint, json_data=json_data)

    async def _request(
        self, method: str, endpoint: str, json_data: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Internal method to handle asynchronous REST API requests."""
        relative_url = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        try:
            # Log the request payload if present
            if json_data:
                logger.debug(f"Request to {method} {relative_url} with payload: {json_data}")
            # Use await for the async client request
            response = await self._client.request(
                method=method,
                url=relative_url,
                json=json_data,
            )
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            # Handle cases where the response might be empty (e.g., 204 No Content)
            if response.status_code == 204:
                return {}
            # Response body might be empty even on 200 OK for some APIs
            if not response.content:
                return {}

            # Parse JSON and handle if the result is None (e.g., API returned "null")
            json_response = response.json()
            if json_response is None:
                logger.warning(
                    f"API endpoint {response.request.url!r} returned JSON null. Treating as empty dictionary."
                )
                return {}
            return json_response
        except httpx.TimeoutException as e:
            logger.error(f"Request timed out to {e.request.url!r}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(
                f"An error occurred while requesting {e.request.url!r}: {type(e).__name__} - {e}"
            )
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} while requesting {e.request.url!r}: {e.response.text}"
            )
            raise
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to decode JSON response from {response.request.url!r}. Status: {response.status_code}. Content: {response.text[:100]}..."
            )
            raise ValueError(f"Invalid JSON received from API: {e}") from e
