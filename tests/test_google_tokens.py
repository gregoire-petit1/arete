"""The Google token Clerk hands out for a signed-in account, offline."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from arete.services import google_tokens


@pytest.fixture
def clerk(monkeypatch):
    """A stand-in for the Clerk SDK client; ``answer`` is what Clerk returns."""
    import clerk_backend_api

    state = SimpleNamespace(answer=[], calls=[])

    class FakeClerk:
        def __init__(self, **options):
            state.calls.append(options)
            self.users = SimpleNamespace(get_o_auth_access_token=self.tokens)

        def tokens(self, *, user_id, provider):
            state.calls.append((user_id, provider))
            return state.answer

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(clerk_backend_api, "Clerk", FakeClerk)
    return state


def test_expiry_is_read_in_milliseconds(clerk):
    # Clerk answers Unix milliseconds: read as seconds, this was the year 58743.
    clerk.answer = [
        SimpleNamespace(
            token="google-access-token",
            scopes=["openid", "email"],
            expires_at=1_791_584_682_000,
        )
    ]
    token = google_tokens.google_access_token("user_a")
    assert token.token == "google-access-token"
    assert token.expires_at == datetime.fromtimestamp(1_791_584_682)
    assert token.has_scopes(("email",)) and not token.has_scopes(("calendar",))
    assert ("user_a", "oauth_google") in clerk.calls
    assert clerk.calls[0]["timeout_ms"] == google_tokens.CLERK_TIMEOUT_MS


def test_no_google_account_is_unavailable(clerk):
    clerk.answer = []
    with pytest.raises(google_tokens.GoogleTokenUnavailable):
        google_tokens.google_access_token("user_a")
