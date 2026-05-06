"""Tests for spec_check.core.transport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from spec_check.core.transport import NullTransport, PrefetchedTransport


class TestNullTransport:
    def test_search_returns_empty(self) -> None:
        assert NullTransport().call("search", query="anything") == {"results": []}

    def test_fetch_block_children_returns_empty(self) -> None:
        out = NullTransport().call("fetch_block_children", block_id="b")
        assert out == {"results": [], "has_more": False, "next_cursor": None}

    def test_fetch_page_returns_minimal_shell(self) -> None:
        out = NullTransport().call("fetch_page", page_id="p")
        assert out["id"] == "p"

    def test_unknown_method_safe_default(self) -> None:
        assert NullTransport().call("query_database", database_id="d") == {}


class TestPrefetchedTransport:
    def _payload(self) -> dict[str, Any]:
        return {
            "page": {
                "id": "p1",
                "url": "u",
                "properties": {"title": {"title": [{"plain_text": "T"}]}},
            },
            "blocks": [{"id": "b1"}, {"id": "b2"}],
            "search_results": {"foo": [{"id": "p1"}]},
        }

    def test_fetch_page_returns_payload_page(self) -> None:
        t = PrefetchedTransport(self._payload())
        out = t.call("fetch_page", page_id="p1")
        assert out["id"] == "p1"

    def test_fetch_block_children_serves_blocks_once(self) -> None:
        t = PrefetchedTransport(self._payload())
        first = t.call("fetch_block_children", block_id="p1")
        assert [b["id"] for b in first["results"]] == ["b1", "b2"]
        assert first["has_more"] is False
        # Subsequent calls return empty so a paginating consumer terminates.
        second = t.call("fetch_block_children", block_id="p1", start_cursor="x")
        assert second["results"] == []

    def test_search_with_known_query(self) -> None:
        t = PrefetchedTransport(self._payload())
        assert t.call("search", query="foo")["results"] == [{"id": "p1"}]

    def test_search_with_unknown_query_returns_empty(self) -> None:
        t = PrefetchedTransport(self._payload())
        assert t.call("search", query="bar") == {"results": []}

    def test_from_file(self, tmp_path: Path) -> None:
        path = tmp_path / "payload.json"
        path.write_text(json.dumps(self._payload()))
        t = PrefetchedTransport.from_file(path)
        assert t.call("fetch_page", page_id="p1")["id"] == "p1"

    def test_non_dict_payload_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be a dict"):
            PrefetchedTransport([])  # type: ignore[arg-type]

    def test_missing_page_falls_back_to_minimal(self) -> None:
        t = PrefetchedTransport({"blocks": []})
        out = t.call("fetch_page", page_id="p")
        assert out["id"] == "p"
