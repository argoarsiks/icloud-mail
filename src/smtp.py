"""Delivers messages through the iCloud SMTP server."""

import smtplib
import ssl
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from email.message import EmailMessage

from credentials import Credentials
from errors import AuthenticationError, DeliveryError, DeliveryUncertainError

SMTP_HOST = "smtp.mail.me.com"
SMTP_PORT = 587
_TIMEOUT_SECONDS = 60


class SmtpTransport:
    """Sends one message per connection over STARTTLS."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        host: str = SMTP_HOST,
        port: int = SMTP_PORT,
        smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP,
    ) -> None:
        self._credentials = credentials
        self._host = host
        self._port = port
        self._smtp_factory = smtp_factory

    def send(self, message: EmailMessage, recipients: Sequence[str]) -> Mapping[str, str]:
        """Send the message and return the recipients the server refused."""
        smtp = self._connect()
        try:
            self._authenticate(smtp)
            return self._deliver(smtp, message, recipients)
        finally:
            self._close_quietly(smtp)

    def _connect(self) -> smtplib.SMTP:
        try:
            return self._smtp_factory(self._host, self._port, timeout=_TIMEOUT_SECONDS)
        except OSError as exc:
            raise DeliveryError(f"cannot connect to {self._host}: {exc}") from exc

    def _authenticate(self, smtp: smtplib.SMTP) -> None:
        try:
            # Without an explicit context starttls() does not verify the certificate.
            # It raises if the server lacks STARTTLS, so login never runs in the clear.
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self._credentials.username, self._credentials.password)
        except smtplib.SMTPAuthenticationError as exc:
            raise AuthenticationError(
                f"login rejected for {self._credentials.username}; check that it uses "
                f"an app-specific password (server replied: {exc})"
            ) from exc
        except OSError as exc:  # SMTPException is a subclass of OSError.
            raise DeliveryError(f"cannot start a secure session: {exc}") from exc

    @staticmethod
    def _deliver(
        smtp: smtplib.SMTP, message: EmailMessage, recipients: Sequence[str]
    ) -> Mapping[str, str]:
        try:
            refused = smtp.send_message(message, to_addrs=list(recipients))
        except (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused) as exc:
            raise DeliveryError(f"the server rejected the email: {exc}") from exc
        except OSError as exc:
            raise DeliveryUncertainError(
                f"the connection failed while sending, the email may have gone out: {exc}"
            ) from exc
        return {
            address: f"{code} {reply.decode(errors='replace')}"
            for address, (code, reply) in refused.items()
        }

    @staticmethod
    def _close_quietly(smtp: smtplib.SMTP) -> None:
        # At this point the outcome is known; a failed QUIT must not change it.
        with suppress(OSError):
            smtp.quit()
        with suppress(OSError):
            smtp.close()
