"""The email draft and its conversion to a MIME message."""

import mimetypes
import re
from dataclasses import dataclass
from email.errors import HeaderParseError
from email.headerregistry import Address
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, getaddresses, make_msgid
from pathlib import Path

from errors import DraftError

# Only ASCII addresses are accepted: smtplib would otherwise need the SMTPUTF8
# extension, and a look-alike Unicode address is more likely a typo or a trap.
_ADDR_SPEC = re.compile(r"[!-?A-~]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")

# smtplib does not declare BODY=8BITMIME for ASCII addresses, so the body has to
# be 7-bit clean. With this policy non-ASCII text becomes quoted-printable or base64.
_POLICY = SMTP.clone(cte_type="7bit")


def make_address(addr_spec: str, display_name: str = "") -> Address:
    """Create a validated address."""
    if not _ADDR_SPEC.fullmatch(addr_spec):
        raise DraftError(f"invalid email address: {addr_spec!r}")
    try:
        return Address(display_name=display_name, addr_spec=addr_spec)
    except (ValueError, IndexError, HeaderParseError) as exc:
        raise DraftError(f"invalid email address: {addr_spec!r}") from exc


def parse_addresses(raw: str) -> tuple[Address, ...]:
    """Parse a comma-separated list such as ``Ann <a@x.org>, b@y.org``."""
    if "\r" in raw or "\n" in raw:
        raise DraftError(f"line breaks are not allowed in addresses: {raw!r}")
    # In strict mode a malformed list yields ("", ""), rejected by make_address,
    # instead of silently dropping part of the recipients.
    return tuple(make_address(spec, name) for name, spec in getaddresses([raw]))


@dataclass(frozen=True, slots=True)
class EmailDraft:
    """A validated email that is ready to be built."""

    sender: Address
    to: tuple[Address, ...]
    subject: str
    cc: tuple[Address, ...] = ()
    bcc: tuple[Address, ...] = ()
    text: str | None = None
    html: str | None = None
    attachments: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not self.to:
            raise DraftError("at least one --to recipient is required")
        if not self.subject.strip():
            raise DraftError("the subject must not be blank")
        if self.subject.splitlines() != [self.subject]:
            raise DraftError("line breaks are not allowed in the subject")
        if not (self.text or self.html):
            raise DraftError("the email needs a text or HTML body")
        for path in self.attachments:
            if not path.is_file():
                raise DraftError(f"attachment not found: {path}")

    @property
    def recipients(self) -> tuple[str, ...]:
        """Unique envelope recipients, including Bcc."""
        everyone = (*self.to, *self.cc, *self.bcc)
        return tuple(dict.fromkeys(address.addr_spec for address in everyone))


class MessageBuilder:
    """Converts an EmailDraft into a MIME message."""

    def build(self, draft: EmailDraft) -> EmailMessage:
        """Build the message.

        The Bcc header stays in the result so the Sent copy records it;
        smtplib.SMTP.send_message removes it from what goes over the wire.
        """
        message = EmailMessage(policy=_POLICY)
        self._set_headers(message, draft)
        self._set_body(message, draft)
        for path in draft.attachments:
            self._attach(message, path)
        return message

    @staticmethod
    def _set_headers(message: EmailMessage, draft: EmailDraft) -> None:
        message["From"] = draft.sender
        message["To"] = draft.to
        if draft.cc:
            message["Cc"] = draft.cc
        if draft.bcc:
            message["Bcc"] = draft.bcc
        message["Subject"] = draft.subject
        message["Date"] = formatdate(localtime=True)
        # An explicit domain keeps the local hostname out of the Message-ID.
        message["Message-ID"] = make_msgid(domain=draft.sender.domain)

    @staticmethod
    def _set_body(message: EmailMessage, draft: EmailDraft) -> None:
        if draft.text and draft.html:
            message.set_content(draft.text)
            message.add_alternative(draft.html, subtype="html")
        elif draft.html:
            message.set_content(draft.html, subtype="html")
        else:
            message.set_content(draft.text)

    @staticmethod
    def _attach(message: EmailMessage, path: Path) -> None:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise DraftError(f"cannot read attachment {path}: {exc}") from exc
        maintype, subtype = MessageBuilder._guess_type(path)
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=path.name)

    @staticmethod
    def _guess_type(path: Path) -> tuple[str, str]:
        content_type, encoding = mimetypes.guess_type(path.name)
        # message/* parts must not be base64-encoded (RFC 2046, section 5.2),
        # and a compressed file is not of the type its inner extension suggests.
        if content_type is None or encoding or content_type.startswith("message/"):
            return "application", "octet-stream"
        maintype, subtype = content_type.split("/", 1)
        return maintype, subtype
