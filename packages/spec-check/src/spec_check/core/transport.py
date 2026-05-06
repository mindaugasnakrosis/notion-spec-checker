"""Concrete :class:`NotionMCPTransport` implementations for the CLI.

The CLI runs outside a Claude Code session, but the Notion MCP only
exposes its tools *inside* a session. Two transports bridge the gap:

- :class:`NullTransport` — returns empty results for every read. Used when
  the CLI is invoked without any Notion data; the spec collector then
  reports ``skipped`` and rules that need spec data emit Info findings.

- :class:`PrefetchedTransport` — reads from an in-memory payload (or a
  JSON file) that Claude Code dropped on disk after calling
  ``mcp__notion__*`` tools itself. This is the production wiring for
  ``spec-check pull --spec-payload <path>``.

Neither transport ever writes to Notion. The :class:`NotionWrapper`
firewall is unchanged — this module only provides the read side.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class NullTransport:
    """Always returns empty results. Used when no Notion data is supplied."""

    def call(self, method: str, /, **kwargs: Any) -> Any:
        if method == "search":
            return {"results": []}
        if method == "fetch_block_children":
            return {"results": [], "has_more": False, "next_cursor": None}
        if method == "fetch_page":
            # Returning a minimal page shape lets the parser produce a
            # ParsedSpec with has_ac_section=False rather than crashing.
            page_id = kwargs.get("page_id", "(unknown)")
            return {"id": page_id, "url": "", "properties": {"title": {"title": []}}}
        # query_database / fetch_database / fetch_user / list_users / fetch_block /
        # fetch_comments — none in the v1 happy path; return safe defaults.
        if method == "list_users":
            return {"results": []}
        return {}


class PrefetchedTransport:
    """Serves canned Notion responses from an in-memory payload.

    Payload shape::

        {
          "page": {... Notion page object ...},
          "blocks": [... list of block objects ...],
          "search_results": {"<query>": [...], ...}   # optional
        }

    Only ``page`` and ``blocks`` are required for the v1 happy path
    (the resolver short-circuits when ``--spec`` is supplied, so search
    is rarely consulted). Search queries that aren't in
    ``search_results`` return an empty list.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise TypeError(f"payload must be a dict, got {type(payload).__name__}")
        self._payload = payload
        self._blocks_served = False

    @classmethod
    def from_file(cls, path: Path) -> PrefetchedTransport:
        with Path(path).open() as fh:
            data = json.load(fh)
        return cls(data)

    def call(self, method: str, /, **kwargs: Any) -> Any:
        if method == "search":
            query = kwargs.get("query", "")
            results = self._payload.get("search_results", {}).get(query, [])
            return {"results": results}

        if method == "fetch_page":
            page = self._payload.get("page")
            if not isinstance(page, dict):
                page_id = kwargs.get("page_id", "(unknown)")
                return {"id": page_id, "url": "", "properties": {"title": {"title": []}}}
            return page

        if method == "fetch_block_children":
            # Serve the full list once, then signal pagination is done.
            if self._blocks_served:
                return {"results": [], "has_more": False, "next_cursor": None}
            self._blocks_served = True
            blocks = self._payload.get("blocks", [])
            if not isinstance(blocks, list):
                blocks = []
            return {"results": blocks, "has_more": False, "next_cursor": None}

        return {}
