"""Single entry point to Garmin Connect, built on ``garminconnect``.

Owns authentication (tokens on disk, optional MFA) and exposes the handful of
Garmin endpoints Arete needs. Everything else in ``arete.garmin`` goes through
this class, so swapping the underlying library again only touches this file.

Tokens live in one directory (``ARETE_GARMIN_TOKENS_DIR``, default
``data/garmin_tokens``) as ``garmin_tokens.json``.
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, cast

from garminconnect import Garmin

logger = logging.getLogger(__name__)

TOKEN_FILE = "garmin_tokens.json"


def default_token_dir() -> Path:
    return Path(os.getenv("ARETE_GARMIN_TOKENS_DIR", "data/garmin_tokens"))


class GarminAuthError(RuntimeError):
    """No usable Garmin session (no tokens, expired, or login refused)."""


class GarminClient:
    """Authenticated access to Garmin Connect for one user."""

    # Login waiting for an MFA code (single-user app: one pending login at a time).
    _pending_mfa: Garmin | None = None

    def __init__(self, token_dir: str | Path | None = None):
        self.token_dir = Path(token_dir) if token_dir else default_token_dir()
        self._api: Garmin | None = None

    # ------------------------------------------------------------------ auth
    @property
    def token_file(self) -> Path:
        return self.token_dir / TOKEN_FILE

    def has_tokens(self) -> bool:
        return self.token_file.exists()

    def connect(self) -> Garmin:
        """Return an authenticated API, restoring the saved session.

        Raises GarminAuthError when no valid session can be restored.
        """
        if self._api is not None:
            return self._api
        if not self.has_tokens():
            raise GarminAuthError(
                f"No Garmin tokens at {self.token_file}. Log in first "
                "(Settings > System, or scripts/garmin_login.py)."
            )
        api = Garmin()
        try:
            api.login(str(self.token_dir))
        except Exception as e:
            raise GarminAuthError(f"Garmin session could not be restored: {e}") from e
        self._api = api
        return api

    def is_authenticated(self) -> bool:
        try:
            self.connect()
            return True
        except GarminAuthError:
            return False

    def login(self, email: str, password: str) -> str:
        """Start a login. Returns "ok" or "needs_mfa" (then call complete_mfa)."""
        api = Garmin(email, password, return_on_mfa=True)
        status, _ = api.login()
        if status == "needs_mfa":
            GarminClient._pending_mfa = api
            return "needs_mfa"
        self._save(api)
        return "ok"

    def complete_mfa(self, code: str) -> None:
        api = GarminClient._pending_mfa
        if api is None:
            raise GarminAuthError("No login waiting for an MFA code.")
        try:
            api.resume_login({}, code)
        finally:
            GarminClient._pending_mfa = None
        self._save(api)

    def _save(self, api: Garmin) -> None:
        self.token_dir.mkdir(parents=True, exist_ok=True)
        api.client.dump(str(self.token_dir))
        self._api = api
        logger.info("Garmin tokens saved to %s", self.token_file)

    def logout(self) -> None:
        if self.token_file.exists():
            self.token_file.unlink()
        self._api = None
        logger.info("Garmin tokens removed from %s", self.token_dir)

    # ------------------------------------------------------------------ data
    def profile(self) -> dict[str, Any]:
        api = self.connect()
        return {
            "display_name": api.display_name,
            "full_name": api.full_name,
            "user_email": api.username,
        }

    def activities(self, start: date, end: date) -> list[dict[str, Any]]:
        """Activity summaries between two dates (inclusive), newest first."""
        return cast(
            list[dict[str, Any]],
            self.connect().get_activities_by_date(start.isoformat(), end.isoformat()),
        )

    def download_fit(self, activity_id: int | str) -> bytes | None:
        """Original FIT bytes for an activity (Garmin ships them zipped)."""
        raw = self.connect().download_activity(
            str(activity_id), dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
        )
        if raw[:2] != b"PK":  # not a zip: assume it is already the FIT payload
            return raw
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".fit"):
                    return zf.read(name)
        logger.warning("No .fit member in download for activity %s", activity_id)
        return None

    def hrv(self, day: date) -> dict[str, Any] | None:
        return cast(dict[str, Any] | None, self.connect().get_hrv_data(day.isoformat()))

    def sleep(self, day: date) -> dict[str, Any] | None:
        return cast(
            dict[str, Any] | None, self.connect().get_sleep_data(day.isoformat())
        )

    def stress(self, day: date) -> dict[str, Any] | None:
        return cast(
            dict[str, Any] | None, self.connect().get_stress_data(day.isoformat())
        )

    def body_battery(self, day: date) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]], self.connect().get_body_battery(day.isoformat()) or []
        )

    def steps(self, day: date) -> list[dict[str, Any]]:
        d = day.isoformat()
        return cast(list[dict[str, Any]], self.connect().get_daily_steps(d, d) or [])

    def resting_hr(self, day: date) -> dict[str, Any] | None:
        return cast(dict[str, Any] | None, self.connect().get_rhr_day(day.isoformat()))
