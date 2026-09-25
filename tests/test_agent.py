"""End to end with a LlamaIndex FunctionAgent and a mock function-calling LLM that calls search_news."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from llama_index.core.agent.workflow import FunctionAgent, ToolCallResult
from llama_index.core.base.llms.types import ChatMessage, MessageRole, ToolCallBlock
from llama_index.core.llms.mock import MockFunctionCallingLLM

from llama_index.tools.typesearch import TypesearchToolSpec

from .fake_api import KEY, FakeApi


def scripted(messages: Sequence[ChatMessage], **kwargs: Any) -> ChatMessage:
    if any(m.role == MessageRole.TOOL for m in messages):
        return ChatMessage(role=MessageRole.ASSISTANT, content="The peso held steady (Diario Ejemplo).")
    call = ToolCallBlock(tool_call_id="call_1", tool_name="search_news", tool_kwargs={"query": "el dólar", "days": 1})
    return ChatMessage(role=MessageRole.ASSISTANT, blocks=[call])


async def run(api: FakeApi, key: str = KEY) -> tuple[str, list[ToolCallResult]]:
    agent = FunctionAgent(
        tools=TypesearchToolSpec(key, base_url=api.url, max_retries=0).to_tool_list(),
        llm=MockFunctionCallingLLM(response_generator=scripted),
    )
    handler = agent.run("What happened with the peso today?")
    results = [ev async for ev in handler.stream_events() if isinstance(ev, ToolCallResult)]
    return str(await handler), results


async def test_the_agent_calls_search_news_and_reads_the_results(api: FakeApi) -> None:
    answer, results = await run(api)
    assert api.last.body == {"query": "el dólar", "mode": "fast", "max_results": 10, "days": 1}
    assert results[0].tool_name == "search_news"
    assert str(results[0].tool_output).startswith('10 results for "el dólar" · fast')
    assert answer == "The peso held steady (Diario Ejemplo)."


async def test_an_api_error_reaches_the_model_as_the_tool_result(api: FakeApi) -> None:
    _, results = await run(api, key="ts_live_wrong")
    assert results[0].tool_output.is_error
    assert "typesearch error (invalid_api_key): The API key is not valid." in str(results[0].tool_output)
