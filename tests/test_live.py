"""Against the real API: runs only with ``TYPESEARCH_LIVE=1`` and ``TYPESEARCH_API_KEY`` (less than a cent: one
``fast`` search of 3 results, the contents of one URL, one similar call and the free coverage)."""

from __future__ import annotations

import os
import re

import pytest

from llama_index.tools.typesearch import TypesearchToolSpec

pytestmark = pytest.mark.skipif(
    os.environ.get("TYPESEARCH_LIVE") != "1" or not os.environ.get("TYPESEARCH_API_KEY"), reason="needs TYPESEARCH_LIVE=1 and a key"
)


def test_the_four_tools() -> None:
    spec = TypesearchToolSpec(max_results=3)
    text = spec.search_news("inflation", days=7)
    assert re.match(r'^(\d+ results?|No results) for "inflation" · fast', text)
    url = re.search(r"^(https?://\S+)$", text, re.MULTILINE)
    if url:
        assert "URL" in spec.get_contents([url.group(1)])
        assert "similar article" in spec.find_similar(url.group(1)) or "No similar articles" in spec.find_similar(url.group(1))
    assert spec.check_coverage().startswith("The index has")
