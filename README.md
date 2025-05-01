# TPlus Python Client Utilities

Python clients for interacting with tplus.

## Install

To install, use either `pip` or `uv pip`:

```shell
uv pip install -e .
```

## Usage Example

### Contracts

Use the `tplusp.contracts` module to read data from t+ contracts.
For example, launch a Sepolia-connected Ape console:

```shell
ape console --network ethereum:sepolia:alchemy
```

**Note**: You can use any provider you want or a RPC directly, it doesn't have to be Alchemy.

Then, once in the console, you will already have access to contracts that you can call methods on:

```python
In [1]: registry.getAssets()
Out[1]: [getAssets_return(assetAddress=HexBytes('0x000000000000000000000000f08a50178dfcde18524640ea6618a1f965821715'), chainId=11155111, maxDeposits=100)]
In [2]: registry.admin()
Out[2]: '0x467a95fC5359edE5d5dDc4f10A1F4B680694858E'
```

You can also get raw returndata, which can be helpful to ensure we can decode elsewhere, such as in Rust:

```python
In [1]: registry.getRiskParameters(decode=False)
Out[1]: HexBytes('0x000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000')
```
