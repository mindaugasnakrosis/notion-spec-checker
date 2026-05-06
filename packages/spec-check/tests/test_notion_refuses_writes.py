"""The Notion read-only firewall.

This is the load-bearing safety test for the second of spec-check's two
read-only surfaces. If a future change lets any write method through the
wrapper, this file fails the build.

The transport is mocked — we never talk to the real Notion MCP here. The
wrapper-level guard is what we're testing, independent of any live MCP.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from spec_check.core.notion import (
    KNOWN_WRITE_NOTION_METHODS,
    READ_ONLY_NOTION_METHODS,
    NotionMCPTransport,
    NotionWrapper,
    NotionWriteRefused,
)


class _RecordingTransport:
    """In-memory transport that records every call for assertion in tests.

    Returns a stable canned response so the wrapper has something to hand back.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, /, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method, dict(kwargs)))
        return {"method": method, "kwargs": kwargs}


@pytest.fixture
def transport() -> _RecordingTransport:
    return _RecordingTransport()


@pytest.fixture
def wrapper(transport: _RecordingTransport) -> NotionWrapper:
    return NotionWrapper(transport)


# ---------------------------------------------------------------------------
# Firewall: every public read method calls only an allowlisted transport method
# ---------------------------------------------------------------------------


def test_only_allowlisted_methods_are_invoked_during_normal_use(
    transport: _RecordingTransport, wrapper: NotionWrapper
) -> None:
    """Exercise every public read method on the wrapper and assert that every
    underlying transport call was on the allowlist.
    """
    wrapper.search("login")
    wrapper.search("login", page_size=10)
    wrapper.fetch_page("abc-123")
    wrapper.fetch_block("blk-1")
    wrapper.fetch_block_children("page-1")
    wrapper.fetch_block_children("page-1", start_cursor="x", page_size=5)
    wrapper.fetch_database("db-1")
    wrapper.query_database("db-1", filter={"property": "Status", "equals": "Done"})
    wrapper.fetch_user("u-1")
    wrapper.list_users()
    wrapper.fetch_comments("blk-1")

    invoked_methods = {method for method, _ in transport.calls}
    illegal = invoked_methods - READ_ONLY_NOTION_METHODS
    assert illegal == set(), f"wrapper invoked non-allowlisted methods: {illegal}"


def test_invocation_log_matches_transport_calls(
    transport: _RecordingTransport, wrapper: NotionWrapper
) -> None:
    wrapper.search("foo")
    wrapper.fetch_page("page-1")

    # Wrapper's own log is in step with the transport's record.
    assert [m for m, _ in wrapper.invocation_log] == [m for m, _ in transport.calls]
    assert wrapper.invocation_log[0] == ("search", {"query": "foo"})
    assert wrapper.invocation_log[1] == ("fetch_page", {"page_id": "page-1"})


# ---------------------------------------------------------------------------
# Firewall: known write methods are refused before reaching the transport
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", sorted(KNOWN_WRITE_NOTION_METHODS))
def test_known_write_method_refused(
    method: str, wrapper: NotionWrapper, transport: _RecordingTransport
) -> None:
    """Direct ``_call`` with any known write method raises and never reaches
    the transport. We hit ``_call`` directly because the wrapper's public
    surface deliberately has no method that even *names* a write verb.
    """
    with pytest.raises(NotionWriteRefused, match=method):
        wrapper._call(method)
    assert transport.calls == []


def test_unknown_method_also_refused(
    wrapper: NotionWrapper, transport: _RecordingTransport
) -> None:
    """Methods that aren't on the allowlist *and* aren't on the known-write
    sentinel are also refused — fail closed.
    """
    with pytest.raises(NotionWriteRefused, match="not on spec-check's read-only allowlist"):
        wrapper._call("brand_new_2027_verb")
    assert transport.calls == []


def test_allowlist_and_writelist_do_not_overlap() -> None:
    """If a write verb ends up on the read-only allowlist, the firewall is
    compromised. Sanity check.
    """
    overlap = READ_ONLY_NOTION_METHODS & KNOWN_WRITE_NOTION_METHODS
    assert overlap == set(), f"Notion verbs in both allow + write lists: {overlap}"


# ---------------------------------------------------------------------------
# The wrapper's public surface contains no write-named methods
# ---------------------------------------------------------------------------


def test_wrapper_has_no_public_write_named_method() -> None:
    """Source-level guard: callers cannot stumble onto a method like
    ``update_page`` even by autocomplete. The class must expose only read
    verbs in its public surface.
    """
    public = {name for name in dir(NotionWrapper) if not name.startswith("_")}
    public -= {"invocation_log"}  # property, not a verb
    forbidden_substrings = (
        "create",
        "update",
        "delete",
        "archive",
        "restore",
        "append",
        "patch",
        "set",
        "move",
        "duplicate",
        "remove",
        "edit",
    )
    offenders = [
        name for name in public if any(sub in name.lower() for sub in forbidden_substrings)
    ]
    assert offenders == [], (
        f"NotionWrapper exposes write-shaped public methods: {offenders}. "
        f"Read-only-on-Notion is enforced by naming as well as by allowlist."
    )


# ---------------------------------------------------------------------------
# Transport protocol contract
# ---------------------------------------------------------------------------


def test_recording_transport_is_a_valid_transport() -> None:
    assert isinstance(_RecordingTransport(), NotionMCPTransport)


def test_magicmock_with_call_method_is_a_valid_transport() -> None:
    m = MagicMock()
    m.call = MagicMock(return_value={})
    assert isinstance(m, NotionMCPTransport)


# ---------------------------------------------------------------------------
# Happy-path passthrough: wrapper hands transport return value back to caller
# ---------------------------------------------------------------------------


def test_search_passes_query_and_returns_transport_response(
    wrapper: NotionWrapper, transport: _RecordingTransport
) -> None:
    out = wrapper.search("login flow", page_size=20)
    assert transport.calls == [("search", {"query": "login flow", "page_size": 20})]
    assert out == {"method": "search", "kwargs": {"query": "login flow", "page_size": 20}}


def test_fetch_page_passes_page_id(wrapper: NotionWrapper, transport: _RecordingTransport) -> None:
    out = wrapper.fetch_page("page-abc")
    assert transport.calls == [("fetch_page", {"page_id": "page-abc"})]
    assert out["kwargs"]["page_id"] == "page-abc"


def test_fetch_block_children_passes_pagination(
    wrapper: NotionWrapper, transport: _RecordingTransport
) -> None:
    wrapper.fetch_block_children("page-1", start_cursor="cursor-1", page_size=50)
    assert transport.calls == [
        (
            "fetch_block_children",
            {"block_id": "page-1", "start_cursor": "cursor-1", "page_size": 50},
        )
    ]


def test_query_database_passes_filter_kwargs(
    wrapper: NotionWrapper, transport: _RecordingTransport
) -> None:
    wrapper.query_database("db-1", filter={"property": "Done"}, page_size=100)
    assert transport.calls == [
        (
            "query_database",
            {"database_id": "db-1", "filter": {"property": "Done"}, "page_size": 100},
        )
    ]
