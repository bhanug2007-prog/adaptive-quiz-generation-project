"""Development-only local CLI for inspecting password reset links generated without SMTP.

Usage (from backend/):
    python -m scripts.dev_reset_outbox
    python -m scripts.dev_reset_outbox --email student@example.com
"""
from __future__ import annotations

import argparse
import json
import sys

from app.core.config import Settings
from app.services.password_reset import read_dev_outbox_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read local development password reset links.")
    parser.add_argument("--email", help="Filter links to a specific account email address.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    s = Settings()
    if s.environment == "production":
        print("Error: dev_reset_outbox cannot be used when ENVIRONMENT=production.", file=sys.stderr)
        return 1

    entries = read_dev_outbox_cli(s, email=args.email)
    if args.as_json:
        print(json.dumps(entries, indent=2))
        return 0

    if not entries:
        print("No active password reset links in the local development outbox.")
        return 0

    print("Development-only password reset outbox (links expire automatically):")
    for entry in entries:
        print(f"- {entry['email']} ({entry.get('role', 'user')}): {entry['reset_link']} [expires {entry['expires_at']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
