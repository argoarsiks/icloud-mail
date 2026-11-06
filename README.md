# icloud-mail

A [Claude Code](https://claude.com/claude-code) skill that sends email from your iCloud Mail account. Claude writes a draft, shows it to you, and sends it after you approve.

It needs no third-party packages, only the Python standard library.

- Plain text and HTML bodies, Cc, Bcc and attachments
- A copy of each email in your Sent folder
- Sending from an iCloud alias
- App password kept in the system keyring
- Exit codes that tell a safe retry from one that could send a duplicate

It only sends. It cannot read or search your mailbox.

Not affiliated with or endorsed by Apple.

## Requirements

- Python 3.11 or newer
- An iCloud Mail address, and an Apple Account with two-factor authentication
- `secret-tool` (libsecret) for keyring storage, or a password file as described below

Developed and tested on Linux only.

## Installation

Clone the repository into your Claude Code skills directory:

```bash
git clone https://github.com/argoarsiks/icloud-mail ~/.claude/skills/icloud-mail
```

### 1. Create an app-specific password

Go to [account.apple.com](https://account.apple.com), open **Sign-In and Security**, then **App-Specific Passwords**, and create one. Your regular Apple Account password will not work.

### 2. Create the config

Create `~/.config/icloud-mail/config.toml`:

```toml
address = "me@icloud.com"
```

To send from an alias, or to show a name to recipients:

```toml
address = "alias@icloud.com"     # From address
display_name = "My Name"         # Optional
username = "primary@icloud.com"  # Login, required when address is an alias
```

The login must be your **primary iCloud Mail address**. An alias or an Apple Account email from another provider will be rejected. You can find the primary address at [icloud.com/mail](https://www.icloud.com/mail) under Settings, Accounts.

### 3. Store the password

Run this in a regular terminal, using your login as the account:

```bash
secret-tool store --label='iCloud Mail' service icloud-mail account primary@icloud.com
```

Without a keyring, put the password in `~/.config/icloud-mail/password` and run `chmod 600` on that file. The script refuses a file that other users can access.

## Usage

In Claude Code, use the command or just ask:

```text
/icloud-mail ann@example.com remind her about the meeting tomorrow at 3 pm
```

```text
Email the report in ./report.pdf to my team, Bcc me
```

The approval step comes from the skill's instructions to Claude. The script itself sends whenever it is run without `--dry-run`, so use your usual caution with Claude Code's permission settings.

You can also run the script directly:

```bash
python3 src/cli.py --to ann@example.com --subject "Hello" --text "Hi Ann" --dry-run
```

See `python3 src/cli.py --help` for all options.

### Exit codes

| Code | Meaning | Safe to resend? |
|---|---|---|
| 0 | Sent, and a copy was saved to Sent | No need |
| 2 | Invalid input, nothing was sent | Yes, after fixing it |
| 3 | Config, password or login problem, nothing was sent | Yes, after fixing it |
| 4 | Rejected by the server, or server unreachable | Yes |
| 5 | Connection failed mid-send, the email may have gone out | **Check Sent first** |
| 6 | Sent, but a recipient was refused or the copy was not saved | **No** |

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `535 authentication failed` | Not an app-specific password, or the login is an alias rather than the primary address |
| `550 Mailbox does not exist` at login | The login is an Apple Account email rather than an iCloud Mail address |
| Connection timeouts | A VPN or proxy drops mail traffic. Route ports 587 and 993 directly. Rules by domain may not match in tunnel mode |
| No password found right after `secret-tool store` | It was run through Claude Code's `!` prefix and saved an empty value. Use a regular terminal |

## Security

- Passwords are read from the keyring or a private file, and are never written to the project or to the script's output.
- TLS certificates are verified for both SMTP and IMAP.
- Anything running as your user can read the password while the keyring is unlocked, Claude Code included. An app-specific password can be revoked at any time without changing your main password, so revoke it if it leaks.

## Development

```bash
uv sync
uv run ruff check
uv run ruff format --check
uv run mypy
```

## License

[MIT](LICENSE)
