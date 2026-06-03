"""
Dev-only contract containers used by :mod:`tplus.evm.dev.env`.

The Solidity source for ``SettlerExecutor`` is kept here as reference so the
ABI/bytecode below can be regenerated if the contract changes.

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract AtomicSettler {
    uint256 public returnAmount;

    constructor() {
        returnAmount = 1_000_000;
    }

    function setReturnAmount(uint256 newAmount) external {
        returnAmount = newAmount;
    }

    function onAtomicSettlement(
        address,
        uint256,
        bytes calldata
    )
        external
        returns (uint256)
    {
        return returnAmount;
    }
}
"""

from ape.contracts import ContractContainer
from ethpm_types import ContractType

SettlerExecutor = ContractContainer(
    contract_type=ContractType(
        contractName="SettlerExecutor",
        abi=[
            {"type": "constructor", "stateMutability": "nonpayable", "inputs": []},
            {
                "type": "function",
                "name": "onAtomicSettlement",
                "stateMutability": "nonpayable",
                "inputs": [
                    {
                        "name": "",
                        "type": "address",
                        "components": None,
                        "internalType": "address",
                    },
                    {
                        "name": "",
                        "type": "uint256",
                        "components": None,
                        "internalType": "uint256",
                    },
                    {
                        "name": "",
                        "type": "bytes",
                        "components": None,
                        "internalType": "bytes",
                    },
                ],
                "outputs": [
                    {
                        "name": "",
                        "type": "uint256",
                        "components": None,
                        "internalType": "uint256",
                    }
                ],
            },
            {
                "type": "function",
                "name": "returnAmount",
                "stateMutability": "view",
                "inputs": [],
                "outputs": [
                    {
                        "name": "",
                        "type": "uint256",
                        "components": None,
                        "internalType": "uint256",
                    }
                ],
            },
            {
                "type": "function",
                "name": "setReturnAmount",
                "stateMutability": "nonpayable",
                "inputs": [
                    {
                        "name": "newAmount",
                        "type": "uint256",
                        "components": None,
                        "internalType": "uint256",
                    }
                ],
                "outputs": [],
            },
        ],
        deploymentBytecode="0x6080604052348015600e575f5ffd5b50620f42405f819055506102b8806100255f395ff3fe608060405234801561000f575f5ffd5b506004361061003f575f3560e01c80633f1d584e146100435780635c7d176b14610073578063f35eeaef1461008f575b5f5ffd5b61005d600480360381019061005891906101be565b6100ad565b60405161006a919061023e565b60405180910390f35b61008d60048036038101906100889190610257565b6100ba565b005b6100976100c3565b6040516100a4919061023e565b60405180910390f35b5f5f549050949350505050565b805f8190555050565b5f5481565b5f5ffd5b5f5ffd5b5f73ffffffffffffffffffffffffffffffffffffffff82169050919050565b5f6100f9826100d0565b9050919050565b610109816100ef565b8114610113575f5ffd5b50565b5f8135905061012481610100565b92915050565b5f819050919050565b61013c8161012a565b8114610146575f5ffd5b50565b5f8135905061015781610133565b92915050565b5f5ffd5b5f5ffd5b5f5ffd5b5f5f83601f84011261017e5761017d61015d565b5b8235905067ffffffffffffffff81111561019b5761019a610161565b5b6020830191508360018202830111156101b7576101b6610165565b5b9250929050565b5f5f5f5f606085870312156101d6576101d56100c8565b5b5f6101e387828801610116565b94505060206101f487828801610149565b935050604085013567ffffffffffffffff811115610215576102146100cc565b5b61022187828801610169565b925092505092959194509250565b6102388161012a565b82525050565b5f6020820190506102515f83018461022f565b92915050565b5f6020828403121561026c5761026b6100c8565b5b5f61027984828501610149565b9150509291505056fea2646970667358221220783af59681766ac27b7c4e76dfa4ef1e4c997f25d51dbee979bf9b315266da2464736f6c634300081e0033",
    )
)
