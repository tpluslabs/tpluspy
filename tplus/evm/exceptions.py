class ContractNotExists(Exception):
    """
    The contract was not deployed to this network.
    """


class SettlementApprovalTimeout(Exception):
    """
    Raised when waiting for a settlement approval times out.
    """

    def __init__(self, timeout: int, expected_nonce: int):
        self.timeout = timeout
        self.expected_nonce = expected_nonce
        message = (
            f"Settlement approval timeout after {timeout}s. Expected nonce: {expected_nonce}. "
            "Check server logs. Possible issues: "
            "1. Do you have a client running? e.g. arbitrum-client or threshold-client. "
            "2. Are you using a settler that is approved on the vault? "
            "3. Your settler account does not have enough credits in the CE."
        )
        super().__init__(message)
