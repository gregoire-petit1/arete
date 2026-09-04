"""One-time Garmin Connect login from a terminal. Saves tokens for the API.

Usage:
    uv run python scripts/garmin_login.py

Tokens are persisted to $ARETE_GARMIN_TOKENS_DIR (default data/garmin_tokens).
The Settings > System page offers the same login flow from the UI.
"""

from __future__ import annotations

import getpass
import sys

from arete.garmin.client import GarminClient


def main() -> int:
    client = GarminClient()
    print(f"Tokens will be saved to: {client.token_dir}")
    email = input("Garmin Connect email: ").strip()
    password = getpass.getpass("Password: ")
    try:
        if client.login(email, password) == "needs_mfa":
            code = input("MFA code (check your phone/email): ").strip()
            client.complete_mfa(code)
    except Exception as e:
        print(f"\nLogin failed: {e}")
        return 1
    print(f"\nOK Tokens saved to {client.token_file}")
    print("You can now call POST /garmin/health/sync and POST /garmin/sync/activities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
