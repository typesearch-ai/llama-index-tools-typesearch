"""Una API falsa de typesearch, por HTTP de verdad, equivalente a la de los SDKs.

Valida cada pedido contra el esquema del OpenAPI (tests/fixtures/requests.schema.json: SearchRequest,
SimilarRequest y ContentsRequest, con countries y languages; como la API, rechaza campos desconocidos con
400 invalid_request) y responde con ejemplos de medios ficticios ``.example``: tantos resultados como pide
``max_results``. Guarda cada pedido; ``api.next(...)`` encola respuestas armadas a mano.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from jsonschema import Draft202012Validator, FormatChecker

KEY = "ts_test_llamaindex"
_SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "requests.schema.json").read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"components": _SCHEMA["components"], "$ref": f"#/components/schemas/{name}"}, format_checker=FormatChecker()
    )


_VALIDATORS = {name: _validator(name) for name in ("SearchRequest", "SimilarRequest", "ContentsRequest")}


def result(n: int, **extra: Any) -> dict[str, Any]:
    wire = n % 2 == 0
    return {
        "url": f"https://examplewire.example/markets/story-{n}" if wire else f"https://diarioejemplo.example/economia/nota-{n}",
        "title": f"Peso holds steady for day {n}" if wire else f"El dólar cerró estable por {n}ª rueda",
        "source": "Example Wire" if wire else "Diario Ejemplo",
        "published_at": "2026-09-21T18:05:31.000Z",
        "section": "economia",
        "snippet": None if wire else "La divisa se mantuvo sin cambios frente al cierre anterior.",
        "score": 0.9612 - n / 100,
        "headline_relevance": 0.91,
        "read": None,
        "highlights": ["The peso ended the session unchanged"] if wire else [],
        "tone": None,
        "answers": None,
        "duplicates": [],
        "date_match": None,
        "referenced_date": None,
        "found_in": "discovery" if wire else "index",
        "country": None if wire else "AR",
        "language": "en" if wire else "es",
        **extra,
    }


def search_response(n: int = 2, **extra: Any) -> dict[str, Any]:
    return {
        "id": "req_fakeli",
        "object": "search",
        "mode": "fast",
        "queries": ["el dólar"],
        "found": n > 0,
        "total": n,
        "results": [result(i) for i in range(1, n + 1)],
        "groups": None,
        "near_misses": [],
        "rejected": [],
        "diffusion": None,
        "tone": None,
        "essential": None,
        "reference": None,
        "temporal": None,
        "site": None,
        "index": None,
        "usage": {
            "tokens": 1840,
            "calls": 2,
            "cost_usd": 0.0014,
            "headlines": 160,
            "from_memory": 0,
            "pages_direct": 0,
            "pages_browser": 0,
            "duration_ms": 910,
        },
        "budget": None,
        "discovery": None,
        "incomplete": False,
        "cached_at": None,
        "warnings": [],
        **extra,
    }


def contents_response(urls: list[str], query: str | None) -> dict[str, Any]:
    results = []
    for u in urls:
        if "unreachable" in u:
            empty = {
                "title": None,
                "description": None,
                "published_at": None,
                "source": None,
                "excerpt": None,
                "highlights": [],
                "relevance": None,
            }
            results.append(
                {"url": u, "status": "error", "error": {"code": "site_unreachable", "message": "The site did not answer."}, **empty}
            )
        else:
            results.append(
                {
                    "url": u,
                    "status": "ok",
                    "error": None,
                    "title": "Presupuesto 2027: las claves del proyecto",
                    "description": "El Gobierno envió el proyecto al Congreso.",
                    "published_at": "2026-09-16T01:12:00.000Z",
                    "source": "Crónica Ejemplo",
                    "excerpt": "El proyecto prevé un superávit primario…",
                    "highlights": ["El proyecto prevé un superávit primario…", "Las provincias recibirán más fondos"] if query else [],
                    "relevance": 0.9712 if query else None,
                }
            )
    return {
        "id": "req_fakecont",
        "object": "contents",
        "results": results,
        "usage": {"tokens": 1320, "calls": 1, "cost_usd": 0.0002, "duration_ms": 1840},
    }


def problem(status: int, code: str, detail: str | None = None) -> dict[str, Any]:
    return {
        "type": f"urn:typesearch:error:{code}",
        "title": code,
        "status": status,
        "detail": detail or f"detail of {code}",
        "code": code,
        "request_id": "req_fakeerr1",
    }


@dataclass
class Scripted:
    status: int
    body: Any
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Recorded:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: Any


class FakeApi:
    def __init__(self) -> None:
        self.requests: list[Recorded] = []
        self._queue: list[Scripted] = []
        self._lock = threading.Lock()
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                api._handle(self)

            def do_POST(self) -> None:
                api._handle(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self._queue.clear()

    def next(self, *responses: Scripted) -> FakeApi:
        with self._lock:
            self._queue.extend(responses)
        return self

    @property
    def last(self) -> Recorded:
        return self.requests[-1]

    def _handle(self, h: BaseHTTPRequestHandler) -> None:
        url = urlparse(h.path)
        length = int(h.headers.get("content-length") or 0)
        body = json.loads(h.rfile.read(length)) if length else None
        with self._lock:
            self.requests.append(Recorded(h.command, url.path, parse_qs(url.query), {k.lower(): v for k, v in h.headers.items()}, body))
            scripted = self._queue.pop(0) if self._queue else None
        if scripted is not None:
            return self._send(h, scripted.status, scripted.body, scripted.headers)
        auth = h.headers.get("authorization")
        if not auth:
            return self._send(h, 401, problem(401, "missing_api_key", "Missing API key."))
        if auth != f"Bearer {KEY}":
            return self._send(h, 401, problem(401, "invalid_api_key", "The API key is not valid."))
        route = f"{h.command} {url.path}"
        if route == "POST /v1/search":
            if self._valid(h, "SearchRequest", body):
                self._send(h, 200, search_response(body.get("max_results", 10), mode=body.get("mode", "normal"), queries=[body["query"]]))
            return None
        if route == "POST /v1/similar":
            if self._valid(h, "SimilarRequest", body):
                reference = {"url": body["url"], "title": "Inflación: qué esperan los analistas"}
                self._send(
                    h,
                    200,
                    search_response(
                        min(body.get("max_results", 10), 2),
                        object="similar",
                        mode=body.get("mode", "normal"),
                        queries=[],
                        reference=reference,
                    ),
                )
            return None
        if route == "POST /v1/contents":
            if self._valid(h, "ContentsRequest", body):
                self._send(h, 200, contents_response(body["urls"], body.get("query")))
            return None
        if route == "GET /v1/sources":
            domain = parse_qs(url.query).get("domain", [None])[0]
            if domain is None:
                out: dict[str, Any] = {
                    "object": "sources",
                    "updated_at": "2026-09-22T14:05:02.000Z",
                    "total": 1234,
                    "articles": 567890,
                    "by_country": [{"country": "AR", "sources": 120}, {"country": None, "sources": 4}],
                    "by_language": [{"language": "es", "sources": 900}],
                }
            elif domain == "diarioejemplo.example":
                out = {
                    "object": "source",
                    "domain": domain,
                    "covered": True,
                    "name": "Diario Ejemplo",
                    "country": "AR",
                    "languages": ["es"],
                    "articles": 1520,
                    "last_refreshed_at": "2026-09-22T14:05:02.000Z",
                }
            else:
                out = {"object": "source", "domain": domain, "covered": False}
            return self._send(h, 200, out)
        return self._send(h, 404, problem(404, "not_found"))

    def _valid(self, h: BaseHTTPRequestHandler, name: str, body: Any) -> bool:
        errors = sorted(_VALIDATORS[name].iter_errors(body), key=lambda e: list(e.absolute_path))
        if errors:
            path = ".".join(str(p) for p in errors[0].absolute_path) or "(body)"
            self._send(
                h,
                400,
                {
                    **problem(400, "invalid_request", f"{path}: {errors[0].message}"),
                    "errors": [{"path": path, "message": errors[0].message}],
                },
            )
        return not errors

    def _send(self, h: BaseHTTPRequestHandler, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
        data = json.dumps(body).encode("utf-8")
        h.send_response(status)
        h.send_header("Content-Type", "application/problem+json" if status >= 400 else "application/json")
        h.send_header("X-Request-Id", "req_fake0001")
        h.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            h.send_header(k, v)
        h.end_headers()
        h.wfile.write(data)


_SHARED: FakeApi | None = None


def shared() -> FakeApi:
    """Una sola API falsa para toda la sesión de pruebas (también para las propiedades de los standard tests)."""
    global _SHARED
    if _SHARED is None:
        _SHARED = FakeApi()
    return _SHARED
