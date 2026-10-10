"""Human feedback on a completed chat root, without server-side conversations.

A signed receipt binds the server-issued run ID to its athlete, account, thread
and deployment. A caller cannot submit an arbitrary LangSmith run ID. Rotating
the tracing key invalidates old receipts. No prompt or credential leaves the API.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import contextmanager
from typing import Literal
from uuid import UUID, uuid5

from langsmith import Client
from langsmith.utils import LangSmithNotFoundError
from urllib3.util import Retry

from arete.config import config
from arete.services.athlete_scope import current_athlete_id

FEEDBACK_CONNECT_TIMEOUT_MS = 1_000
FEEDBACK_READ_TIMEOUT_MS = 4_000
FEEDBACK_CLOSE_SECONDS = 1.0
FeedbackKey = Literal["user_score", "reaction"]


class FeedbackUnavailable(Exception):
    pass


def receipt(trace_id: UUID, thread_id: UUID | None, account_id: str) -> str:
    if not config.langsmith_tracing or not config.langsmith_api_key:
        raise FeedbackUnavailable("Le feedback nécessite la traçabilité LangSmith.")
    payload = json.dumps(
        [
            "arete.chat.feedback.v1",
            config.langsmith_endpoint,
            config.langsmith_project,
            current_athlete_id(),
            account_id,
            str(thread_id) if thread_id else None,
            str(trace_id),
        ],
        separators=(",", ":"),
    ).encode()
    return hmac.new(
        config.langsmith_api_key.encode(), payload, hashlib.sha256
    ).hexdigest()


def authorize(trace_id: UUID, thread_id: UUID | None, account_id: str, token: str):
    if not hmac.compare_digest(receipt(trace_id, thread_id, account_id), token):
        raise PermissionError("Ce retour ne correspond pas à ta réponse du coach.")


@contextmanager
def feedback_client():
    # Separate from the background trace exporter: success means acknowledged.
    # SDK writes and HTTP adapter both have zero retries, even after a timeout.
    client = Client(
        api_key=config.langsmith_api_key,
        api_url=config.langsmith_endpoint,
        workspace_id=config.langsmith_workspace_id,
        timeout_ms=(FEEDBACK_CONNECT_TIMEOUT_MS, FEEDBACK_READ_TIMEOUT_MS),
        retry_config=Retry(total=0),
        auto_batch_tracing=False,
        tracing_sampling_rate=1.0,
    )
    try:
        yield client
    finally:
        client.close(timeout=FEEDBACK_CLOSE_SECONDS)


def feedback_id(trace_id: UUID, key: FeedbackKey) -> UUID:
    # Deterministic across tabs/reloads: never create a second vote on a retry.
    return uuid5(trace_id, f"arete.chat.{key}")


def read_feedback(client: Client, trace_id: UUID, key: FeedbackKey):
    try:
        return client.read_feedback(feedback_id(trace_id, key))
    except LangSmithNotFoundError:
        return None


def read_state(trace_id: UUID) -> dict:
    with feedback_client() as client:
        vote = read_feedback(client, trace_id, "user_score")
        reaction = read_feedback(client, trace_id, "reaction")
    return {
        "user_score": vote.score if vote else None,
        "reaction": reaction.value if reaction else None,
    }


def write_feedback(trace_id: UUID, key: FeedbackKey, value: int | str | None) -> None:
    # At most four SDK requests: existing feedback, project, server info, create.
    # Existing feedback needs only two. No polling for eventual trace ingestion.
    with feedback_client() as client:
        existing = read_feedback(client, trace_id, key)
        identifier = feedback_id(trace_id, key)
        if value is None:
            if existing is not None:
                client.delete_feedback(identifier)
            return
        assert (key == "user_score" and type(value) is int and value in (0, 1)) or (
            key == "reaction" and isinstance(value, str)
        ), "Feedback must be validated at the boundary"
        score = value if isinstance(value, int) else None
        reaction = value if isinstance(value, str) else None
        if existing is not None:
            client.update_feedback(identifier, score=score, value=reaction)
            return
        project = client.read_project(project_name=config.langsmith_project)
        client.create_feedback(
            trace_id=trace_id,
            session_id=project.id,
            feedback_id=identifier,
            key=key,
            score=score,
            value=reaction,
            feedback_source_type="api",
            source_info={"source": "arete_chat", "athlete_id": current_athlete_id()},
            stop_after_attempt=1,
        )
