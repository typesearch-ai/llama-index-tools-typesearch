# llama-index-tools-typesearch

[typesearch](https://typesearch.ai) news search for [LlamaIndex](https://developers.llamaindex.ai) agents:
recent news on any topic from outlets worldwide, by country and language, with a calibrated relevance score
on every result.

```bash
pip install llama-index-tools-typesearch
```

Python 3.10+, `llama-index-core` 0.13–0.14. Create a key in the [dashboard](https://app.typesearch.ai) and
set it as `TYPESEARCH_API_KEY`.

## Usage

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI
from llama_index.tools.typesearch import TypesearchToolSpec

tools = TypesearchToolSpec().to_tool_list()  # reads TYPESEARCH_API_KEY

agent = FunctionAgent(
    tools=tools,
    llm=OpenAI(model="gpt-4.1"),
    system_prompt="Answer with recent news. Cite the source and the link of every fact.",
)
response = await agent.run("What changed in EU AI Act enforcement this week?")
```

## Tools

The same tools, parameters and descriptions as the [typesearch MCP server](https://typesearch.ai/docs/integrations/mcp):

| Tool | What it does | What the agent can set |
| --- | --- | --- |
| `search_news` | News on a topic: title, link, source, date, country and language, standfirst and short excerpts, each with a relevance score. | `query`, `days`, `published_after`, `published_before`, `include_domains`, `exclude_domains`, `countries`, `languages` |
| `get_contents` | Title, standfirst, date, source and a short verbatim excerpt (up to 25 words) of up to 10 article URLs — never the full text. | `urls`, `query` |
| `find_similar` | Other coverage of the story in an article URL. | `url`, `days` |
| `check_coverage` | Whether a news domain is covered, or the index coverage by country and language. Free. | `domain` |

Each tool returns a compact, readable text list with the link of every article, the same text the MCP
server returns: it leaves room in the context window for the answer. You can also call them directly:

```python
spec = TypesearchToolSpec(max_results=5)
print(spec.search_news("lithium royalties in Chile", days=30, languages=["es", "en"]))
```

## Settings

| Parameter | Default | |
| --- | --- | --- |
| `api_key` | `TYPESEARCH_API_KEY` | Your key. |
| `base_url` | `TYPESEARCH_BASE_URL` | Defaults to `https://api.typesearch.ai`. |
| `mode` | `"fast"` | How much `search_news` reads before ranking: `ultra`, `fast`, `normal` or `deep`. See [modes](https://typesearch.ai/docs/modes). |
| `max_results` | `10` | Per search and per `find_similar`, 1 to 50. |
| `days` | — | The window when the agent asks for none. The API's default is the last 7 days. |
| `include_domains` · `exclude_domains` | — | Fixed domain filters. |
| `countries` · `languages` | — | Fixed country (ISO 3166-1 alpha-2) and language (ISO 639-1) filters of the sources. |
| `highlights` | — | Verbatim excerpts from the articles read (`normal` and `deep`). |
| `timezone` | — | IANA time zone that decides what day "today" is. |
| `timeout` · `max_retries` | `70` · `2` | Per request, as in the [`typesearch`](https://pypi.org/project/typesearch/) SDK. |
| `client` | — | A `typesearch.Typesearch` client you already have. |

A filter set here always applies, over what the agent asks for, in `search_news` and in `find_similar`
(where the agent never sees them). To give the agent only some tools:
`TypesearchToolSpec().to_tool_list(spec_functions=["search_news"])`.

## Errors

A failed call raises `TypesearchToolError` with a message the agent can read and act on —
`typesearch error (rate_limited): … Retry after 12 s.` — without the key; agents hand it to the model as
the tool result. The original [`typesearch`](https://pypi.org/project/typesearch/) error is its `__cause__`.
The key is read on the first call, so building the tools never fails without it.

## Pricing

Each call is billed to your key like the API request it makes: a search by its mode, `get_contents` per
page, `find_similar` per request; `check_coverage` is free. Identical calls within 10 minutes come from the
cache and cost nothing. Prices: [typesearch.ai/pricing](https://typesearch.ai/pricing).

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest                       # against a fake API that validates every request against the API schema,
                                    # and a FunctionAgent end to end with a mock LLM
TYPESEARCH_LIVE=1 TYPESEARCH_API_KEY=ts_live_… uv run pytest tests/test_live.py   # the real API (less than a cent)
```

## License

[MIT](LICENSE)
