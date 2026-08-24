# Users

T+ identifies traders by an Ed25519 public key. `tpluspy` ships a small local
key manager ({py:class}`tplus.utils.user.UserManager`) that stores keys as
encrypted keyfiles under `~/.tplus/users/`, plus a {py:class}`tplus.utils.user.User`
class for in-memory keys.

:::{note}
T+ user signing is Ed25519 over compact-JSON payloads. It is used for OMS
authentication, order signing, approvals, and settlement requests alike.
:::

## Storage layout

`UserManager` uses `~/.tplus/users/` as its data folder. For a user named
`alice` it produces:

| File                       | Contents                                                 |
| -------------------------- | -------------------------------------------------------- |
| `~/.tplus/users/alice`     | Ed25519 private key, encrypted with the user's password. |
| `~/.tplus/users/alice.pub` | Hex-encoded public key sidecar (used to load lazily).    |

## Generating a new user

```{code-block} python
from tplus.utils.user import UserManager

manager = UserManager()
user = manager.generate("alice")  # prompts for a new password
print(user.public_key)
```

Pass `password=` to skip the prompt (useful for tests/CI):

```{code-block} python
user = manager.generate("alice", password="hunter2")
```

## Importing an existing key

```{code-block} python
manager.add("alice", private_key="0x...32-byte-hex...", password="hunter2")
```

The argument accepts a hex string, raw bytes, or an
{py:class}`cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey`.
Both 32-byte seeds and 64-byte seed+pubkey concatenations are supported.

## Loading a user

```{code-block} python
from tplus.utils.user import load_user

user = load_user("alice")          # by name
default = load_user()              # default user (only one stored, or set explicitly)
```

`load_user` uses {py:meth}`tplus.utils.user.UserManager.load`, which returns a
{py:class}`tplus.utils.user.LocalUser`: the public key is read from the
`*.pub` sidecar immediately, while the private key is decrypted lazily on
the first call to `sign`. This means listing users is cheap and never
prompts for a password.

## Using an EVM account as a T+ user

An EVM account can back a T+ user, in one of two ways. Which one you want depends on
whether the wallet already has a T+ account.

### Reaching the account a wallet already controls

A T+ account created from a wallet registers that wallet's own secp256k1 key as an
additional signer. The account id itself is unrelated to the wallet key, so it has to be
looked up. {py:meth}`tplus.client.base.BaseClient.resolve_evm_user` does that, exactly as
the T+ frontend does on login:

```{code-block} python
from ape import accounts
from tplus.client import OrderBookClient

account = accounts.load("me")

async with OrderBookClient(base_url=...) as client:
    user = await client.resolve_evm_user(account)
    print(user.public_key)  # the T+ account id, not a key derived from the wallet
```

The returned user acts for that account and co-signs every request with the wallet, which
T+ verifies against the registered signer. The wallet is prompted once per signature. To
trade without a prompt per order, register an Ed25519 session signer once and act through
a {py:class}`tplus.utils.user.DelegatedUser`:

```{code-block} python
from tplus.utils.user import DelegatedUser, User

session = User()
await client.add_multisig_signer(session, user=user)   # one wallet prompt, high tier

trader = DelegatedUser(user.public_key, session)
async with OrderBookClient(base_url=..., default_user=trader) as client:
    await client.create_limit_order(...)
```

If the wallet controls no T+ account yet, `resolve_evm_user` returns the derived user
described next: the account tpluspy would create for it. If it controls several, pass
`account_public_key=` to pick one.

### The derived identity

Passing an EVM account directly derives a T+ user from one fixed-message signature. The
same EVM key always yields the same user, which makes it a stable local identity and the
one used when tpluspy creates an account for a wallet. It is **not** the account a wallet
already has on the T+ frontend — use `resolve_evm_user` for that.

Pass the EVM account itself anywhere a `User` is accepted, whether that is
`default_user=`, a per-call `user=`, or a `signer=`. It is resolved for you:

```{code-block} python
from ape import accounts
from tplus.client import OrderBookClient

account = accounts.load("me")

async with OrderBookClient(base_url=..., default_user=account) as client:
    await client.get_user_inventory()                    # signs as the T+ user behind the account
    await client.get_user_inventory(user=other_account)  # per-call override
```

An `eth_account` signer works the same way and needs no `[evm]` extra:

```{code-block} python
from eth_account import Account

client = OrderBookClient(base_url=..., default_user=Account.from_key("0x..."))
```

Use {py:func}`tplus.utils.user.load_user_from_ape_account` to hold the
{py:class}`tplus.utils.user.User` itself, for example to read its public key or to pick a
sub-account. `load_user` loads stored keyfiles by name, so Ape aliases and keyfile names
occupy separate namespaces and cannot collide.

```{code-block} python
from tplus.utils.user import load_user_from_ape_account

user = load_user_from_ape_account("me")        # by Ape alias (needs the `evm` extra)
user = load_user_from_ape_account(account)     # an already-loaded Ape account
user = load_user_from_ape_account(account, sub_account=1)

print(user.public_key, user.evm_address)
```

The EVM signature is only a deterministic seed: the resulting user is Ed25519 like any
other T+ account and signs every request the same way. The derivation is held by the
{py:class}`tplus.utils.user.UserManager`, so a password-protected Ape account is unlocked
at most once per process. For an `eth_account` signer, the equivalent constructor is
{py:meth}`tplus.utils.user.User.from_eth_account`.

### Keeping the T+ user and the chain signer separate

Passing a single Ape account means "use this account for both". The two signers are
independent, so a stored keyfile user can trade while a different EVM account pays gas:

```{code-block} python
from tplus.evm.managers.settle import SettlementManager
from tplus.utils.user import load_user

manager = SettlementManager(default_user=load_user("alice"), ape_account=accounts.load("gas-payer"))
manager = SettlementManager(account)  # one account for both

await manager.init_settlement(..., user=load_user("bob"))  # per-call override
```

Handed a single account, a manager does not assume which T+ account that wallet uses. It
looks the account up on first use, the same way
{py:meth}`tplus.client.base.BaseClient.resolve_evm_user` does, so a deposit credits the
wallet's own account rather than an identity derived from it. Call
{py:meth}`tplus.evm.managers.evm.ChainSigningManager.resolve_default_user` to do it up
front. Settlement approvals are sealed to the account's Ed25519 key, so a wallet-backed
account cannot decrypt them — pass the account's master key as `user=` for those.

### On the CLI

`--tplus-account` / `TPLUS_ACCOUNT` refers to stored keyfiles. The EVM commands
(`tplus settle`, `tplus withdraw`, `tplus deposit`) take the Ape account through Ape's own
`--account` option.

## Listing all users

```{code-block} python
manager = UserManager()
print(list(manager.usernames))
for user in manager.users:
    print(user.public_key)
```

## Setting a default user

```{code-block} python
manager.set_default("alice")
default = manager.load_default()
```

If only a single user is stored, that user is automatically the default.

## Signing payloads

Every `User` exposes a `sign()` method that produces the raw 64-byte Ed25519
signature over a normalized payload (whitespace stripped):

```{code-block} python
sig = user.sign('{"hello":"world"}')  # bytes of length 64
```

Most callers should not need to invoke `sign` directly -- the OMS client and
helper functions in `tplus.utils.signing` build and sign payloads for you.

## Sub-accounts

Each user has a default sub-account (index `0`). Pass `sub_account=` to use a
different one:

```{code-block} python
from tplus.utils.user import User

user = User(private_key=secret_bytes, sub_account=1)
print(user.sub_account)  # 1
```

## API reference

See {py:mod}`tplus.utils.user` for the full reference.
