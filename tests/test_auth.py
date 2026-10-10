"""Sign-in at the API boundary: off by default, enforced with ARETE_AUTH=clerk."""

from __future__ import annotations

import pytest

from arete.api import auth
from arete.dataio.db import connect
from arete.services import oauth_state, users

OWNER = "user_owner"
OTHER = "user_other"
PROFILES = {OWNER: ("Owner@Example.com", "Greg"), OTHER: ("other@example.com", None)}
TOKENS = {"owner-token": OWNER, "other-token": OTHER}


@pytest.fixture(autouse=True)
def _clean_users():
    con = connect()
    con.execute("DELETE FROM app.users")
    con.close()
    yield
    con = connect()
    con.execute("DELETE FROM app.users")
    con.close()


@pytest.fixture
def enforced(monkeypatch):
    """Clerk mode with a fake verifier: no network, no real keys."""
    monkeypatch.setenv("ARETE_AUTH", "clerk")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_fake")
    monkeypatch.setenv("ARETE_OWNER_EMAIL", "owner@example.com")
    monkeypatch.delenv("ARETE_API_KEY", raising=False)
    fetched: list[str] = []

    def verify(token: str):
        if token in TOKENS:
            return {"sub": TOKENS[token]}
        raise auth.AuthError(401, "Session invalide ou expirée.")

    def profile(clerk_user_id: str):
        fetched.append(clerk_user_id)
        return PROFILES[clerk_user_id]

    monkeypatch.setattr(auth, "_verify_session_token", verify)
    monkeypatch.setattr(auth, "_fetch_clerk_profile", profile)
    return fetched


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_open_by_default(client, monkeypatch):
    monkeypatch.delenv("ARETE_AUTH", raising=False)
    assert client.get("/settings").status_code == 200
    assert client.get("/auth/config").json() == {
        "enabled": False,
        "publishable_key": None,
    }
    me = client.get("/auth/me").json()
    assert (me["athlete_id"], me["is_owner"], me["email"]) == (1, True, "")


def test_enforced_mode_requires_a_credential(client, enforced):
    refused = client.get("/settings")
    assert refused.status_code == 401
    assert refused.headers["www-authenticate"] == "Bearer"
    assert client.get("/settings", headers=_bearer("garbage")).status_code == 401
    # Public without a credential: the probe, the sign-in bootstrap, the schema.
    assert client.get("/health").status_code == 200
    assert client.get("/auth/config").json() == {
        "enabled": True,
        "publishable_key": "pk_test_fake",
    }
    assert client.get("/openapi.json").status_code == 200
    # The Strava callback arrives from the provider's redirect, with no session:
    # it keeps its own state check and must not be turned away at the door.
    assert client.get("/strava/callback").status_code != 401
    # Slack events carry Slack's signature, checked by their own route.
    assert "www-authenticate" not in client.post("/slack/events").headers


def test_the_owner_gets_the_athlete_and_other_accounts_wait(client, enforced):
    me = client.get("/auth/me", headers=_bearer("owner-token")).json()
    assert me == {
        "email": "owner@example.com",
        "name": "Greg",
        "athlete_id": 1,
        "is_owner": True,
    }
    assert client.get("/settings", headers=_bearer("owner-token")).status_code == 200

    other = client.get("/auth/me", headers=_bearer("other-token")).json()
    assert (other["email"], other["athlete_id"], other["is_owner"]) == (
        "other@example.com",
        None,
        False,
    )
    refused = client.get("/settings", headers=_bearer("other-token"))
    assert refused.status_code == 403
    assert "Aucun athlète" in refused.json()["detail"]
    # Each account's profile was read from Clerk once, then served from the table.
    assert sorted(enforced) == sorted([OWNER, OTHER])


def test_the_api_key_acts_as_the_owner(client, enforced, monkeypatch):
    monkeypatch.setenv("ARETE_API_KEY", "k-" * 16)
    assert client.get("/settings", headers=_bearer("k-" * 16)).status_code == 200
    assert client.get("/auth/me", headers=_bearer("k-" * 16)).json()["is_owner"] is True
    assert client.get("/settings", headers=_bearer("k-" * 15)).status_code == 401


def test_misconfiguration_fails_closed(client, monkeypatch):
    monkeypatch.setenv("ARETE_AUTH", "clerk")
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    assert client.get("/settings").status_code == 503
    assert client.get("/health").status_code == 200


def test_an_identity_provider_outage_is_a_503_not_a_leak(client, enforced, monkeypatch):
    def down(_token):
        raise RuntimeError("clerk unreachable")

    monkeypatch.setattr(auth, "_verify_session_token", down)
    assert client.get("/settings", headers=_bearer("owner-token")).status_code == 503


class TestUsers:
    def test_every_owner_address_gets_the_athlete(self, monkeypatch):
        # One person, two Google accounts: both addresses are the athlete.
        monkeypatch.setenv("ARETE_OWNER_EMAIL", "Owner@Example.com, me@home.example")
        first = users.upsert_user("u1", "owner@example.com", "Greg")
        assert first.athlete_id == 1 and first.is_owner
        again = users.upsert_user("u1", "OWNER@example.com", None)
        assert (again.athlete_id, again.name) == (1, "Greg")
        home = users.upsert_user("u2", "ME@home.example", None)
        assert home.athlete_id == 1
        other = users.upsert_user("u3", "other@example.com", "Someone")
        assert other.athlete_id is None
        assert [u.clerk_user_id for u in users.list_users()] == ["u1", "u2", "u3"]

    def test_the_owner_e_mail_falls_back_to_settings(self, monkeypatch):
        monkeypatch.delenv("ARETE_OWNER_EMAIL", raising=False)
        monkeypatch.setattr(
            users, "get_user_settings", lambda user_id=1: {"email": "Me@Example.com"}
        )
        assert users.upsert_user("u3", "me@example.com").athlete_id == 1
        assert users.upsert_user("u4", "you@example.com").athlete_id is None


class TestOAuthState:
    def test_round_trip_tamper_and_expiry(self):
        state = oauth_state.issue("secret", now=1_000_000)
        assert oauth_state.verify("secret", state, now=1_000_100)
        assert not oauth_state.verify("other", state, now=1_000_100)
        assert not oauth_state.verify("secret", state + "x", now=1_000_100)
        assert not oauth_state.verify("secret", state, now=1_000_000 + 601)
        assert not oauth_state.verify("secret", None)
        assert not oauth_state.verify("secret", "a.b")
