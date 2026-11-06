"""Exception hierarchy and the process exit codes it maps to."""

from enum import IntEnum
from typing import ClassVar


class ExitCode(IntEnum):
    """Exit codes of the CLI.

    They separate "safe to retry" from "do not retry": resending after
    UNCERTAIN or SENT_WITH_WARNINGS can deliver the same email twice.
    """

    OK = 0
    USAGE = 2  # Invalid arguments or draft; nothing was sent.
    SETUP = 3  # Configuration, password or login problem; nothing was sent.
    NOT_SENT = 4  # The server rejected the email or was unreachable.
    UNCERTAIN = 5  # The connection failed mid-send; the email may have gone out.
    SENT_WITH_WARNINGS = 6  # Sent, but a recipient was refused or the Sent copy failed.


class IcloudMailError(Exception):
    """Base class for every expected failure."""

    exit_code: ClassVar[ExitCode] = ExitCode.NOT_SENT


class DraftError(IcloudMailError):
    """The email cannot be built from the given input."""

    exit_code = ExitCode.USAGE


class ConfigError(IcloudMailError):
    """The account configuration is missing or invalid."""

    exit_code = ExitCode.SETUP


class CredentialError(IcloudMailError):
    """The app-specific password is missing or stored unsafely."""

    exit_code = ExitCode.SETUP


class AuthenticationError(IcloudMailError):
    """The server rejected the username or app-specific password."""

    exit_code = ExitCode.SETUP


class DeliveryError(IcloudMailError):
    """The email was definitely not accepted by the server."""

    exit_code = ExitCode.NOT_SENT


class DeliveryUncertainError(IcloudMailError):
    """The connection failed mid-send, so the outcome is unknown."""

    exit_code = ExitCode.UNCERTAIN


class ArchiveError(IcloudMailError):
    """The email was sent, but its copy could not be saved to Sent."""

    exit_code = ExitCode.SENT_WITH_WARNINGS
