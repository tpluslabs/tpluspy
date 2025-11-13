from collections.abc import Iterator
from getpass import getpass
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # type: ignore
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat  # type: ignore

from tplus.utils.user.ed_keyfile import decrypt_keyfile, encrypt_keyfile
from tplus.utils.user.model import User
from tplus.utils.user.validate import privkey_to_bytes


def _store(path: Path, password: str, private_key: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypt_keyfile(private_key, password, f"{path}")


class UserManager:
    """
    A class for managing local T+ users.
    """

    def __init__(self):
        self._data_folder = Path.home() / ".tplus" / "users"
        self._default_user = None

    @property
    def usernames(self) -> Iterator[str]:
        if not self._data_folder.is_dir():
            return

        for userfile in self._data_folder.iterdir():
            if userfile.is_file():
                yield userfile.stem

    @property
    def users(self) -> Iterator["User"]:
        for username in self.usernames:
            yield self.load(username)

    def generate(self, name: str, password=None) -> "User":
        path = self.get_non_existing_path(name)
        sk = Ed25519PrivateKey.generate()
        password = password or getpass(f"Enter new password for '{name}': ")
        private_key_bytes = sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        _store(path, password, private_key_bytes)
        return User(private_key=sk)

    def load(self, name: str, password=None) -> "User":
        path = self._get_existing_path(name)
        password = password or getpass(f"Enter existing password for '{name}': ")
        private_key = decrypt_keyfile(password, f"{path}")
        return User(private_key=private_key)

    def load_default(self, password=None) -> Optional["User"]:
        if name := self._default_user:
            return self.load(name, password=password)

        # Use the first one, if there are any.
        if username := next(self.usernames, None):
            return self.load(username, password=password)

        return None

    def set_default(self, name: str) -> None:
        self._default_user = name

    def add(self, name: str, private_key: str | bytes, password=None) -> "User":
        path = self.get_non_existing_path(name)
        private_key_bytes = privkey_to_bytes(private_key)
        password = password or getpass(f"Enter new password for '{name}': ")
        _store(path, password, private_key_bytes)
        return User(private_key=private_key_bytes)

    def get_non_existing_path(self, name: str) -> Path:
        path = self._data_folder / name
        if path.is_file():
            raise ValueError("User already exists")

        return path

    def _get_existing_path(self, name: str) -> Path:
        path = self._data_folder / name
        if not path.is_file():
            raise ValueError(f"User '{name}' not found.")

        return path
