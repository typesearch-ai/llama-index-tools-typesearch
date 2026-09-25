"""typesearch tool spec: news search for LlamaIndex agents."""

import re
from importlib import metadata
from typing import Any, Literal

from llama_index.core.tools.tool_spec.base import BaseToolSpec

import typesearch
from typesearch import APIConnectionError, APIError, APITimeoutError, RateLimitError, Typesearch, TypesearchError

from ._format import (
    contents_output,
    contents_text,
    coverage_output,
    coverage_text,
    find_similar_output,
    find_similar_text,
    news_search_output,
    news_search_text,
)

try:
    __version__ = metadata.version("llama-index-tools-typesearch")
except metadata.PackageNotFoundError:  # pragma: no cover - sin instalar
    __version__ = "0.0.0"

USER_AGENT = f"llama-index-tools-typesearch/{__version__} typesearch-python/{typesearch.__version__}"

Mode = Literal["ultra", "fast", "normal", "deep"]

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2}))?$")


class TypesearchToolError(Exception):
    """A typesearch call failed. The message is meant for the agent (and has no key); the SDK error is
    ``__cause__``."""


def _readable(e: Exception) -> TypesearchToolError:
    if isinstance(e, APIError):
        retry = f" Retry after {e.retry_after:g} s." if isinstance(e, RateLimitError) and e.retry_after else ""
        request = f" [request {e.request_id}]" if e.request_id else ""
        return TypesearchToolError(f"typesearch error ({e.code}): {e.message}{retry}{request}")
    if isinstance(e, APITimeoutError):
        return TypesearchToolError("typesearch error (timeout): the API took too long to answer. Try again, or use a lighter mode.")
    if isinstance(e, APIConnectionError):
        return TypesearchToolError("typesearch error (connection): could not reach the typesearch API. Try again.")
    return TypesearchToolError(f"typesearch error: {e}")


def _check_list(name: str, value: list[str] | None, most: int) -> None:
    if value is not None and (not isinstance(value, list) or len(value) > most or not all(isinstance(x, str) for x in value)):
        raise TypesearchToolError(f"{name} must be a list of at most {most} strings.")


class TypesearchToolSpec(BaseToolSpec):
    """typesearch tool spec: news search, article contents, similar coverage and index coverage.

    Each tool returns a compact, readable text — the same as the typesearch MCP server — with the link of
    every article to cite. Filters set here (``countries``, ``languages``, ``include_domains``,
    ``exclude_domains``) always apply, over what the agent asks for.

    >>> from llama_index.tools.typesearch import TypesearchToolSpec
    >>> tools = TypesearchToolSpec().to_tool_list()  # reads TYPESEARCH_API_KEY
    """

    spec_functions = ["search_news", "get_contents", "find_similar", "check_coverage"]

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        mode: Mode = "fast",
        max_results: int = 10,
        days: int | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        countries: list[str] | None = None,
        languages: list[str] | None = None,
        highlights: bool | None = None,
        timezone: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: Typesearch | None = None,
    ) -> None:
        """
        Args:
            api_key: Your typesearch API key. Defaults to the ``TYPESEARCH_API_KEY`` environment variable.
            base_url: Defaults to ``TYPESEARCH_BASE_URL``, or ``https://api.typesearch.ai``.
            mode: How much ``search_news`` reads before ranking: ``fast`` (default, the cheapest and
                quickest), ``ultra``, ``normal`` or ``deep``. See https://typesearch.ai/docs/modes.
            max_results: Results per search and per ``find_similar``, 1 to 50. Defaults to 10.
            days: The window when the agent asks for none. The API's default is the last 7 days.
            include_domains: Always search only these domains or paths.
            exclude_domains: Never these domains or paths.
            countries: Always search only sources from these countries (ISO 3166-1 alpha-2).
            languages: Always search only sources in these languages (ISO 639-1).
            highlights: Verbatim excerpts from the articles read (``normal`` and ``deep``).
            timezone: IANA time zone that decides what day "today" is.
            timeout: Seconds before a request is aborted. Defaults to 70.
            max_retries: Retries on connection errors, ``429 rate_limited`` and ``5xx``. Defaults to 2.
            client: A ``typesearch.Typesearch`` client you already have.
        """
        if mode not in ("ultra", "fast", "normal", "deep"):
            raise ValueError("mode must be ultra, fast, normal or deep.")
        if not isinstance(max_results, int) or not 1 <= max_results <= 50:
            raise ValueError("max_results must be a whole number from 1 to 50.")
        self.mode = mode
        self.max_results = max_results
        self.days = days
        self.include_domains = include_domains
        self.exclude_domains = exclude_domains
        self.countries = countries
        self.languages = languages
        self.highlights = highlights
        self.timezone = timezone
        self._client = client
        # El cliente se crea en la primera llamada: armar las herramientas sin clave no falla.
        self._kwargs: dict[str, Any] = {"default_headers": {"User-Agent": USER_AGENT}}
        for key, value in (("api_key", api_key), ("base_url", base_url), ("timeout", timeout), ("max_retries", max_retries)):
            if value is not None:
                self._kwargs[key] = value

    def _api(self) -> Typesearch:
        if self._client is None:
            try:
                self._client = Typesearch(**self._kwargs)
            except TypesearchError as e:
                raise _readable(e) from e
        return self._client

    def search_news(
        self,
        query: str,
        days: int | None = None,
        published_after: str | None = None,
        published_before: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        countries: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> str:
        """Search recent news on any topic across a curated index of news outlets worldwide, judged by a relevance model.
        Returns the matching articles: title, link, source, date, country and language, standfirst, and short excerpts
        in the modes that read, each with a relevance score from 0 to 1. Use it for current events and for what outlets
        reported about a company, person, place or topic. It covers the last 7 days unless you set days or a date range.
        Cite the link of every fact.

        Args:
            query (str): What to look for, in any language: a topic, event, person, company or place, such as "inflation in Argentina" or "OpenAI funding".
            days (int, optional): Only the last N days, 1 to 365. Defaults to 7 unless published_after or published_before are given.
            published_after (str, optional): Published on or after this date: 2026-09-25, or a date-time with offset.
            published_before (str, optional): Published on or before this date; a bare date includes that whole day.
            include_domains (list[str], optional): Only these domains or paths, such as example.com or example.com/sports.
            exclude_domains (list[str], optional): Never these domains or paths.
            countries (list[str], optional): Only sources from these countries: ISO 3166-1 alpha-2 codes, such as ["AR"] or ["US", "GB"].
            languages (list[str], optional): Only sources that publish in these languages: ISO 639-1 codes, such as ["es"] or ["en", "pt"].
        """
        query = (query or "").strip()
        if not 2 <= len(query) <= 200:
            raise TypesearchToolError("query needs 2 to 200 characters.")
        if days is not None and not (isinstance(days, int) and 1 <= days <= 365):
            raise TypesearchToolError("days must be a whole number from 1 to 365.")
        for name, value in (("published_after", published_after), ("published_before", published_before)):
            if value is not None and not _DATE.match(value):
                raise TypesearchToolError(f"{name} must be a date (2026-09-25) or a date-time with its offset (2026-09-25T14:00:00Z).")
        for name, lst, most in (
            ("include_domains", include_domains, 20),
            ("exclude_domains", exclude_domains, 20),
            ("countries", countries, 50),
            ("languages", languages, 20),
        ):
            _check_list(name, lst, most)

        dated = days is not None or published_after is not None or published_before is not None
        options: dict[str, Any] = {"mode": self.mode, "max_results": self.max_results}
        window = days if days is not None else (None if dated else self.days)
        if window is not None:
            options["days"] = window
        if published_after:
            options["published_after"] = published_after
        if published_before:
            options["published_before"] = published_before
        for key, fixed, asked in (
            ("include_domains", self.include_domains, include_domains),
            ("exclude_domains", self.exclude_domains, exclude_domains),
            ("countries", self.countries, countries),
            ("languages", self.languages, languages),
        ):
            chosen = fixed or asked
            if chosen:
                options[key] = list(chosen)
        if self.highlights is not None:
            options["highlights"] = self.highlights
        if self.timezone:
            options["timezone"] = self.timezone
        try:
            res = self._api().search(query, **options)
        except TypesearchError as e:
            raise _readable(e) from e
        return news_search_text(news_search_output(res, query))

    def get_contents(self, urls: list[str], query: str | None = None) -> str:
        """Get the title, standfirst, date, source and a short verbatim excerpt (up to 25 words) of up to 10 news
        article URLs. With a query, the excerpt is the one about it and relevance says how much the article covers it.
        Never returns the full text.

        Args:
            urls (list[str]): Up to 10 article URLs, such as https://example.com/news/article.
            query (str, optional): Optional: the excerpt is then the one about this query, with a relevance score.
        """
        if isinstance(urls, str):
            urls = [urls]
        if not urls or len(urls) > 10:
            raise TypesearchToolError("urls needs 1 to 10 article URLs.")
        try:
            q = query.strip() if query else ""
            res = self._api().contents(urls, query=q) if q else self._api().contents(urls)
        except TypesearchError as e:
            raise _readable(e) from e
        return contents_text(contents_output(res))

    def find_similar(self, url: str, days: int | None = None) -> str:
        """Find other news articles about the same story as a given article URL, across the index (the last 7 days by
        default). Useful to see how other outlets covered a story.

        Args:
            url (str): The article URL whose story to find elsewhere.
            days (int, optional): Only the last N days, 1 to 365. Defaults to 7.
        """
        if days is not None and not (isinstance(days, int) and 1 <= days <= 365):
            raise TypesearchToolError("days must be a whole number from 1 to 365.")
        window = days if days is not None else self.days
        # `fast`: similar cuesta lo mismo en ultra, fast y normal, y fast no lee más que la nota de referencia.
        options: dict[str, Any] = {"mode": "fast", "max_results": self.max_results, **({"days": window} if window is not None else {})}
        try:
            res = self._api().similar(url, **options)
        except TypesearchError as e:
            raise _readable(e) from e
        return find_similar_text(find_similar_output(res))

    def check_coverage(self, domain: str | None = None) -> str:
        """Check whether a news domain is in the typesearch index (pass domain), or get the index coverage: how many
        sources and articles, by country and by language. Free.

        Args:
            domain (str, optional): A news domain, such as example.com. Without it: the coverage by country and language.
        """
        try:
            res = self._api().sources(domain=domain.strip()) if domain and domain.strip() else self._api().sources()
        except TypesearchError as e:
            raise _readable(e) from e
        return coverage_text(coverage_output(res))
