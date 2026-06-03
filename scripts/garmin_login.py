"""One-time Garmin Connect login. Saves tokens for daily sync.

Usage:
    uv run python scripts/garmin_login.py

Tokens are persisted to /app/data/garmin_tokens/ (or $ARETE_GARMIN_TOKENS_DIR).
Subsequent syncs use `garth.resume()` to authenticate silently.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

import garth


TOKENS_DIR = Path(os.environ.get("ARETE_GARMIN_TOKENS_DIR", "/app/data/garmin_tokens"))


def main() -> int:
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Tokens will be saved to: {TOKENS_DIR}")
    print()
    email = input("Garmin Connect email: ").strip()
    password = getpass.getpass("Password: ")

    client = garth.Client()
    try:
        result = client.login(email, password, return_on_mfa=True)
        if isinstance(result, tuple) and result[0] == "needs_mfa":
            print("\nMFA required. Check your phone/email for the code.")
            mfa_code = input("MFA code: ").strip()
            client.login(email, password, prompt_mfa=lambda: mfa_code)
    except garth.exc.GarthHTTPError as e:
        print(f"\nLogin failed: HTTP {e.response.status_code}")
        if e.response.status_code == 401:
            print(
                "Check email/password. If you use social login, set a Garmin password first."
            )
        return 1
    except Exception as e:
        print(f"\nLogin failed: {e}")
        return 1

    garth.save(str(TOKENS_DIR))
    print(f"\nOK Tokens saved to {TOKENS_DIR}")
    print("You can now run sync_daily_metrics.py to fetch health data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
