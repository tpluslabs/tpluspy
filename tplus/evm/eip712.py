from eip712.messages import EIP712Message


class Domain(EIP712Message):
    _name_ = "MyrtleWyckoff"
    _version_ = "1.0.0"


class Order(Domain):
    tokenOut: "address"  # type: ignore
    amountOut: "uint256"  # type: ignore
    tokenIn: "address"  # type: ignore
    amountIn: "uint256"  # type: ignore
    user: "bytes32"  # type: ignore
    nonce: "uint256"  # type: ignore
    validUntil: "uint256"  # type: ignore
