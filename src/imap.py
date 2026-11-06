"""Saves copies of sent messages through the iCloud IMAP server.

SMTP only delivers an email: nothing appears in the Sent folder unless the
client puts it there.
"""

import imaplib
import re
import ssl
from collections.abc import Callable
from contextlib import suppress
from email.message import EmailMessage

from credentials import Credentials
from errors import ArchiveError

IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993
_TIMEOUT_SECONDS = 60
_DEFAULT_SENT_MAILBOX = '"Sent Messages"'  # imaplib does not quote mailbox names.

# A LIST response line, for example: (\HasNoChildren \Sent) "/" "Sent Messages"
_LIST_LINE = re.compile(rb'\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<mailbox>.+)', re.IGNORECASE)


class ImapSentArchive:
    """Appends messages to the mailbox the server marks as Sent."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        host: str = IMAP_HOST,
        port: int = IMAP_PORT,
        imap_factory: Callable[..., imaplib.IMAP4] = imaplib.IMAP4_SSL,
    ) -> None:
        self._credentials = credentials
        self._host = host
        self._port = port
        self._imap_factory = imap_factory

    def store(self, message: EmailMessage) -> None:
        """Save the message, or raise ArchiveError."""
        try:
            imap = self._imap_factory(
                self._host,
                self._port,
                # Without an explicit context IMAP4_SSL does not verify the certificate.
                ssl_context=ssl.create_default_context(),
                timeout=_TIMEOUT_SECONDS,
            )
            try:
                self._append(imap, message)
            finally:
                with suppress(imaplib.IMAP4.error, OSError):
                    imap.logout()
        except (imaplib.IMAP4.error, OSError, UnicodeError) as exc:
            raise ArchiveError(f"cannot save a copy to Sent: {exc}") from exc

    def _append(self, imap: imaplib.IMAP4, message: EmailMessage) -> None:
        imap.login(self._credentials.username, self._credentials.password)
        mailbox = self._find_sent_mailbox(imap)
        status, reply = imap.append(mailbox, r"(\Seen)", None, message.as_bytes())
        if status != "OK":
            raise ArchiveError(f"cannot save a copy to {mailbox}: {reply!r}")

    @staticmethod
    def _find_sent_mailbox(imap: imaplib.IMAP4) -> str:
        """Find the mailbox with the RFC 6154 \\Sent flag, which is locale-independent."""
        status, lines = imap.list()
        if status == "OK":
            for line in lines:
                match = _LIST_LINE.fullmatch(line) if isinstance(line, bytes) else None
                if match and b"\\sent" in match["flags"].lower().split():
                    return match["mailbox"].decode("ascii")
        return _DEFAULT_SENT_MAILBOX
