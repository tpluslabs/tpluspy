from collections.abc import Iterator
from getpass import getpass
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # type: ignore
from cryptography.hazmat.primitives.serialization import (  # type: ignore
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from tplus.utils.user.ed_keyfile import decrypt_keyfile, encrypt_keyfile
from tplus.utils.user.model import LocalUser, User
from tplus.utils.user.validate import privkey_to_bytes

PUBKEY_SUFFIX = ".pub"


def _store(path: Path, password: str, private_key: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypt_keyfile(private_key, password, f"{path}")


class UserManager:
    """Manage local T+ users stored as encrypted Ed25519 keyfiles.

    Keyfiles live under ``~/.tplus/users/``. Each user has an encrypted
    private-key file and a plaintext ``<name>.pub`` sidecar containing the
    hex public key, so listing and identifying users does not require
    decrypting them.
    """

    def __init__(self):
        self._data_folder = Path.home() / ".tplus" / "users"
        self._default_user = None

    @property
    def usernames(self) -> Iterator[str]:
        """Iterate over the names of every user stored locally.

        Yields:
            The base name of each keyfile under ``~/.tplus/users/``.
        """
        if not self._data_folder.is_dir():
            return

        for userfile in self._data_folder.iterdir():
            if userfile.is_file() and userfile.suffix != PUBKEY_SUFFIX:
                yield userfile.stem

    @property
    def users(self) -> Iterator["User"]:
        """Iterate over every locally stored user as a :class:`LocalUser`.

        Each user is loaded lazily; the private key is not decrypted until
        the first call to ``sign``.

        Yields:
            One :class:`LocalUser` per locally stored keyfile.
        """
        for username in self.usernames:
            yield self.load(username)

    def generate(self, name: str, password=None) -> "User":
        """Generate a fresh Ed25519 user and persist it locally.

        Args:
            name: Name of the user. Must not collide with an existing keyfile.
            password: Password used to encrypt the private key on disk. If
                ``None``, the caller is prompted via :func:`getpass.getpass`.

        Returns:
            The newly generated :class:`User`.

        Raises:
            ValueError: If a user with the given name already exists.
        """
        path = self.get_non_existing_path(name)
        sk = Ed25519PrivateKey.generate()
        password = password or getpass(f"Enter new password for '{name}': ")
        private_key_bytes = sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        _store(path, password, private_key_bytes)
        user = User(private_key=sk)
        self._write_pubkey(name, user)
        return user

    def load(self, name: str, password=None) -> "User":
        """Load a previously stored user.

        If a public-key sidecar is present, a :class:`LocalUser` is returned
        and the private key remains encrypted on disk until the first sign
        call. Otherwise, the keyfile is unlocked immediately and a sidecar
        is written for next time.

        Args:
            name: Name of the user to load.
            password: Password used to decrypt the keyfile. If ``None`` and
                an unlock is required, the caller is prompted.

        Returns:
            The loaded user.

        Raises:
            ValueError: If no user is stored under ``name``.
        """
        path = self._get_existing_path(name)
        pubkey_path = self._pubkey_path(name)

        def _unlock() -> bytes:
            pw = password if password is not None else getpass(f"Enter password for '{name}': ")
            return decrypt_keyfile(pw, f"{path}")

        if pubkey_path.is_file():
            return LocalUser(public_key=pubkey_path.read_text().strip(), unlock=_unlock)

        # Legacy keyfile with no pubkey sidecar — unlock once to derive it, then migrate.
        user = User(private_key=_unlock())
        self._write_pubkey(name, user)
        return user

    def load_default(self, password=None) -> Optional["User"]:
        """Load the default user, if one is configured or inferable.

        If :meth:`set_default` has been called, that user is returned. If
        only a single user is stored, it is automatically treated as the
        default. Otherwise ``None`` is returned.

        Args:
            password: Password used to decrypt the keyfile if the default is
                a legacy keyfile without a public-key sidecar.

        Returns:
            The default user, or ``None`` if no users are stored.
        """
        if name := self._default_user:
            return self.load(name, password=password)

        # Use the first one, if there are any.
        if username := next(self.usernames, None):
            return self.load(username, password=password)

        return None

    def set_default(self, name: str) -> None:
        """Mark ``name`` as the default user for :meth:`load_default`.

        Args:
            name: Name of the user to mark as default. Not validated until
                :meth:`load_default` is invoked.
        """
        self._default_user = name

    def add(self, name: str, private_key: str | bytes, password=None) -> "User":
        """Import an existing Ed25519 private key as a local user.

        Args:
            name: Name to store the user under. Must not collide with an
                existing keyfile.
            private_key: The Ed25519 private key. Accepts a hex string,
                raw bytes, or an existing :class:`Ed25519PrivateKey`. Both
                32-byte seeds and 64-byte ``seed || pubkey`` concatenations
                are accepted.
            password: Password used to encrypt the private key on disk. If
                ``None``, the caller is prompted.

        Returns:
            The imported :class:`User`.

        Raises:
            ValueError: If a user with the given name already exists.
        """
        path = self.get_non_existing_path(name)
        private_key_bytes = privkey_to_bytes(private_key)
        password = password or getpass(f"Enter new password for '{name}': ")
        _store(path, password, private_key_bytes)
        user = User(private_key=private_key_bytes)
        self._write_pubkey(name, user)
        return user

    def get_non_existing_path(self, name: str) -> Path:
        """Return the keyfile path for ``name``, asserting no user exists yet.

        Args:
            name: Name to check.

        Returns:
            The path the keyfile would occupy.

        Raises:
            ValueError: If a user with the given name already exists.
        """
        path = self._data_folder / name
        if path.is_file():
            raise ValueError("User already exists")

        return path

    def _get_existing_path(self, name: str) -> Path:
        path = self._data_folder / name
        if not path.is_file():
            raise ValueError(f"User '{name}' not found.")

        return path

    def _pubkey_path(self, name: str) -> Path:
        return self._data_folder / f"{name}{PUBKEY_SUFFIX}"

    def _write_pubkey(self, name: str, user: "User") -> None:
        path = self._pubkey_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{user.public_key}\n")
