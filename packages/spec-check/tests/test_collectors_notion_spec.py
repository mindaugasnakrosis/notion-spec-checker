"""Tests for spec_check.core.collectors.notion_spec."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from spec_check.core.collectors.notion_spec import (
    RawSpecBundle,
    collect_notion_spec,
)
from spec_check.core.notion import (
    NotionTransportError,
    NotionWrapper,
    NotionWriteRefused,
)
from spec_check.core.snapshot import create_check_dir


class _StubTransport:
    """Configurable transport. Each call name maps to a callable returning a
    canned response, so tests can simulate happy paths and failures
    without spinning up a real MCP.
    """

    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, /, **kwargs: Any) -> Any:
        self.calls.append((method, dict(kwargs)))
        handler = self.handlers.get(method)
        if handler is None:
            raise RuntimeError(f"no handler for {method!r}")
        return handler(**kwargs)


@pytest.fixture
def transport() -> _StubTransport:
    return _StubTransport()


@pytest.fixture
def wrapper(transport: _StubTransport) -> NotionWrapper:
    return NotionWrapper(transport)


def test_skipped_when_spec_id_empty(wrapper: NotionWrapper, tmp_path: Path) -> None:
    paths = create_check_dir(tmp_path)
    out = collect_notion_spec(wrapper, "", paths)
    assert out.status.state == "skipped"
    assert "no spec_id" in (out.status.detail or "")


def test_happy_path_writes_raw_blocks_and_returns_bundle(
    wrapper: NotionWrapper, transport: _StubTransport, tmp_path: Path
) -> None:
    paths = create_check_dir(tmp_path)
    transport.handlers["fetch_page"] = lambda **_: {
        "id": "page-1",
        "url": "https://notion.so/page-1",
        "properties": {"title": "Login"},
    }
    transport.handlers["fetch_block_children"] = lambda **_: {
        "results": [
            {
                "id": "blk-1",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"plain_text": "Acceptance Criteria"}]},
            },
            {
                "id": "blk-2",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"plain_text": "Given …"}]},
            },
        ],
        "has_more": False,
        "next_cursor": None,
    }

    out = collect_notion_spec(wrapper, "page-1", paths)

    assert out.status.state == "ok"
    assert out.status.name == "notion_spec"
    assert out.data is not None
    assert isinstance(out.data, RawSpecBundle)
    assert paths.spec_raw_blocks.exists()

    payload = json.loads(paths.spec_raw_blocks.read_text())
    assert payload["page"]["id"] == "page-1"
    assert len(payload["blocks"]) == 2


def test_pagination_walks_until_has_more_false(
    wrapper: NotionWrapper, transport: _StubTransport, tmp_path: Path
) -> None:
    paths = create_check_dir(tmp_path)
    transport.handlers["fetch_page"] = lambda **_: {"id": "page-1"}

    pages = [
        {"results": [{"id": "blk-1"}], "has_more": True, "next_cursor": "c1"},
        {"results": [{"id": "blk-2"}], "has_more": True, "next_cursor": "c2"},
        {"results": [{"id": "blk-3"}], "has_more": False, "next_cursor": None},
    ]

    def _fetch(**_: Any) -> Any:
        return pages.pop(0)

    transport.handlers["fetch_block_children"] = _fetch

    out = collect_notion_spec(wrapper, "page-1", paths)
    assert out.status.state == "ok"
    assert out.data is not None
    assert [b["id"] for b in out.data.blocks] == ["blk-1", "blk-2", "blk-3"]


def test_failed_when_fetch_page_blows_up(
    wrapper: NotionWrapper, transport: _StubTransport, tmp_path: Path
) -> None:
    paths = create_check_dir(tmp_path)

    def _boom(**_: Any) -> Any:
        raise NotionTransportError("MCP unreachable")

    transport.handlers["fetch_page"] = _boom

    out = collect_notion_spec(wrapper, "page-1", paths)
    assert out.status.state == "failed"
    assert "MCP unreachable" in (out.status.detail or "")
    assert not paths.spec_raw_blocks.exists()


def test_failed_when_block_fetch_blows_up(
    wrapper: NotionWrapper, transport: _StubTransport, tmp_path: Path
) -> None:
    paths = create_check_dir(tmp_path)
    transport.handlers["fetch_page"] = lambda **_: {"id": "page-1"}

    def _boom(**_: Any) -> Any:
        raise RuntimeError("rate limited")

    transport.handlers["fetch_block_children"] = _boom

    out = collect_notion_spec(wrapper, "page-1", paths)
    assert out.status.state == "failed"
    assert "rate limited" in (out.status.detail or "")


def test_firewall_refusal_propagates(
    wrapper: NotionWrapper, transport: _StubTransport, tmp_path: Path
) -> None:
    """If the wrapper itself ever rejects a call (which would be a bug
    because the collector only invokes allowlisted methods), we propagate
    rather than swallow. That preserves the firewall guarantee.
    """
    paths = create_check_dir(tmp_path)

    def _refuse(**_: Any) -> Any:
        raise NotionWriteRefused("forbidden")

    transport.handlers["fetch_page"] = _refuse

    with pytest.raises(NotionWriteRefused):
        collect_notion_spec(wrapper, "page-1", paths)
