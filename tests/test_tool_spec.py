"""TypesearchToolSpec against the fake API: the tools an agent gets, what they send and what the model reads."""

from __future__ import annotations

from typing import Any

import pytest
from llama_index.core.tools import FunctionTool
from llama_index.core.tools.tool_spec.base import BaseToolSpec
from typesearch import RateLimitError, Typesearch

from llama_index.tools.typesearch import TypesearchToolError, TypesearchToolSpec, __version__

from .fake_api import KEY, FakeApi, Scripted, problem, search_response


def spec(api: FakeApi, **kwargs: Any) -> TypesearchToolSpec:
    return TypesearchToolSpec(KEY, base_url=api.url, max_retries=0, **kwargs)


def tools(s: TypesearchToolSpec) -> dict[str, FunctionTool]:
    return {t.metadata.name or "": t for t in s.to_tool_list()}


def test_class() -> None:
    assert BaseToolSpec.__name__ in [b.__name__ for b in TypesearchToolSpec.__mro__]


def test_four_tools_with_the_mcp_names_and_parameters(api: FakeApi) -> None:
    ts = tools(spec(api))
    assert list(ts) == ["search_news", "get_contents", "find_similar", "check_coverage"]
    props = {name: t.metadata.get_parameters_dict() for name, t in ts.items()}
    assert list(props["search_news"]["properties"]) == [
        "query",
        "days",
        "published_after",
        "published_before",
        "include_domains",
        "exclude_domains",
        "countries",
        "languages",
    ]
    assert props["search_news"]["required"] == ["query"]
    assert props["search_news"]["properties"]["countries"]["description"].startswith("Only sources from these countries")
    assert list(props["get_contents"]["properties"]) == ["urls", "query"]
    assert list(props["find_similar"]["properties"]) == ["url", "days"]
    assert list(props["check_coverage"]["properties"]) == ["domain"]
    assert "Cite the link of every fact." in ts["search_news"].metadata.description


def test_search_news_defaults_and_text(api: FakeApi) -> None:
    out = tools(spec(api))["search_news"].call(query="el dólar")
    assert api.last.path == "/v1/search"
    assert api.last.body == {"query": "el dólar", "mode": "fast", "max_results": 10}
    assert api.last.headers["authorization"] == f"Bearer {KEY}"
    assert api.last.headers["user-agent"].startswith(f"llama-index-tools-typesearch/{__version__} typesearch-python/")
    text = str(out)
    assert not out.is_error
    assert text.startswith('10 results for "el dólar" · fast · US$0.0014')
    assert (
        "1. El dólar cerró estable por 1ª rueda\nDiario Ejemplo · 2026-09-21 18:05 UTC · AR/es\nhttps://diarioejemplo.example/economia/nota-1"
        in text
    )
    assert "found beyond the index" in text


def test_search_news_passes_what_the_agent_asks_for_and_the_fixed_filters_win(api: FakeApi) -> None:
    s = spec(api, mode="normal", max_results=5, countries=["AR"], highlights=True, timezone="America/Argentina/Buenos_Aires")
    s.search_news(
        "lithium royalties",
        days=3,
        include_domains=["diarioejemplo.example"],
        exclude_domains=["examplewire.example"],
        countries=["US"],
        languages=["es"],
    )
    assert api.last.body == {
        "query": "lithium royalties",
        "mode": "normal",
        "max_results": 5,
        "days": 3,
        "include_domains": ["diarioejemplo.example"],
        "exclude_domains": ["examplewire.example"],
        "countries": ["AR"],
        "languages": ["es"],
        "highlights": True,
        "timezone": "America/Argentina/Buenos_Aires",
    }
    s.search_news("lithium royalties", published_after="2026-09-01", published_before="2026-09-20T12:00:00Z")
    assert api.last.body["published_after"] == "2026-09-01"
    assert api.last.body["published_before"] == "2026-09-20T12:00:00Z"


def test_days_is_the_window_when_the_agent_asks_for_none(api: FakeApi) -> None:
    s = spec(api, days=1)
    s.search_news("el dólar")
    assert api.last.body["days"] == 1
    s.search_news("el dólar", days=30)
    assert api.last.body["days"] == 30
    s.search_news("el dólar", published_after="2026-09-01")
    assert "days" not in api.last.body


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": "x"},
        {"query": "el dólar", "days": 0},
        {"query": "el dólar", "published_after": "yesterday"},
        {"query": "el dólar", "countries": ["AR"] * 51},
    ],
)
def test_invalid_input_never_reaches_the_api(api: FakeApi, kwargs: dict[str, Any]) -> None:
    with pytest.raises(TypesearchToolError):
        spec(api).search_news(**kwargs)
    with pytest.raises(TypesearchToolError):
        tools(spec(api))["search_news"].call(**kwargs)
    assert api.requests == []


def test_invalid_settings() -> None:
    with pytest.raises(ValueError):
        TypesearchToolSpec(max_results=51)
    with pytest.raises(ValueError):
        TypesearchToolSpec(mode="turbo")  # type: ignore[arg-type]


def test_nothing_found(api: FakeApi) -> None:
    body = search_response(
        0,
        near_misses=[search_response(1)["results"][0]],
        cached_at="2026-09-25T10:00:00Z",
        incomplete=True,
        warnings=[{"code": "country_not_indexed", "message": "No source from XX."}],
    )
    api.next(Scripted(200, body))
    text = spec(api).search_news("el dólar")
    assert text.startswith('No results for "el dólar" · fast · cached, free')
    assert "Closest articles, which may not be about it:" in text
    assert "Incomplete:" in text
    assert "Note (country_not_indexed): No source from XX." in text


def test_get_contents(api: FakeApi) -> None:
    text = spec(api).get_contents(
        ["https://cronicaejemplo.example/politica/presupuesto", "https://unreachable.example/x"], query="presupuesto"
    )
    assert api.last.path == "/v1/contents"
    assert api.last.body == {
        "urls": ["https://cronicaejemplo.example/politica/presupuesto", "https://unreachable.example/x"],
        "query": "presupuesto",
    }
    assert text.split("\n")[0] == "1 of 2 URLs read · US$0.0002"
    assert "> El proyecto prevé un superávit primario…\n> Las provincias recibirán más fondos\nRelevance to the query: 0.97" in text
    assert "Error (site_unreachable): The site did not answer." in text
    spec(api).get_contents(["https://cronicaejemplo.example/a"])
    assert api.last.body == {"urls": ["https://cronicaejemplo.example/a"]}
    with pytest.raises(TypesearchToolError):
        spec(api).get_contents([])


def test_find_similar(api: FakeApi) -> None:
    text = spec(api, max_results=3).find_similar("https://diarioejemplo.example/economia/nota-1", days=30)
    assert api.last.path == "/v1/similar"
    assert api.last.body == {"url": "https://diarioejemplo.example/economia/nota-1", "mode": "fast", "max_results": 3, "days": 30}
    assert text.startswith('2 similar articles to "Inflación: qué esperan los analistas" · US$0.0014')


def test_find_similar_nothing_found(api: FakeApi) -> None:
    api.next(Scripted(200, search_response(0, object="similar", queries=[], reference=None)))
    assert spec(api).find_similar("https://diarioejemplo.example/a").startswith("No similar articles · US$")


def test_check_coverage(api: FakeApi) -> None:
    s = spec(api)
    assert (
        s.check_coverage("diarioejemplo.example")
        == "diarioejemplo.example is covered (Diario Ejemplo): AR · es · 1,520 articles · last refreshed 2026-09-22T14:05Z."
    )
    assert api.last.query["domain"] == ["diarioejemplo.example"]
    assert s.check_coverage("otro.example") == "otro.example is not covered by the index."
    assert s.check_coverage() == (
        "The index has 1,234 sources and 567,890 articles.\nSources by country: AR 120, international 4.\nSources by language: es 900."
    )


def test_errors_are_readable_and_keep_the_sdk_error(api: FakeApi) -> None:
    with pytest.raises(
        TypesearchToolError, match=r"^typesearch error \(invalid_api_key\): The API key is not valid\. \[request req_fakeerr1\]$"
    ):
        TypesearchToolSpec("ts_live_wrong", base_url=api.url).search_news("el dólar")
    api.next(Scripted(429, problem(429, "rate_limited", "Too many requests."), {"Retry-After": "9"}))
    with pytest.raises(TypesearchToolError, match="Retry after 9 s.") as e:
        spec(api).search_news("el dólar")
    assert isinstance(e.value.__cause__, RateLimitError)
    api.next(Scripted(402, problem(402, "insufficient_credits", "No credit left.")))
    with pytest.raises(TypesearchToolError, match=r"typesearch error \(insufficient_credits\): No credit left\."):
        tools(spec(api))["get_contents"].call(urls=["https://cronicaejemplo.example/a"])


def test_a_missing_key_fails_the_call_not_the_constructor(api: FakeApi) -> None:
    s = TypesearchToolSpec(base_url=api.url)
    with pytest.raises(TypesearchToolError, match="Missing API key"):
        s.check_coverage()
    assert api.requests == []


def test_the_key_comes_from_the_environment(api: FakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESEARCH_API_KEY", KEY)
    monkeypatch.setenv("TYPESEARCH_BASE_URL", api.url)
    TypesearchToolSpec().search_news("el dólar")
    assert api.last.headers["authorization"] == f"Bearer {KEY}"


def test_a_client_of_your_own(api: FakeApi) -> None:
    TypesearchToolSpec(client=Typesearch(KEY, base_url=api.url, default_headers={"X-Trace": "abc"})).search_news("el dólar")
    assert api.last.headers["x-trace"] == "abc"


async def test_async_tool_calls(api: FakeApi) -> None:
    out = await tools(spec(api, max_results=3))["search_news"].acall(query="el dólar")
    assert str(out).startswith('3 results for "el dólar"')
