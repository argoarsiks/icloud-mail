"""The send workflow, independent of concrete protocols."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from errors import ArchiveError


class MailTransport(Protocol):
    """Delivers a message to its recipients."""

    def send(self, message: EmailMessage, recipients: Sequence[str]) -> Mapping[str, str]:
        """Send the message and return the refused recipients with the reasons."""
        ...


class SentArchive(Protocol):
    """Keeps a copy of a delivered message."""

    def store(self, message: EmailMessage) -> None:
        """Save the message, or raise ArchiveError."""
        ...


@dataclass(frozen=True, slots=True)
class DeliveryReport:
    """The outcome of a send in which the server accepted the email."""

    message_id: str
    accepted: tuple[str, ...]
    refused: Mapping[str, str] = field(default_factory=dict)
    archive_error: str | None = None

    @property
    def has_warnings(self) -> bool:
        return bool(self.refused or self.archive_error)


class MailService:
    """Sends a message, then saves its copy."""

    def __init__(self, transport: MailTransport, archive: SentArchive) -> None:
        self._transport = transport
        self._archive = archive

    def send(self, message: EmailMessage, recipients: Sequence[str]) -> DeliveryReport:
        """Deliver the message.

        A failure to save the copy goes into the report instead of being raised:
        by then the email has left, and an error would invite a duplicate resend.
        """
        refused = self._transport.send(message, recipients)
        archive_error = None
        try:
            self._archive.store(message)
        except ArchiveError as exc:
            archive_error = str(exc)
        return DeliveryReport(
            message_id=message["Message-ID"],
            accepted=tuple(address for address in recipients if address not in refused),
            refused=refused,
            archive_error=archive_error,
        )
