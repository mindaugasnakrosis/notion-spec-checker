"""Read-only wrapper over the Notion MCP.

This is the **second** of two read-only firewalls (the other is
:mod:`spec_check.core.gitwrap`). The wrapper exposes only read methods —
``search``, ``fetch_page``, ``fetch_block_children``, ``query_database``,
``fetch_database``, ``fetch_user``, ``list_users``. Any attempt to invoke a
write method against the underlying client raises :class:`NotionWriteRefused`.

Why an allowlist (not a blocklist):
- The Notion API and the Notion MCP both keep adding write verbs.
- A blocklist will silently miss a future write tool. An allowlist fails
  closed: a new tool is invisible to spec-check until someone explicitly
  decides it is read-only and adds it to :data:`READ_ONLY_NOTION_METHODS`.

The wrapper does not talk to the real MCP itself. It takes a transport
object that satisfies the :class:`NotionMCPTransport` protocol — production
code (built in step 10) wires the actual ``mcp__notion__*`` tool calls
through this transport; tests pass a mock. That separation is what keeps
the firewall test independent of the live MCP.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# Methods we may legitimately call against Notion. Each is read-only by Notion's
# API definition. Adding to this set is a deliberate review event — see
# CONTRIBUTING.md.
READ_ONLY_NOTION_METHODS: frozenset[str] = frozenset(
    {
        "search",
        "fetch_page",
        "fetch_block_children",
        "fetch_database",
        "query_database",
        "fetch_user",
        "list_users",
        "fetch_block",
        "fetch_comments",
    }
)

# Sentinel set: methods we explicitly refuse. The wrapper never invokes any of
# these even if the underlying transport exposes them. Listed for explicit
# error messages and the test guard. Not exhaustive — the firewall fails
# closed, so anything *not* on the read-only allowlist is also refused.
KNOWN_WRITE_NOTION_METHODS: frozenset[str] = frozenset(
    {
        "create_page",
        "update_page",
        "delete_page",
        "archive_page",
        "restore_page",
        "create_database",
        "update_database",
        "delete_database",
        "create_block",
        "update_block",
        "delete_block",
        "append_block_children",
        "patch_block_children",
        "create_comment",
        "delete_comment",
        "update_comment",
        "create_user",
        "update_user",
        "delete_user",
        "set_page_property",
        "update_page_properties",
        "move_page",
        "duplicate_page",
    }
)


class NotionWriteRefused(RuntimeError):
    """Raised when the wrapper is asked to invoke a non-allowlisted Notion method."""


class NotionTransportError(RuntimeError):
    """Raised when the underlying MCP transport surfaces an error."""


@runtime_checkable
class NotionMCPTransport(Protocol):
    """Minimal contract spec-check needs from a Notion MCP client.

    The single ``call`` method takes a string method name and arbitrary
    keyword arguments, and returns whatever Notion gave back. Production
    code (step 10) implements this against the real ``mcp__notion__*``
    tool surface; tests pass an in-memory mock.
    """

    def call(self, method: str, /, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class NotionPage:
    """Minimal projection of a Notion page. Just what the parser needs."""

    page_id: str
    title: str
    url: str
    last_edited_time: str  # ISO 8601 from Notion; parsed downstream


class NotionWrapper:
    """The read-only firewall in front of any Notion MCP transport.

    Every public method routes through :meth:`_call`, which enforces the
    read-only allowlist. Direct attribute access on ``self._transport`` is
    not exposed — callers go through this wrapper or not at all.
    """

    def __init__(self, transport: NotionMCPTransport) -> None:
        self._transport = transport
        self._invocation_log: list[tuple[str, Mapping[str, Any]]] = []

    @property
    def invocation_log(self) -> list[tuple[str, Mapping[str, Any]]]:
        """Tuples of ``(method_name, kwargs)`` in invocation order. Useful in
        tests to assert that only allowlisted methods were called.
        """
        return list(self._invocation_log)

    # -- Read-only public surface -------------------------------------------

    def search(self, query: str, *, page_size: int | None = None) -> Any:
        """Search Notion pages by title. Returns whatever the MCP returns."""
        kwargs: dict[str, Any] = {"query": query}
        if page_size is not None:
            kwargs["page_size"] = page_size
        return self._call("search", **kwargs)

    def fetch_page(self, page_id: str) -> Any:
        return self._call("fetch_page", page_id=page_id)

    def fetch_block_children(
        self, block_id: str, *, start_cursor: str | None = None, page_size: int | None = None
    ) -> Any:
        kwargs: dict[str, Any] = {"block_id": block_id}
        if start_cursor is not None:
            kwargs["start_cursor"] = start_cursor
        if page_size is not None:
            kwargs["page_size"] = page_size
        return self._call("fetch_block_children", **kwargs)

    def fetch_block(self, block_id: str) -> Any:
        return self._call("fetch_block", block_id=block_id)

    def fetch_database(self, database_id: str) -> Any:
        return self._call("fetch_database", database_id=database_id)

    def query_database(self, database_id: str, **filters: Any) -> Any:
        return self._call("query_database", database_id=database_id, **filters)

    def fetch_user(self, user_id: str) -> Any:
        return self._call("fetch_user", user_id=user_id)

    def list_users(self) -> Any:
        return self._call("list_users")

    def fetch_comments(self, block_id: str) -> Any:
        return self._call("fetch_comments", block_id=block_id)

    # -- Internal -----------------------------------------------------------

    def _call(self, method: str, **kwargs: Any) -> Any:
        if method not in READ_ONLY_NOTION_METHODS:
            raise NotionWriteRefused(
                f"Notion method {method!r} is not on spec-check's read-only "
                f"allowlist. spec-check is read-only on Notion by contract; "
                f"refusing the call."
            )
        self._invocation_log.append((method, dict(kwargs)))
        try:
            return self._transport.call(method, **kwargs)
        except NotionWriteRefused:
            raise
        except Exception as exc:  # pragma: no cover - the transport's domain
            raise NotionTransportError(f"Notion MCP transport failed on {method!r}: {exc}") from exc
