"""A next-message draft is isolated from the answer, tools and failed runs."""

import asyncio
import json
from time import monotonic
from unittest.mock import AsyncMock, patch

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from arete.agent.middlewares.autosuggestion import AutoSuggestionMiddleware
from arete.agent.middlewares.observability import ModelTelemetryMiddleware
from arete.agent.runtime.autosuggestion import suggest_reply
from arete.agent.runtime.context import AgentContext
from arete.agent.runtime.execution import stream_agent
from arete.api.agent_streaming import StreamProjection

ANSWER = "Je peux préparer une séance facile. Ça te convient ?"
DRAFT = "Oui, prépare cette séance."


def graph(suggestion):
    return create_agent(
        GenericFakeChatModel(messages=iter([AIMessage(ANSWER)])),
        middleware=[
            ModelTelemetryMiddleware(),
            AutoSuggestionMiddleware(model=suggestion, context_tokens=8192),
        ],
        context_schema=AgentContext,
    )


def model(text=DRAFT):
    return GenericFakeChatModel(
        messages=iter([AIMessage(text)]), disable_streaming=True
    )


@pytest.mark.parametrize("endpoint", ["/agent/chat", "/agent/chat/stream"])
def test_http_returns_draft_separate_from_answer(client, endpoint):
    with patch("arete.api.agent.get_agent", return_value=graph(model())):
        response = client.post(
            endpoint, json={"messages": [{"role": "user", "content": "Demain ?"}]}
        )
    assert response.status_code == 200
    if endpoint.endswith("/stream"):
        events = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert events[-2] == {"type": "suggestion", "text": DRAFT}
        assert events[-1]["message"]["content"] == ANSWER
        assert all(
            DRAFT not in e.get("text", "")
            for e in events
            if e["type"] in ("token", "message")
        )
    else:
        assert response.json()["suggestion"] == DRAFT
        assert response.json()["message"]["content"] == ANSWER


def test_suggestion_is_one_measured_request_after_the_answer(caplog):
    context = AgentContext(suggest_reply=True)

    async def run():
        projection = StreamProjection()
        events = []
        async for part in stream_agent(
            graph(model()), {"messages": [HumanMessage("Demain ?")]}, context=context
        ):
            events.extend(projection.events(part))
        return events, projection.done()

    events, done = asyncio.run(run())
    assert events[-1] == {"type": "suggestion", "text": DRAFT}
    assert done["message"]["content"] == ANSWER
    assert context.stats.model_calls == 2
    assert context.stats.suggestion_calls == 1


@pytest.mark.parametrize(
    "profile,enabled",
    [("briefing", True), ("feedback", True), ("review", True), ("chat", False)],
)
def test_background_and_disabled_runs_make_no_auxiliary_call(profile, enabled):
    context = AgentContext(profile=profile, suggest_reply=enabled)
    result = asyncio.run(
        graph(model()).ainvoke(
            {"messages": [HumanMessage("Demain ?")]}, context=context
        )
    )
    assert not result.get("suggestion")
    assert context.stats.suggestion_calls == 0


@pytest.mark.parametrize(
    "failure",
    [ConnectionError("down"), TimeoutError("slow"), ValueError("invalid response")],
)
def test_optional_failure_preserves_the_final_answer(failure, caplog):
    suggestion = model()
    with patch.object(
        GenericFakeChatModel, "ainvoke", new=AsyncMock(side_effect=failure)
    ):
        # Exercise the operation directly: patching the class would also affect the coach.
        context = AgentContext(suggest_reply=True)
        result = asyncio.run(
            suggest_reply(
                [HumanMessage("Demain ?"), AIMessage(ANSWER)],
                model=suggestion,
                context_tokens=8192,
                context=context,
                config={},
            )
        )
    assert result is None
    assert context.stats.suggestion_calls == 1
    assert "autosuggestion unavailable" in caplog.text


@pytest.mark.parametrize("text", ["", "x" * 301, "Une option\nUne autre"])
def test_invalid_output_is_rejected_without_truncation(text, caplog):
    context = AgentContext(suggest_reply=True)
    result = asyncio.run(
        suggest_reply(
            [HumanMessage("Demain ?"), AIMessage(ANSWER)],
            model=model(text),
            context_tokens=8192,
            context=context,
            config={},
        )
    )
    assert result is None
    assert "autosuggestion unavailable" in caplog.text


def test_deadline_and_oversized_context_skip_the_request(caplog):
    for deadline, question in [(monotonic(), "Demain ?"), (None, "x" * 100_000)]:
        context = AgentContext(suggest_reply=True)
        context.deadline = deadline
        result = asyncio.run(
            suggest_reply(
                [HumanMessage(question), AIMessage(ANSWER)],
                model=model(),
                context_tokens=8192,
                context=context,
                config={},
            )
        )
        assert result is None
        assert context.stats.model_calls == 0


def test_cancellation_propagates():
    with (
        patch.object(
            GenericFakeChatModel,
            "ainvoke",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(
            suggest_reply(
                [HumanMessage("Demain ?"), AIMessage(ANSWER)],
                model=model(),
                context_tokens=8192,
                context=AgentContext(),
                config={},
            )
        )


def test_timeout_cancels_auxiliary_work_and_still_finishes_the_answer(monkeypatch):
    import arete.agent.runtime.autosuggestion as operation

    class SlowModel(GenericFakeChatModel):
        async def ainvoke(self, *args, **kwargs):
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.append(True)
            raise AssertionError("Timeout must cancel inference")

    cancelled = []
    monkeypatch.setattr(operation, "SUGGESTION_TIMEOUT_SEC", 0.01)
    context = AgentContext(suggest_reply=True)
    result = asyncio.run(
        graph(SlowModel(messages=iter([]))).ainvoke(
            {"messages": [HumanMessage("Demain ?")]},
            context=context,
        )
    )
    assert result["messages"][-1].text == ANSWER
    assert not result.get("suggestion")
    assert cancelled == [True]
    assert context.stats.model_calls == 2


def test_shared_graph_keeps_concurrent_suggestions_in_their_own_streams():
    class EchoModel(GenericFakeChatModel):
        async def ainvoke(self, messages, *args, **kwargs):
            await asyncio.sleep(0)
            return AIMessage(f"Suite de {json.loads(messages[1].text)['athlete']}")

    shared = create_agent(
        GenericFakeChatModel(messages=iter([AIMessage(ANSWER), AIMessage(ANSWER)])),
        middleware=[
            AutoSuggestionMiddleware(
                model=EchoModel(messages=iter([])), context_tokens=8192
            )
        ],
        context_schema=AgentContext,
    )

    async def consume(question):
        context = AgentContext(suggest_reply=True, thread_id=question)
        events = [
            p["data"]
            async for p in stream_agent(
                shared, {"messages": [HumanMessage(question)]}, context=context
            )
            if p["type"] == "custom"
        ]
        assert context.stats.suggestion_calls == 1
        return events

    async def run():
        return await asyncio.gather(consume("course"), consume("musculation"))

    assert asyncio.run(run()) == [
        [{"type": "suggestion", "text": "Suite de course"}],
        [{"type": "suggestion", "text": "Suite de musculation"}],
    ]


def test_exchange_is_data_in_a_user_turn_not_an_assistant_prefill():
    from arete.agent.context.builder import build_suggestion_context

    messages = [
        HumanMessage("Ancienne question"),
        AIMessage("Ancienne réponse"),
        HumanMessage("On continue"),
        AIMessage(ANSWER),
    ]
    prompt = build_suggestion_context(messages, model=model(), context_tokens=8192)
    assert [m.type for m in prompt] == ["system", "human"]
    assert json.loads(prompt[-1].text) == {"athlete": "On continue", "coach": ANSWER}
    assert messages[-1].text == ANSWER


def test_reasoning_only_response_logs_why_there_is_no_suggestion(caplog):
    suggestion = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    response_metadata={"finish_reason": "length"},
                    usage_metadata={
                        "input_tokens": 296,
                        "output_tokens": 512,
                        "total_tokens": 808,
                        "output_token_details": {"reasoning": 512},
                    },
                )
            ]
        ),
        disable_streaming=True,
    )
    result = asyncio.run(
        suggest_reply(
            [HumanMessage("On continue"), AIMessage(ANSWER)],
            model=suggestion,
            context_tokens=8192,
            context=AgentContext(),
            config={},
        )
    )
    assert result is None
    assert "finish_reason=length chars=0" in caplog.text
    assert "'reasoning': 512" in caplog.text
    assert ANSWER not in caplog.text
