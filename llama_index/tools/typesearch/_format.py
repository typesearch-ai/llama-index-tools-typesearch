"""La salida de cada herramienta: los datos sin campos vacíos y un texto breve y legible, que es lo que lee el
modelo. Es el mismo formato que el MCP de typesearch (``salidaDe*`` en typesearch-api/lib/api/mcp-contrato.ts):
un agente ve lo mismo por el MCP y por este paquete."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from typesearch.types import ContentsResponse, Result, SearchResponse, Source, Sources

_WHERE = {
    "homepage": "from the homepage",
    "section": "from a section page",
    "site_search": "from the site's search",
    "discovery": "found beyond the index",
}


def compact(d: dict[str, Any]) -> dict[str, Any]:
    """Sin None, sin cadenas vacías y sin listas vacías: lo que no dice nada no gasta tokens."""
    return {k: v for k, v in d.items() if v is not None and v != "" and not (isinstance(v, list) and len(v) == 0)}


def shorten(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    cut = clean.rfind(" ", 0, limit)
    return f"{clean[: cut if cut > limit * 0.6 else limit - 1]}…"


def to_minute(iso: str | None) -> str | None:
    """ISO al minuto, en UTC: ``2026-09-25T14:05Z``."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def round2(x: float) -> float:
    """Como ``Math.round(x * 100) / 100`` en JavaScript (el .5 sube), para que dé lo mismo que el MCP."""
    return math.floor(x * 100 + 0.5) / 100


def compact_result(r: Result) -> dict[str, Any]:
    found_in = getattr(r, "found_in", None)
    return compact(
        {
            "title": r.title,
            "url": r.url,
            "source": r.source,
            "published_at": to_minute(r.published_at),
            # El país y el idioma de la fuente llegan con la API que filtra por país e idioma.
            "country": getattr(r, "country", None),
            "language": getattr(r, "language", None),
            "snippet": shorten(r.snippet, 300) if r.snippet else None,
            "highlights": list(r.highlights or []),
            "score": round2(r.score),
            "found_in": None if found_in in (None, "index") else found_in,
        }
    )


def news_search_output(res: SearchResponse, query: str) -> dict[str, Any]:
    """Los datos compactos de una búsqueda. ``results`` va siempre, aunque esté vacía."""
    results = [compact_result(r) for r in res.results or []]
    rest = compact(
        {
            "near_misses": [compact_result(r) for r in (res.near_misses or [])[:5]] if not results else [],
            "incomplete": True if res.incomplete else None,
            "cached": True if res.cached_at else None,
            "cost_usd": (res.usage.cost_usd if res.usage and res.usage.cost_usd is not None else 0),
            "warnings": [{"code": w.code, "message": w.message} for w in res.warnings or []],
            "request_id": res.id,
        }
    )
    return {"query": query, "mode": res.mode, "results": results, **rest}


def _result_lines(r: dict[str, Any], i: int) -> list[str]:
    place = "/".join(x for x in (r.get("country"), r.get("language")) if x)
    when = r["published_at"].replace("T", " ").replace("Z", " UTC") if r.get("published_at") else None
    meta = " · ".join(x for x in (r.get("source"), when, place or None, _WHERE.get(r.get("found_in") or "")) if x)
    lines = [f"{i + 1}. {r['title']}"]
    if meta:
        lines.append(meta)
    lines.append(r["url"])
    if r.get("snippet"):
        lines.append(r["snippet"])
    lines += [f"> {h}" for h in r.get("highlights", [])]
    return lines


def news_search_text(s: dict[str, Any]) -> str:
    """El texto que lee el modelo."""
    n = len(s["results"])
    head = f"{n} result{'' if n == 1 else 's'}" if n else "No results"
    cost = "cached, free" if s.get("cached") else f"US${s['cost_usd']:.4f}"
    parts = [f'{head} for "{s["query"]}" · {s["mode"]} · {cost}']
    if s["results"]:
        parts += ["\n".join(_result_lines(r, i)) for i, r in enumerate(s["results"])]
    elif s.get("near_misses"):
        parts.append("Closest articles, which may not be about it:")
        parts += ["\n".join(_result_lines(r, i)) for i, r in enumerate(s["near_misses"])]
    if s.get("incomplete"):
        parts.append("Incomplete: the time or token budget ran out; repeating the search in a minute may bring more.")
    parts += [f"Note ({w['code']}): {w['message']}" for w in s.get("warnings", [])]
    return "\n\n".join(parts)


# --- Contenidos, parecidas y cobertura, como salidaDeContenidos, salidaDeParecidas y salidaDeCobertura del MCP ---


def find_similar_output(res: SearchResponse) -> dict[str, Any]:
    out = news_search_output(res, "")
    del out["query"]
    ref = res.reference
    return {**({"reference": {"title": ref.title, "url": ref.url}} if ref else {}), **out}


def find_similar_text(s: dict[str, Any]) -> str:
    n = len(s["results"])
    head = f"{n} similar article{'' if n == 1 else 's'}" if n else "No similar articles"
    of = f' to "{s["reference"]["title"]}"' if s.get("reference") else ""
    cost = "cached, free" if s.get("cached") else f"US${s['cost_usd']:.4f}"
    parts = [f"{head}{of} · {cost}"]
    if s["results"]:
        parts += ["\n".join(_result_lines(r, i)) for i, r in enumerate(s["results"])]
    elif s.get("near_misses"):
        parts.append("Closest articles, which may not be about it:")
        parts += ["\n".join(_result_lines(r, i)) for i, r in enumerate(s["near_misses"])]
    if s.get("incomplete"):
        parts.append("Incomplete: the time or token budget ran out; repeating the search in a minute may bring more.")
    parts += [f"Note ({w['code']}): {w['message']}" for w in s.get("warnings", [])]
    return "\n\n".join(parts)


def contents_output(res: ContentsResponse) -> dict[str, Any]:
    results = []
    for x in res.results or []:
        results.append(
            compact(
                {
                    "url": x.url,
                    "status": x.status,
                    "title": x.title,
                    "description": shorten(x.description, 300) if x.description else None,
                    "published_at": to_minute(x.published_at),
                    "source": x.source,
                    "excerpt": x.excerpt,
                    # El fragmento sobre la consulta ya es `excerpt`: los destacados sólo si suman algo.
                    "highlights": [h for h in (x.highlights or []) if h != x.excerpt],
                    "relevance": None if x.relevance is None else round2(x.relevance),
                    "error": {"code": x.error.code, "message": x.error.message} if x.error else None,
                }
            )
        )
    return {"results": results, "cost_usd": res.usage.cost_usd if res.usage and res.usage.cost_usd is not None else 0, "request_id": res.id}


def contents_text(s: dict[str, Any]) -> str:
    ok = sum(1 for x in s["results"] if x["status"] == "ok")
    n = len(s["results"])
    blocks = []
    for i, x in enumerate(s["results"]):
        if x["status"] == "error":
            blocks.append(f"{i + 1}. {x['url']}\nError ({x['error']['code']}): {x['error']['message']}")
            continue
        when = x["published_at"].replace("T", " ").replace("Z", " UTC") if x.get("published_at") else None
        meta = " · ".join(v for v in (x.get("source"), when) if v)
        lines = [f"{i + 1}. {x.get('title') or x['url']}", *([meta] if meta else []), x["url"]]
        if x.get("description"):
            lines.append(x["description"])
        if x.get("excerpt"):
            lines.append(f"> {x['excerpt']}")
        lines += [f"> {h}" for h in x.get("highlights", [])]
        if "relevance" in x:
            lines.append(f"Relevance to the query: {x['relevance']:g}")
        blocks.append("\n".join(lines))
    return "\n\n".join([f"{ok} of {n} URL{'' if n == 1 else 's'} read · US${s['cost_usd']:.4f}", *blocks])


def coverage_output(res: Sources | Source) -> dict[str, Any]:
    if isinstance(res, Source):
        return compact(
            {
                "domain": res.domain,
                "covered": res.covered,
                "name": res.name,
                "country": res.country,
                "languages": list(res.languages or []),
                "articles": res.articles,
                "last_refreshed_at": to_minute(res.last_refreshed_at),
            }
        )
    by_country = [{"country": x.country or "international", "sources": x.sources} for x in res.by_country or []]
    return compact(
        {
            "sources": res.total,
            "articles": res.articles,
            "updated_at": to_minute(res.updated_at),
            "by_country": by_country,
            "by_language": [{"language": x.language, "sources": x.sources} for x in res.by_language or []],
        }
    )


def coverage_text(s: dict[str, Any]) -> str:
    if "domain" in s:
        if not s.get("covered"):
            return f"{s['domain']} is not covered by the index."
        place = " · ".join(v for v in (s.get("country"), "/".join(s.get("languages", [])) or None) if v)
        name = f" ({s['name']})" if s.get("name") else ""
        articles = f" · {s['articles']:,} articles" if "articles" in s else ""
        refreshed = f" · last refreshed {s['last_refreshed_at']}" if s.get("last_refreshed_at") else ""
        return f"{s['domain']} is covered{name}: {place}{articles}{refreshed}."

    def listed(xs: list[dict[str, Any]], key: str) -> str:
        return ", ".join(f"{x[key]} {x['sources']}" for x in xs)

    return "\n".join(
        [
            f"The index has {s.get('sources', 0):,} sources and {s.get('articles', 0):,} articles.",
            f"Sources by country: {listed(s.get('by_country', []), 'country')}.",
            f"Sources by language: {listed(s.get('by_language', []), 'language')}.",
        ]
    )
