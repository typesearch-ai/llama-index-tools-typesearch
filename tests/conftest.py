from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from .fake_api import FakeApi, shared


@pytest.fixture
def api() -> Iterator[FakeApi]:
    a = shared()
    a.reset()
    yield a
    a.reset()


@pytest.fixture(autouse=True)
def _no_key_from_the_environment(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    # Las pruebas no leen la clave ni la URL de quien las corre, salvo las en vivo
    # (TYPESEARCH_LIVE=1 pytest tests/test_live.py).
    if not (os.environ.get("TYPESEARCH_LIVE") == "1" and "test_live" in request.node.nodeid):
        monkeypatch.delenv("TYPESEARCH_API_KEY", raising=False)
        monkeypatch.delenv("TYPESEARCH_BASE_URL", raising=False)
