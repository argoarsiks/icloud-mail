"""Command-line interface: the composition root of the application."""

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from email.headerregistry import Address
from email.message import EmailMessage
from pathlib import Path

from config import AccountConfig, default_config_dir
from credentials import CredentialResolver, PasswordFileStore, SecretToolStore
from errors import DraftError, ExitCode, IcloudMailError
from imap import ImapSentArchive
from message import EmailDraft, MessageBuilder, parse_addresses
from service import DeliveryReport, MailService
from smtp import SmtpTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send an email from an iCloud Mail account.",
        epilog=(
            "exit codes: 0 sent; 2 invalid input; 3 setup or login problem; 4 not sent; "
            "5 outcome unknown, do not resend blindly; "
            "6 sent with warnings, do not resend"
        ),
    )
    parser.add_argument("--to", action="append", required=True, help="recipients, repeatable")
    parser.add_argument("--cc", action="append", default=[], help="repeatable")
    parser.add_argument("--bcc", action="append", default=[], help="repeatable")
    parser.add_argument("--subject", required=True)

    text = parser.add_mutually_exclusive_group()
    text.add_argument("--text", help="plain text body")
    text.add_argument("--text-file", metavar="PATH", help="plain text body file, '-' for stdin")

    html = parser.add_mutually_exclusive_group()
    html.add_argument("--html", help="HTML body")
    html.add_argument("--html-file", metavar="PATH", help="HTML body file, '-' for stdin")

    parser.add_argument(
        "--attach", action="append", default=[], type=Path, metavar="PATH", help="repeatable"
    )
    parser.add_argument(
        "--config", type=Path, default=default_config_dir() / "config.toml", metavar="PATH"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="build and print the email without sending it"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except IcloudMailError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


def _run(args: argparse.Namespace) -> int:
    config = AccountConfig.load(args.config)
    draft = _draft_from_args(args, config.sender)
    message = MessageBuilder().build(draft)

    if args.dry_run:
        _print_json(_preview(draft, message))
        return ExitCode.OK

    report = _make_service(config).send(message, draft.recipients)
    _print_json(_report_to_dict(report))
    return ExitCode.SENT_WITH_WARNINGS if report.has_warnings else ExitCode.OK


def _make_service(config: AccountConfig) -> MailService:
    stores = (SecretToolStore(), PasswordFileStore(default_config_dir() / "password"))
    credentials = CredentialResolver(stores).resolve(config.username)
    return MailService(SmtpTransport(credentials), ImapSentArchive(credentials))


def _draft_from_args(args: argparse.Namespace, sender: Address) -> EmailDraft:
    return EmailDraft(
        sender=sender,
        to=_parse_all(args.to),
        cc=_parse_all(args.cc),
        bcc=_parse_all(args.bcc),
        subject=args.subject,
        text=_read_body(args.text, args.text_file),
        html=_read_body(args.html, args.html_file),
        attachments=tuple(args.attach),
    )


def _parse_all(values: Iterable[str]) -> tuple[Address, ...]:
    return tuple(address for value in values for address in parse_addresses(value))


def _read_body(inline: str | None, path: str | None) -> str | None:
    if path is None:
        return inline
    try:
        if path == "-":
            return sys.stdin.read()
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DraftError(f"cannot read body from {path}: {exc}") from exc


def _preview(draft: EmailDraft, message: EmailMessage) -> dict[str, object]:
    return {
        "status": "dry_run",
        "from": str(draft.sender),
        "to": [str(address) for address in draft.to],
        "cc": [str(address) for address in draft.cc],
        "bcc": [str(address) for address in draft.bcc],
        "subject": draft.subject,
        "text": draft.text,
        "html": draft.html,
        "attachments": [
            {"name": path.name, "size_bytes": path.stat().st_size} for path in draft.attachments
        ],
        "message_size_bytes": len(message.as_bytes()),
    }


def _report_to_dict(report: DeliveryReport) -> dict[str, object]:
    return {
        "status": "sent_with_warnings" if report.has_warnings else "sent",
        "message_id": report.message_id,
        "accepted": list(report.accepted),
        "refused": dict(report.refused),
        "saved_to_sent": report.archive_error is None,
        "archive_error": report.archive_error,
    }


def _print_json(data: dict[str, object]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
