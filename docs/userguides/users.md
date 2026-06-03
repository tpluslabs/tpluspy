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
