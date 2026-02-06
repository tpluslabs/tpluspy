import json
from collections.abc import AsyncIterator

from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.asset_identifier import ChainAddress
from tplus.model.settlement import BatchSettlementRequest, TxSettlementRequest
from tplus.model.types import ChainID


class SettlementClient(BaseClearingEngineClient):
    """
    Clearing engine APIs related to settlements.
    """

    async def init_settlement(self, request: dict | TxSettlementRequest):
        """
        Initialize a transaction (atomic) based settlement. This begins the process
        of settling. Use ``get_signatures()`` to retrieve successful signatures.

        Args:
            request (dict | TxSettlementRequest): transaction request.
        """
        if isinstance(request, dict):
            # Validate.
            request = TxSettlementRequest.model_validate(request)

        data = request.model_dump(mode="json")
        await self._post("settlement/init", json_data=data)

    async def get_signatures(self, user: str) -> list[dict]:
        """
        Get CE approved signatures for the given user for settlement. This happens
        after settlement initialization.

        Args:
            user (str): The settler.

        Returns:
            A list of approval dictionaries containing signatures, nonces, and expirys.
        """
        prefix = "settlement/signatures"
        result = await self._get(f"{prefix}/{user}")
        if isinstance(result, list):
            return result

        elif isinstance(result, dict) and "error" in result:
            raise RuntimeError(result["error"])

        # Unknown. Return + log whatever it is and let it fail elsewhere.
        self.logger.error(f"Unknown result format for {prefix} response: {result}.")
        return result  # type: ignore

    async def stream_approvals(self, user_hex: str) -> AsyncIterator[dict]:
        """
        Stream settlement approvals for a given user via WebSocket.

        This connects to the `/settlement/approvals/{user_hex}` WebSocket endpoint
        and yields settlement approval messages as they are received. Messages
        are encrypted and need to be decrypted using the user's Ed25519 private key.

        Args:
            user_hex: The settler's public key in hex format (no 0x prefix).

        Yields:
            dict: Settlement approval messages with the following structure:
                - reference: str - hex-encoded settlement hash
                - signature: dict - the approval signature
                - encrypted_data: str - hex-encoded encrypted approval JSON
        """
        path = f"settlement/approvals/{user_hex}"
        websocket_cm = await self._open_ws(path)

        async with websocket_cm as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    self.logger.warning(
                        f"Received non-JSON message on {path} stream: {message[:100]}…"
                    )

                if isinstance(data, dict) and data.get("type") in self.CONTROL_MESSAGE_TYPES:
                    continue

                yield data

    async def init_batch_settlement(self, request: dict | BatchSettlementRequest):
        """
        Initialize a bundle-based settlement.

        Args:
            request (dict | BatchSettlementRequest): The transaction request.
        """
        if isinstance(request, dict):
            # Validate.
            request = BatchSettlementRequest.model_validate(request)

        json_data = request.model_dump(mode="json")
        await self._post("settlement/batch", json_data=json_data)

    async def update_nonce(self, user: str, chain_id: ChainID):
        """
        Request that the CE check the deposit vault for new settlements for
        the given user.

        Args:
            user (str): The user pubkey key ID.
            chain_id (int): The chain ID to check.
        """
        request = {"user": user, "chain_id": chain_id}
        await self._post("settlement/update-nonce", json_data=request)

    async def update_approved_settlers(self, chain_id: ChainID, vault_address: str):
        """
        Request that the CE check the deposit vault for new approved settlers.

        Args:
            chain_id (int): The chain ID to check.
            vault_address (str): The vault address to check.
        """
        request = ChainAddress(f"{vault_address}@{chain_id}")
        json_data = request.model_dump(mode="json")
        await self._post("settlers/update", json_data=json_data)

    async def get_approved_settlers(self, chain_id: ChainID) -> list[str]:
        """
        Request that the CE check the deposit vault for new approved settlers.

        Args:
            chain_id (int): The chain ID to check.
        """
        return await self._get(f"settlers/{chain_id}")  # type: ignore
