"""Coaching agent REST surface: POST /agent/chat.

The only writer of ``panel_context`` — same single-writer contract as Cortex's
``agent-run-context.ts``. Stateless v1: the client sends the full message
history each call; persistence lands later if needed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages import BaseMessage as LangchainMessage
from pydantic import BaseModel, Field

from arete.agent.agent import AGENT_RECURSION_LIMIT, get_agent
from arete.agent.context import (
    MAX_PANEL_CONTEXT_CHARS,
    PANEL_CONTEXT_KEY,
    PANEL_PAGES,
    AgentContext,
)
from arete.agent.filesystem import NOTES_LEDGER, SESSIONS_LEDGER, memory_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

#: Hard bound on history size per request (bounds the envelope; a normal turn
#: is 2-20 messages). Over it → 413, never silent truncation.
MAX_MESSAGES = 60
MAX_MESSAGE_CHARS = 16_000


class ChatMessageIn(BaseModel):
    """One client-side message. Role is client-asserted but role-flipped to
    'user' server-side for anything that is not 'assistant'."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    """Body of POST /agent/chat."""

    messages: list[ChatMessageIn] = Field(..., min_length=1, max_length=MAX_MESSAGES)
    page: str | None = Field(
        default=None, description="Frontend page currently open (panel context)"
    )
    panel_context: dict | None = Field(
        default=None,
        description=(
            "Free-form page context stamped at the request tail every turn. "
            "Merged over the derived page name when provided."
        ),
    )


class ChatMessageOut(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    message: ChatMessageOut


def _to_langchain(role: str, content: str) -> LangchainMessage:
    if role == "assistant":
        return AIMessage(content=content)
    return HumanMessage(content=content)


def _panel_context_source(request: ChatRequest) -> dict[str, str]:
    """Serialize the open-page payload. Single writer of PANEL_CONTEXT_KEY."""
    payload: dict = {}
    if request.page is not None:
        if request.page not in PANEL_PAGES:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown page '{request.page}'. Valid: {sorted(PANEL_PAGES)}",
            )
        payload["page"] = request.page
    if request.panel_context is not None:
        payload.update(request.panel_context)
    if not payload:
        return {}
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    if len(raw) > MAX_PANEL_CONTEXT_CHARS:
        # Skip, never truncate (Cortex contract): half a payload parses as a
        # different page.
        raise HTTPException(
            status_code=413,
            detail=f"panel_context over budget ({len(raw)} > {MAX_PANEL_CONTEXT_CHARS} chars)",
        )
    return {PANEL_CONTEXT_KEY: raw}


def _to_agent_context(source: dict[str, str]) -> AgentContext:
    """Coerce the raw source dict into the declared context schema.

    ``create_agent(context_schema=AgentContext)`` does NOT coerce a plain dict
    passed at invoke time (verified: ``request.runtime.context`` arrives as
    ``None``), so the router builds the dataclass itself.
    """
    return AgentContext(source=source)


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    """Run the coaching agent over the client-provided history."""
    graph = get_agent()
    history = [_to_langchain(m.role, m.content) for m in body.messages]
    source = _panel_context_source(body)
    try:
        result = graph.invoke(
            {"messages": history},
            context=_to_agent_context(source),
            config={"recursion_limit": AGENT_RECURSION_LIMIT},
        )
    except ValueError as exc:
        # Model misconfiguration (missing key, unknown provider).
        raise HTTPException(status_code=500, detail=str(exc)) from None
    except Exception as exc:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=502, detail=f"Agent run failed: {exc}") from exc

    messages = result.get("messages", [])
    if not messages:
        raise HTTPException(status_code=502, detail="Agent returned no messages")
    final = messages[-1]
    return ChatResponse(
        message=ChatMessageOut(role="assistant", content=final.text() if hasattr(final, "text") else str(final.content))
    )


class StreamRequest(ChatRequest):
    """Body of POST /agent/chat/stream — same contract, SSE response."""


async def _sse_stream(
    body: StreamRequest,
) -> AsyncIterator[str]:
    """Yield SSE frames for one agent run.

    Events (JSON in ``data:`` frames, one JSON object per frame):
    - ``{"type": "tool_start"|"tool_end", "name": ..., "args": ...}`` — custom
      events from ``ToolEventMiddleware``
    - ``{"type": "token", "text": ...}`` — final-answer deltas (messages mode,
      model node only)
    - ``{"type": "done", "message": {role, content}}`` — full final message,
      so the client replaces its streamed buffer with a consistent value
    - ``{"type": "error", "detail": ...}`` — mid-stream failure
    """
    graph = get_agent()
    history = [_to_langchain(m.role, m.content) for m in body.messages]
    context = _to_agent_context(_panel_context_source(body))

    try:
        async for part in graph.astream(
            {"messages": history},
            context=context,
            config={"recursion_limit": AGENT_RECURSION_LIMIT},
            stream_mode=["messages", "custom"],
            version="v2",
        ):
            kind = part["type"]
            if kind == "custom":
                event = part["data"]
                if isinstance(event, dict) and event.get("type") in (
                    "tool_start",
                    "tool_end",
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif kind == "messages":
                chunk, meta = part["data"]
                # Only model-node tokens: tool-node message passthroughs are
                # already covered by the custom tool events.
                text = getattr(chunk, "text", "") or ""
                if meta.get("langgraph_node") == "model" and text:
                    yield f"data: {json.dumps({'type': 'token', 'text': text}, ensure_ascii=False)}\n\n"
    except ValueError as exc:
        # Model misconfiguration (missing key, unknown provider).
        yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, ensure_ascii=False)}\n\n"
        return
    except Exception as exc:
        logger.exception("Agent stream failed")
        yield f"data: {json.dumps({'type': 'error', 'detail': f'Agent run failed: {exc}'}, ensure_ascii=False)}\n\n"
        return

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/chat/stream")
async def chat_stream(body: StreamRequest) -> StreamingResponse:
    """Stream one agent run as Server-Sent Events (see _sse_stream)."""
    return StreamingResponse(
        _sse_stream(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Memory ledger viewer (Settings page)
# ---------------------------------------------------------------------------


class LedgerFile(BaseModel):
    """One memory-ledger file: name + markdown content."""

    name: str
    content: str


class LedgerResponse(BaseModel):
    files: list[LedgerFile]


_LEDGER_FILES = (NOTES_LEDGER, SESSIONS_LEDGER)


@router.get("/memory", response_model=LedgerResponse)
def get_memory() -> LedgerResponse:
    """Read the agent's memory ledger (bounded files, 64k chars each)."""
    root = memory_root().resolve()
    files: list[LedgerFile] = []
    for name in _LEDGER_FILES:
        path = (root / name).resolve()
        # Defense in depth: the frontend only ever asks for the two known
        # names, but assert the path stays inside the memory root anyway.
        assert path.parent == root, f"ledger path escaped memory root: {name}"
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        if len(content) > MAX_PANEL_CONTEXT_CHARS:
            content = content[:MAX_PANEL_CONTEXT_CHARS] + "\n\n… (tronqué à l'affichage)"
        files.append(LedgerFile(name=name, content=content))
    return LedgerResponse(files=files)
