from eip712.messages import EIP712Message

from tplus.evm.contracts import TPLUS_DEPLOYMENTS


class Domain(EIP712Message):
    _chainId_ = 11155111
    _name_ = "MyrtleWyckoff"
    _verifyingContract_ = TPLUS_DEPLOYMENTS[11155111]["DepositVault"]


class Order(Domain):
    tokenOut: "address"  # type: ignore
    amountOut: "uint256"  # type: ignore
    tokenIn: "address"  # type: ignore
    amountIn: "uint256"  # type: ignore
    userId: "bytes"  # type: ignore
    nonce: "uint256"  # type: ignore
    validUntil: "uint256"  # type: ignore
