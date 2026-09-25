"""A LlamaIndex agent that answers with recent news and cites its sources.

pip install llama-index-tools-typesearch llama-index-llms-openai
TYPESEARCH_API_KEY=ts_live_... OPENAI_API_KEY=... python examples/agent.py "What changed in EU AI Act enforcement this week?"
"""

import asyncio
import sys

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI

from llama_index.tools.typesearch import TypesearchToolSpec

agent = FunctionAgent(
    tools=TypesearchToolSpec(max_results=8).to_tool_list(),  # reads TYPESEARCH_API_KEY
    llm=OpenAI(model="gpt-4.1"),
    system_prompt="Answer with recent news. Cite the source and the link of every fact.",
)


async def main() -> None:
    question = " ".join(sys.argv[1:]) or "What changed in EU AI Act enforcement this week?"
    print(await agent.run(question))


if __name__ == "__main__":
    asyncio.run(main())
