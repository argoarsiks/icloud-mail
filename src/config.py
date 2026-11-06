"""Account configuration, read from a TOML file.

Example ``~/.config/icloud-mail/config.toml``::

    address = "me@icloud.com"       # Required: the From address, may be an alias.
    display_name = "My Name"        # Optional: the name shown to recipients.
    username = "me@icloud.com"      # Optional: the login, defaults to address.
                                    # Set it to the primary address when sending
                                    # from an alias.
"""

import os
import tomllib
from dataclasses import dataclass
from email.headerregistry import Address
from pathlib import Path
from typing import Self

from errors import ConfigError, DraftError
from message import make_address

_KNOWN_KEYS = frozenset({"address", "display_name", "username"})


def default_config_dir() -> Path:
    """Return the application's configuration directory (XDG base directory spec)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "icloud-mail"


@dataclass(frozen=True, slots=True)
class AccountConfig:
    """The sending identity and the login that authenticates it."""

    sender: Address
    username: str

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate the configuration file."""
        try:
            with path.open("rb") as file:
                data = tomllib.load(file)
        except FileNotFoundError as exc:
            raise ConfigError(f"config file not found: {path}") from exc
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"cannot read config file {path}: {exc}") from exc
        return cls._from_mapping(data, path)

    @classmethod
    def _from_mapping(cls, data: dict[str, object], path: Path) -> Self:
        unknown = data.keys() - _KNOWN_KEYS
        if unknown:
            raise ConfigError(f"unknown keys in {path}: {', '.join(sorted(unknown))}")
        address = cls._string(data, "address", path)
        if not address:
            raise ConfigError(f"'address' is required in {path}")
        try:
            sender = make_address(address, cls._string(data, "display_name", path))
        except DraftError as exc:
            raise ConfigError(f"invalid 'address' in {path}: {exc}") from exc
        return cls(sender=sender, username=cls._string(data, "username", path) or address)

    @staticmethod
    def _string(data: dict[str, object], key: str, path: Path) -> str:
        value = data.get(key, "")
        if not isinstance(value, str):
            raise ConfigError(f"'{key}' must be a string in {path}")
        return value
