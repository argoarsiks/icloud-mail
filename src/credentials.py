"""Looks up the app-specific password in the available secret stores."""

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from errors import CredentialError

_KEYRING_SERVICE = "icloud-mail"
_KEYRING_TIMEOUT_SECONDS = 30


@dataclass(frozen=True, slots=True)
class Credentials:
    """A login pair. The password is excluded from repr to keep it out of logs."""

    username: str
    password: str = field(repr=False)


class CredentialStore(Protocol):
    """A place that may hold the password."""

    def lookup(self, username: str) -> str | None:
        """Return the password, or None if this store does not have it."""
        ...


class SecretToolStore:
    """The system keyring, accessed through libsecret's ``secret-tool``."""

    def lookup(self, username: str) -> str | None:
        command = ["secret-tool", "lookup", "service", _KEYRING_SERVICE, "account", username]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=_KEYRING_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            # Not installed or no keyring daemon: let the next store try.
            return None
        return (result.stdout.strip() or None) if result.returncode == 0 else None


class PasswordFileStore:
    """A plain file, accepted only if nobody but its owner can access it."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def lookup(self, username: str) -> str | None:
        try:
            if self._path.stat().st_mode & 0o077:
                raise CredentialError(
                    f"{self._path} is accessible by other users; run: chmod 600 {self._path}"
                )
            return self._path.read_text(encoding="utf-8").strip() or None
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as exc:
            raise CredentialError(f"cannot read {self._path}: {exc}") from exc


class CredentialResolver:
    """Queries the stores in order and returns the first password found."""

    def __init__(self, stores: Sequence[CredentialStore]) -> None:
        self._stores = stores

    def resolve(self, username: str) -> Credentials:
        for store in self._stores:
            password = store.lookup(username)
            if password:
                return Credentials(username=username, password=password)
        raise CredentialError(
            f"no app-specific password found for {username}; store it with: "
            f"secret-tool store --label='iCloud Mail' "
            f"service {_KEYRING_SERVICE} account {username}"
        )
